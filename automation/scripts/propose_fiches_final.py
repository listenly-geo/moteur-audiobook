#!/usr/bin/env python3
"""
Proposition quotidienne des 5 meilleures fiches audiobook.

Combine:
  1. optimized_titles.json (titre + pertinence audiobook)
  2. keyword_planner.json (volume Google Ads)
  3. proposed_history.json (déjà proposées?)

Scoring final = (titre_score * 0.4) + (volume_score * 0.3) + (audiobook_relevance * 0.3)
Top 5 = proposées à l'indexation → envoyées à Google Search Console

Output: rapport + update proposed_history.json
"""
import os, json, datetime

TITLES_FILE = "data/optimized_titles.json"
KEYWORD_FILE = "data/keyword_planner.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"

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
    return set(data) if isinstance(data, list) else {data.get("url")}

def save_proposed(proposed_set):
    """Sauvegarde les fiches proposées."""
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed_set)), f, ensure_ascii=False, indent=2)

def calculate_final_score(title_data, volume):
    """Calcule le score final = titre + volume + audiobook relevance."""
    title_score = title_data.get("score", 5.0)

    # Volume score (1-100 mille recherches/mois)
    vol_normalized = min(100, (volume or 100) / 100)
    volume_score = vol_normalized * 10

    # Audiobook relevance (mots-clés pertinents?)
    title = title_data.get("title_optimized", "").lower()
    audiobook_keywords = ["audiobook", "revenu", "vivre", "publier", "droits", "vente"]
    has_audiobook_kw = any(kw in title for kw in audiobook_keywords)
    audiobook_score = 10 if has_audiobook_kw else 6

    # Scoring final (pondéré)
    final = (title_score * 0.4) + (volume_score * 0.3) + (audiobook_score * 0.3)
    return round(final, 1)

def main():
    print("=" * 80)
    print(f"🎯 PROPOSITION QUOTIDIENNE — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Charge les données
    titles = load_json(TITLES_FILE, [])
    keywords = load_json(KEYWORD_FILE, {})
    proposed = load_proposed()

    # Index volumes par question
    volumes = {}
    for idea in keywords.get("idees", []):
        volumes[idea.get("requete", "")] = idea.get("volume_mensuel_moyen", 0)

    # Calcule scores et filtre
    candidates = []
    for title_data in titles:
        slug = title_data.get("slug", "")
        question = title_data.get("question", "")
        url = f"{SITE_BASE_URL}{slug}.html"

        if url in proposed:
            continue  # Déjà proposée

        volume = volumes.get(question, 100)
        final_score = calculate_final_score(title_data, volume)

        candidates.append({
            "slug": slug,
            "url": url,
            "title": title_data.get("title_optimized", ""),
            "author": title_data.get("author", ""),
            "volume": volume,
            "score": final_score
        })

    # Trier par score et prendre top 5
    candidates.sort(key=lambda x: -x["score"])
    to_propose = candidates[:5]

    if not to_propose:
        print("✅ Aucune nouvelle fiche pertinente à proposer.")
        return

    print(f"\n🎯 {len(to_propose)} FICHES À INDEXER :\n")

    for i, fiche in enumerate(to_propose, 1):
        print(f"{i}. ⭐ Score: {fiche['score']:.1f}/10")
        print(f"   {fiche['title']}")
        print(f"   {fiche['author']}")
        print(f"   Volume: {fiche['volume']} recherches/mois")
        print(f"   {fiche['url']}\n")

    # Marquer comme proposées
    for fiche in to_propose:
        proposed.add(fiche["url"])
    save_proposed(proposed)

    print(f"📊 Total proposées (historique): {len(proposed)}")
    print(f"\n🔍 Google Search Console: https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
