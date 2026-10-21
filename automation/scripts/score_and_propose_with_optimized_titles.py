#!/usr/bin/env python3
"""
PIPELINE COMPLÈTE AUDIOBOOK

1. Charge pages générées (generate_audiobook_fiches.py)
2. Google Ads volumes (keyword_planner.py)
3. Score pages (volume + audiobook + GSC)
4. GÉNÈRE titres optimisés basés sur Google Ads
5. TOP 5 avec titres optimisés
6. Propose à Google Search Console

Titre optimisé = vraie requête Google avec volume
Objectif: toucher plus de monde avec les requêtes réelles
"""

import os, json, re, requests, datetime
from pathlib import Path

PAGES_DIR = "pages/moteur-audiobook/"
KEYWORD_FILE = "data/keyword_planner.json"
GSC_FILE = "data/gsc/pages.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_proposed():
    """Charge les URLs déjà proposées."""
    if not os.path.exists(PROPOSED_HISTORY_FILE):
        return set()
    with open(PROPOSED_HISTORY_FILE) as f:
        data = json.load(f)
    return set(data) if isinstance(data, list) else set()

def save_proposed(proposed_set):
    """Sauvegarde les fiches proposées."""
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed_set)), f, ensure_ascii=False, indent=2)

def extract_title_from_html(html_content):
    """Extrait le titre <title> du HTML."""
    match = re.search(r'<title>([^<]+)</title>', html_content)
    return match.group(1) if match else ""

def extract_h1_from_html(html_content):
    """Extrait le h1 du HTML."""
    match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content)
    return match.group(1) if match else ""

def find_best_matching_keyword(page_content, keywords_data):
    """Trouve le meilleur keyword Google Ads pour la page."""
    if not keywords_data or "idees" not in keywords_data:
        return None, 0

    content_lower = page_content.lower()
    best_keyword = None
    best_volume = 0
    best_match_score = 0

    # Cherche le keyword qui matche le mieux avec le contenu de la page
    for idea in keywords_data.get("idees", []):
        requete = idea.get("requete", "").lower()
        volume = idea.get("volume_mensuel_moyen", 0)

        # Calcule le score de match (nombre de mots en commun)
        requete_words = set(requete.split())
        content_words = set(content_lower.split())
        overlap = len(requete_words & content_words)

        if overlap >= 2 and volume > best_volume:
            best_keyword = idea.get("requete", "")
            best_volume = volume
            best_match_score = overlap

    return best_keyword, best_volume

def generate_optimized_title(original_title, best_keyword, volume):
    """Génère un titre optimisé basé sur Google Ads keyword."""

    # Si on a un keyword Google Ads avec volume, l'utilise
    if best_keyword and volume > 0:
        title = best_keyword
        # Ajoute ? si absent
        if not title.endswith("?"):
            title = title + "?"
        # Assure 50-60 chars
        if len(title) > 60:
            title = title[:57] + "?"
        return title, volume

    # Sinon, retourne le titre original
    return original_title, 0

def calculate_score(page_html, volume, keywords_data, gsc_data, proposed_url):
    """Score page basé sur volume + audiobook relevance + GSC."""

    # 1. Volume Google Ads (normalisé 0-10)
    vol_score = min(10, (volume / 100)) if volume else 0

    # 2. Audiobook relevance (mots-clés)
    html_lower = page_html.lower()
    audiobook_keywords = ["audiobook", "revenu", "vivre", "publier", "droits",
                          "vente", "editeur", "auteur", "livre", "écrire", "contrat"]
    audiobook_score = 10 if any(kw in html_lower for kw in audiobook_keywords) else 7

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
    """Génère un token OAuth2 pour Google Search Console."""
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
    """Soumet les URLs à Google Search Console."""
    if not token:
        print("⚠️  Soumission GSC : token manquant")
        return []

    submitted = []
    for url in urls:
        try:
            api_url = f"https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
            body = {"inspectionUrl": url}
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            r = requests.post(api_url, json=body, headers=headers, timeout=30)
            if r.status_code == 200:
                submitted.append(url)
                print(f"  ✅ {url}")
            else:
                print(f"  ⚠️  {url} : code {r.status_code}")
        except Exception as e:
            print(f"  ⚠️  {url} : {str(e)[:50]}")
    return submitted

def main():
    print("=" * 80)
    print(f"🎯 PIPELINE SCORE + TITRES OPTIMISÉS — {datetime.datetime.now().isoformat()}")
    print("=" * 80)

    # Charge données
    keywords = load_json(KEYWORD_FILE, {})
    gsc_data = load_json(GSC_FILE, {})
    proposed = load_proposed()

    # Trouve et score les pages
    pages_to_score = []

    if os.path.exists(PAGES_DIR):
        for html_file in sorted(Path(PAGES_DIR).glob("*.html")):
            with open(html_file, "r", encoding="utf-8") as f:
                html_content = f.read()

            original_title = extract_title_from_html(html_content)
            h1 = extract_h1_from_html(html_content)

            # URL de la page
            url = f"{SITE_BASE_URL}{html_file.name}"

            # Trouve le meilleur keyword Google Ads
            best_keyword, volume = find_best_matching_keyword(html_content, keywords)

            # Génère titre optimisé
            optimized_title, matched_volume = generate_optimized_title(original_title, best_keyword, volume)

            # Score
            score = calculate_score(html_content, matched_volume, keywords, gsc_data, url in proposed)

            if url not in proposed:
                pages_to_score.append({
                    "filename": html_file.name,
                    "url": url,
                    "original_title": original_title,
                    "h1": h1,
                    "optimized_title": optimized_title,
                    "keyword": best_keyword,
                    "volume": matched_volume,
                    "score": score
                })

    if not pages_to_score:
        print("⚠️  Aucune page trouvée.")
        return

    # Trier par score
    pages_to_score.sort(key=lambda x: -x["score"])

    print(f"\n🏊 Pages trouvées: {len(pages_to_score)}\n")
    print("TOP 10 par score:\n")
    for i, page in enumerate(pages_to_score[:10], 1):
        print(f"{i}. [{page['score']:>4.1f}⭐] {page['volume']:>4} vol | {page['optimized_title'][:50]}")

    # TOP 5 à proposer
    to_propose = pages_to_score[:5]

    if not to_propose:
        print("\n✅ Aucune nouvelle page pertinente.")
        return

    print(f"\n🎯 {len(to_propose)} PAGES À INDEXER :\n")
    for i, page in enumerate(to_propose, 1):
        print(f"{i}. ⭐ Score: {page['score']:.1f}/10")
        print(f"   Titre optimisé: \"{page['optimized_title']}\"")
        if page['keyword']:
            print(f"   Keyword Google: \"{page['keyword']}\"")
        print(f"   Volume: {page['volume']} recherches/mois")
        print(f"   {page['url']}\n")

    # Soumets à Google
    print("📤 Soumission à Google Search Console...\n")
    urls = [page["url"] for page in to_propose]
    token = get_gsc_token()
    submitted = submit_to_gsc(urls, token)
    print(f"\n✅ {len(submitted)}/{len(urls)} soumises à Google")

    # Marquer comme proposées
    for page in to_propose:
        proposed.add(page["url"])
    save_proposed(proposed)

    print(f"\n📊 Total proposées: {len(proposed)}")
    print(f"\n🔍 Google Search Console: https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
