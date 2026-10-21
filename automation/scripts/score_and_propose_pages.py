#!/usr/bin/env python3
"""
PIPELINE SIMPLE AUDIOBOOK

1. Charge pages générées (generate_audiobook_fiches.py)
2. Score pages (volume Google Ads + audiobook + GSC)
3. TOP 5 sélectionnées
4. Optimise titres (règles: 50-60 chars, avant "quand/si/pour", +?)
5. Propose à Google

C'est tout.
"""

import os, json, re, requests, datetime
from pathlib import Path

PAGES_DIR = "pages/moteur-audiobook/"
KEYWORD_FILE = "data/keyword_planner.json"
GSC_FILE = "data/gsc/pages.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]
GSC_SITE = "sc-domain:audiobooklab.fr"
SITEMAP_URL = "https://audiobooklab.fr/blog-audiobook/sitemap.xml"
LAST_RUN_FILE = "data/last_run.json"

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_proposed():
    if not os.path.exists(PROPOSED_HISTORY_FILE):
        return set()
    with open(PROPOSED_HISTORY_FILE) as f:
        data = json.load(f)
    return set(data) if isinstance(data, list) else set()

def save_proposed(proposed_set):
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed_set)), f, ensure_ascii=False, indent=2)

def extract_title_from_html(html_content):
    """Extrait le titre de la page (h1 ou title)."""
    # Cherche h1 d'abord
    match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content)
    if match:
        return match.group(1)
    # Sinon title
    match = re.search(r'<title>([^<]+)</title>', html_content)
    return match.group(1) if match else ""

MAX_TITLE = 70  # au-dessus, on reformule

