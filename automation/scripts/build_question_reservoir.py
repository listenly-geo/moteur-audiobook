#!/usr/bin/env python3
"""
Construit le réservoir de questions à partir de Google Keyword Planner.

Le réservoir = TOUTES les questions possibles avec volume.
Chaque jour, le système les score et propose les TOP 5.

Utilise keyword_planner.json (résultats Google Ads API).
"""
import os, json, datetime

KEYWORD_FILE = "data/keyword_planner.json"
RESERVOIR_FILE = "data/question_reservoir.json"

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def main():
    print("=" * 80)
    print(f"🏊 CONSTRUCTION RÉSERVOIR — {datetime.date.today().isoformat()}")
    print("=" * 80)

    # Charge les résultats Google Keyword Planner
    keywords = load_json(KEYWORD_FILE)

    if keywords.get("statut") != "connecte":
        print(f"⚠️  Keyword Planner non connecté: {keywords.get('statut')}")
        return

    ideas = keywords.get("idees", [])
    if not ideas:
        print("⚠️  Aucune idée Google Ads retournée")
        return

    # Construire le réservoir
    reservoir = []
    for idea in ideas:
        requete = idea.get("requete", "")
        volume = idea.get("volume_mensuel_moyen", 0)
        concurrence = idea.get("concurrence", "UNSPECIFIED")

        if requete and volume > 0:  # Seulement les questions avec du volume
            reservoir.append({
                "question": requete,
                "volume_mensuel": volume,
                "concurrence": concurrence,
                "status": "pending",  # pending, proposed, indexed, archived
                "date_added": datetime.date.today().isoformat(),
                "score": 0.0,
                "last_scored": None
            })

    # Trier par volume (meilleur d'abord)
    reservoir.sort(key=lambda x: -x["volume_mensuel"])

    # Sauvegarder
    os.makedirs(os.path.dirname(RESERVOIR_FILE), exist_ok=True)
    with open(RESERVOIR_FILE, "w", encoding="utf-8") as f:
        json.dump(reservoir, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Réservoir construit: {len(reservoir)} questions")
    print(f"\nTop 5 par volume:\n")
    for i, q in enumerate(reservoir[:5], 1):
        print(f"{i}. [{q['volume_mensuel']:>4} vol] {q['question']}")

    print(f"\nFichier: {RESERVOIR_FILE}")

if __name__ == "__main__":
    main()
