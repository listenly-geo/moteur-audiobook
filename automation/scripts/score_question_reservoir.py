#!/usr/bin/env python3
"""
Score quotidien de TOUTES les questions du réservoir.

Scoring = (volume * 0.5) + (audiobook_relevance * 0.3) + (gsc_performance * 0.2)

TOP 5 = proposées chaque jour à l'indexation.
"""
import os, json, datetime

RESERVOIR_FILE = "data/question_reservoir.json"
GSC_FILE = "data/gsc/pages.json"  # Données GSC réelles
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"

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

def calculate_score(question, volume, gsc_data, proposed):
    """Calcule le score d'une question."""

    # 1. Volume Google Ads (normalisé 0-10)
    vol_score = min(10, (volume / 100)) if volume else 0

    # 2. Audiobook relevance (keywords pertinents)
    q_lower = question.lower()
    audiobook_keywords = ["audiobook", "revenu", "vivre", "publier", "droits", "vente", "editeur", "auteur", "livre"]
    audiobook_score = 10 if any(kw in q_lower for kw in audiobook_keywords) else 4

    # 3. GSC performance (si déjà indexée)
    gsc_score = 0
    gsc_list = gsc_data if isinstance(gsc_data, list) else gsc_data.values()
    for page_data in gsc_list:
        if isinstance(page_data, dict) and page_data.get("clics", 0) > 0:
            gsc_score = 10  # Page qui performe
        elif isinstance(page_data, dict) and page_data.get("impressions", 0) > 0:
            gsc_score = max(gsc_score, 5)  # Page vue

    # 4. Bonus si pas encore proposée
    pending_bonus = 0 if proposed else 2

    # Score final (pondéré)
    final = (vol_score * 0.5) + (audiobook_score * 0.3) + (gsc_score * 0.2) + pending_bonus
    return round(min(10, final), 1)

def main():
    print("=" * 80)
    print(f"📊 SCORING RÉSERVOIR — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Charge les données
    reservoir = load_json(RESERVOIR_FILE, [])
    gsc_data = load_json(GSC_FILE, {})
    proposed = load_proposed()

    if not reservoir:
        print("⚠️  Réservoir vide. Lancez build_question_reservoir.py d'abord.")
        return

    # Score chaque question
    for q in reservoir:
        url = f"https://audiobooklab.fr/blog-audiobook/{q['question'].lower().replace(' ', '-')[:60]}.html"
        already_proposed = url in proposed

        q["score"] = calculate_score(q["question"], q["volume_mensuel"], gsc_data, already_proposed)
        q["last_scored"] = datetime.date.today().isoformat()

    # Trier par score
    reservoir.sort(key=lambda x: -x["score"])

    # Sauvegarder
    os.makedirs(os.path.dirname(RESERVOIR_FILE), exist_ok=True)
    with open(RESERVOIR_FILE, "w", encoding="utf-8") as f:
        json.dump(reservoir, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Scoring complet: {len(reservoir)} questions\n")
    print("TOP 10 par score :\n")
    for i, q in enumerate(reservoir[:10], 1):
        print(f"{i}. [{q['score']:>4.1f}⭐] {q['volume_mensuel']:>4} vol | {q['question'][:50]}")

    print(f"\nFichier: {RESERVOIR_FILE}")

if __name__ == "__main__":
    main()