def clean_title(t):
    import html
    t = html.unescape(t).replace("\xa0", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t.rstrip(" ?").strip() + "?"

def rewrite_title(title):
    """Reformule (sans tronquer) une question trop longue en question Google courte et complète."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = (
        "Reformule cette question en une question courte, naturelle et complète, "
        "telle qu'un auteur la taperait sur Google ou la poserait à ChatGPT.\n"
        "Règles : même sujet et mots-clés principaux, 45 à 65 caractères, grammaticalement "
        "complète, finit par '?', rien d'inventé, pas de 'et' qui enchaîne deux questions.\n"
        "Réponds uniquement par la question.\n\n"
        f"Question : {title}"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 100,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        r.raise_for_status()
        out = clean_title(r.json()["content"][0]["text"].strip().strip('"'))
        if 25 <= len(out) <= 75:
            return out
    except Exception as e:
        print(f"⚠️  Reformulation : {str(e)[:80]}")
    return None

def optimize_title(original_title):
    """Garde la question si elle est assez courte ; sinon la reformule (jamais de troncature)."""
    title = clean_title(original_title)
    if len(title) <= MAX_TITLE:
        return title
    return rewrite_title(title) or title

def calculate_score(html_content, keywords_data, gsc_data, proposed_url):
    """Score simple: volume + audiobook + GSC."""

    html_lower = html_content.lower()

    # 1. Volume Google Ads - récupère le volume moyen
    volume = 0
    if keywords_data and "idees" in keywords_data:
        volumes = [idea.get("volume_mensuel_moyen", 0) for idea in keywords_data.get("idees", [])]
        volume = sum(volumes) / len(volumes) if volumes else 0

    vol_score = min(10, (volume / 100)) if volume else 0

    # 2. Audiobook relevance
    audiobook_keywords = ["audiobook", "revenu", "vivre", "publier", "droits",
                          "vente", "editeur", "auteur", "livre", "écrire", "contrat"]
    audiobook_score = 10 if any(kw in html_lower for kw in audiobook_keywords) else 6

    # 3. GSC performance
    gsc_score = 0
    gsc_list = gsc_data if isinstance(gsc_data, list) else gsc_data.values()
    for page_data in gsc_list:
        if isinstance(page_data, dict) and page_data.get("clics", 0) > 0:
            gsc_score = 10
        elif isinstance(page_data, dict) and page_data.get("impressions", 0) > 0:
            gsc_score = max(gsc_score, 5)

    # 4. Bonus si pas encore proposée
    pending_bonus = 2 if not proposed_url else 0

    # Score final
    final = (vol_score * 0.5) + (audiobook_score * 0.3) + (gsc_score * 0.15) + pending_bonus
    return round(min(10, final), 1)

def get_gsc_token():
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "{}"))
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        print(f"⚠️  Token GSC : {str(e)[:100]}")
        return None

def submit_to_gsc(urls, token):
    """1) soumet le sitemap (seul levier API réel pour informer Google)
    2) inspecte chaque URL proposée (état d'indexation). L'API ne peut PAS 'demander l'indexation'."""
    from urllib.parse import quote
    report = {"sitemap": None, "inspection": {}}
    if not token:
        print("⚠️  Soumission GSC : token manquant")
        return report
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.put(
            f"https://www.googleapis.com/webmasters/v3/sites/{quote(GSC_SITE, safe='')}/sitemaps/{quote(SITEMAP_URL, safe='')}",
            headers=headers, timeout=30)
        report["sitemap"] = r.status_code
        print(f"  {'✅' if r.status_code in (200, 204) else '⚠️ '} Sitemap soumis : code {r.status_code} {r.text[:120] if r.status_code >= 300 else ''}")
    except Exception as e:
        report["sitemap"] = str(e)[:80]
        print(f"  ⚠️  Sitemap : {report['sitemap']}")

    for url in urls:
        try:
            r = requests.post(
                "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                json={"inspectionUrl": url, "siteUrl": GSC_SITE, "languageCode": "fr"},
                headers={**headers, "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 200:
                st = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
                report["inspection"][url] = st.get("coverageState", "?")
                print(f"  ✅ {url} → {report['inspection'][url]}")
            else:
                report["inspection"][url] = f"code {r.status_code}"
                print(f"  ⚠️  {url} : code {r.status_code} {r.text[:100]}")
        except Exception as e:
            report["inspection"][url] = str(e)[:50]
            print(f"  ⚠️  {url} : {str(e)[:50]}")
    return report

def main():
    print("=" * 80)
    print(f"🎯 SCORE + PROPOSE — {datetime.datetime.now().isoformat()}")
    print("=" * 80)

    # Charge données
    keywords = load_json(KEYWORD_FILE, {})
    gsc_data = load_json(GSC_FILE, {})
    proposed = load_proposed()

    # Score les pages
    pages_to_score = []

    if os.path.exists(PAGES_DIR):
        for html_file in sorted(Path(PAGES_DIR).glob("*.html")):
            with open(html_file, "r", encoding="utf-8") as f:
                html_content = f.read()

            original_title = extract_title_from_html(html_content)
            url = f"{SITE_BASE_URL}{html_file.name}"

            # Score
            score = calculate_score(html_content, keywords, gsc_data, url in proposed)

            optimized_title = clean_title(original_title)

            if url not in proposed:
                pages_to_score.append({
                    "filename": html_file.name,
                    "url": url,
                    "original_title": original_title,
                    "optimized_title": optimized_title,
                    "score": score
                })

    if not pages_to_score:
        print("⚠️  Aucune page trouvée.")
        return

    # Trier par score
    pages_to_score.sort(key=lambda x: -x["score"])

    print(f"\n🏊 Pages trouvées: {len(pages_to_score)}\n")
    print("TOP 10:\n")
    for i, page in enumerate(pages_to_score[:10], 1):
        print(f"{i}. [{page['score']:>4.1f}⭐] {page['optimized_title'][:50]}")

    # TOP 5 à proposer
    to_propose = pages_to_score[:5]

    if not to_propose:
        print("\n✅ Aucune nouvelle page pertinente.")
        return

    for page in to_propose:
        page["optimized_title"] = optimize_title(page["original_title"])

    print(f"\n🎯 {len(to_propose)} PAGES À INDEXER :\n")
    for i, page in enumerate(to_propose, 1):
        print(f"{i}. ⭐ Score: {page['score']:.1f}/10")
        print(f"   Titre: \"{page['optimized_title']}\"")
        print(f"   {page['url']}\n")

    # Soumets à Google
    print("📤 Soumission à Google Search Console...\n")
    urls = [page["url"] for page in to_propose]
    token = get_gsc_token()
    report = submit_to_gsc(urls, token)
    os.makedirs("data", exist_ok=True)
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.datetime.now().isoformat(), "sitemap": report["sitemap"],
                   "pages": [{"titre": p["optimized_title"], "titre_original": p["original_title"],
                              "score": p["score"], "url": p["url"],
                              "google": report["inspection"].get(p["url"])} for p in to_propose]},
                  f, ensure_ascii=False, indent=2)

    # Marquer comme proposées
    for page in to_propose:
        proposed.add(page["url"])
    save_proposed(proposed)

    print(f"\n📊 Total proposées: {len(proposed)}")
    print(f"\n🔍 Google Search Console: https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
