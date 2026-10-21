#!/usr/bin/env python3
"""
PIPELINE UNIFIÉE MOTEUR AUDIOBOOK

Intègre:
1. Question stock (podcast Bookmakers + expertise)
2. Google Ads volumes (données réelles)
3. GSC performance (clics, impressions)
4. Scoring audiobook (mots-clés, pertinence)
5. Titre optimisé (court + auteur + SEO)
6. Proposition TOP 5 à Google Search Console

Architecture:
question_stock.json (expertise) + keyword_planner.json (volume)
  → score_with_gsc.json
  → optimized_titles.json
  → propose to GSC
"""

import os, json, datetime, requests

STOCK_FILE = "automation/state/question_stock.json"
KEYWORD_FILE = "data/keyword_planner.json"
GSC_FILE = "data/gsc/pages.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
SCOPED_FILE = "data/questions_with_scope.json"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_proposed():
    """Charge les fiches déjà proposées."""
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

def get_volume_for_question(question, keywords_data):
    """Trouve le volume Google Ads pour une question."""
    if not keywords_data or "idees" not in keywords_data:
        return 0

    q_lower = question.lower().strip()

    # Match exact d'abord
    for idea in keywords_data.get("idees", []):
        if idea.get("requete", "").lower().strip() == q_lower:
            return idea.get("volume_mensuel_moyen", 0)

    # Match partiel si exact ne trouve rien
    words = set(q_lower.split())
    best_match = 0
    for idea in keywords_data.get("idees", []):
        requete = idea.get("requete", "").lower()
        idea_words = set(requete.split())
        overlap = len(words & idea_words)
        if overlap >= 2:  # Au moins 2 mots en commun
            best_match = max(best_match, idea.get("volume_mensuel_moyen", 0))

    return best_match

def generate_optimized_title(question, guest_name, volume):
    """Génère un titre optimisé SEO = la question elle-même."""
    # Titre = la question (autorité + expertise dans le contenu de la page)

    q_clean = question.strip().rstrip("?").strip()

    # Extrait le noyau de la question (avant "quand", "si", "pour", etc.)
    truncate_words = [" quand ", " si ", " pour ", " en ", " versus ", " ou "]
    for word in truncate_words:
        if word.lower() in q_clean.lower():
            q_clean = q_clean.split(word)[0].strip()
            break

    # Ajoute ? et assure 50-60 chars (format moteur-trafic)
    title = q_clean + "?"

    # Si trop court, remplace par la question complète (mieux pour SEO)
    if len(title) < 35:
        title = question.strip()
        if not title.endswith("?"):
            title = title + "?"

    # Si trop long, tronque intelligemment
    if len(title) > 60:
        title = title[:57] + "?"

    return title

def calculate_score(question, volume, gsc_data, proposed):
    """Score question basé sur volume + audiobook relevance + GSC."""

    # 1. Volume Google Ads (normalisé 0-10)
    vol_score = min(10, (volume / 100)) if volume else 0

    # 2. Audiobook relevance
    q_lower = question.lower()
    audiobook_keywords = ["audiobook", "revenu", "vivre", "publier", "droits",
                          "vente", "editeur", "auteur", "livre", "écrire", "contrat"]
    audiobook_score = 10 if any(kw in q_lower for kw in audiobook_keywords) else 8

    # 3. GSC performance (si déjà indexée)
    gsc_score = 0
    gsc_list = gsc_data if isinstance(gsc_data, list) else gsc_data.values()
    for page_data in gsc_list:
        if isinstance(page_data, dict) and page_data.get("clics", 0) > 0:
            gsc_score = 10
        elif isinstance(page_data, dict) and page_data.get("impressions", 0) > 0:
            gsc_score = max(gsc_score, 5)

    # 4. Bonus si pas encore proposée
    pending_bonus = 2 if not proposed else 0

    # Score final (pondéré)
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
    print(f"🎯 PIPELINE UNIFIÉE AUDIOBOOK — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Charge les données
    stock = load_json(STOCK_FILE, [])
    keywords = load_json(KEYWORD_FILE, {})
    gsc_data = load_json(GSC_FILE, {})
    proposed = load_proposed()

    if not stock:
        print("⚠️  Stock vide. Lancez generate_audiobook_fiches.py d'abord.")
        return

    print(f"\n🏊 Chargé: {len(stock)} questions du podcast\n")

    # Score chaque question du stock
    scored_questions = []
    for q_data in stock:
        question = q_data.get("question", {}).get("question", "")
        guest_name = q_data.get("guest_name", "")

        if not question:
            continue

        # Récupère le volume Google Ads
        volume = get_volume_for_question(question, keywords)

        # Génère titre optimisé
        title = generate_optimized_title(question, guest_name, volume)

        # URL slug
        slug = question.lower().replace(" ", "-").replace("?", "").replace("'", "")[:60]
        url = f"{SITE_BASE_URL}{slug}.html"

        # Score
        already_proposed = url in proposed
        score = calculate_score(question, volume, gsc_data, already_proposed)

        if url not in proposed:  # Ne score que les non proposées
            scored_questions.append({
                "question": question,
                "title": title,
                "guest": guest_name,
                "volume": volume,
                "url": url,
                "score": score,
                "original_data": q_data
            })

    # Trier par score
    scored_questions.sort(key=lambda x: -x["score"])

    print(f"📊 Scorées: {len(scored_questions)} non proposées\n")
    print("TOP 10:\n")
    for i, q in enumerate(scored_questions[:10], 1):
        print(f"{i}. [{q['score']:>4.1f}⭐] {q['volume']:>4} vol | {q['title'][:50]}")

    # TOP 5 à proposer
    to_propose = scored_questions[:5]

    if not to_propose:
        print("\n✅ Aucune nouvelle question pertinente.")
        print(f"📊 Total proposées: {len(proposed)}")
        return

    print(f"\n🎯 {len(to_propose)} FICHES À PROPOSER :\n")
    for i, q in enumerate(to_propose, 1):
        print(f"{i}. ⭐ Score: {q['score']:.1f}/10")
        print(f"   \"{q['title']}\"")
        print(f"   Auteur: {q['guest']}")
        print(f"   Volume: {q['volume']} recherches/mois")
        print(f"   {q['url']}\n")

    # Soumis à Google
    print("📤 Soumission à Google Search Console...\n")
    urls = [q["url"] for q in to_propose]
    token = get_gsc_token()
    submitted = submit_to_gsc(urls, token)
    print(f"\n✅ {len(submitted)}/{len(urls)} soumises à Google")

    # Marquer comme proposées
    for q in to_propose:
        proposed.add(q["url"])
    save_proposed(proposed)

    print(f"\n📊 Total proposées: {len(proposed)}")
    print(f"\n🔍 Google Search Console: https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
