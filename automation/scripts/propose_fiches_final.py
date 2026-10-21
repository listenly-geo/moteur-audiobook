#!/usr/bin/env python3
"""
Proposition quotidienne des 5 meilleures questions du réservoir.

Utilise question_reservoir.json (déjà scoré).
Les TOP 5 sont proposées à l'indexation Google.
"""
import os, json, datetime, requests

RESERVOIR_FILE = "data/question_reservoir.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_proposed():
    """Charge la liste des fiches déjà proposées."""
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
    print(f"🎯 PROPOSITION QUOTIDIENNE — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Charge le réservoir scoré
    reservoir = load_json(RESERVOIR_FILE, [])
    proposed = load_proposed()

    if not reservoir:
        print("⚠️  Réservoir vide.")
        return

    # Sélectionne TOP 5 non encore proposées
    candidates = []
    for q_data in reservoir:
        question = q_data.get("question", "")
        score = q_data.get("score", 0)
        volume = q_data.get("volume_mensuel", 0)

        # URL slugifiée (garde le ? pour le titre, le supprime pour l'URL)
        slug = question.lower().replace(" ", "-").replace("?", "").replace("'", "")[:60]
        url = f"{SITE_BASE_URL}{slug}.html"

        # Titre avec ?
        title_with_question = question if question.endswith("?") else question + "?"

        if url not in proposed:  # Non encore proposée
            candidates.append({
                "question": title_with_question,  # AVEC ?
                "url": url,
                "volume": volume,
                "score": score
            })

    # TOP 5 (déjà triés par score)
    to_propose = candidates[:5]

    if not to_propose:
        print("✅ Aucune nouvelle question pertinente.")
        print(f"📊 Total proposées: {len(proposed)}")
        return

    print(f"\n🎯 {len(to_propose)} QUESTIONS À INDEXER :\n")
    for i, q in enumerate(to_propose, 1):
        print(f"{i}. ⭐ Score: {q['score']:.1f}/10")
        print(f"   \"{q['question']}\"")
        print(f"   Volume: {q['volume']} recherches/mois")
        print(f"   {q['url']}\n")

    # Soumettre à Google
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
