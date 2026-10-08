#!/usr/bin/env python3
"""
Propose les 5 meilleures fiches à indexer (score >= 6).
Filtre automatiquement les fiches de faible qualité.
"""

import os
import json
from datetime import datetime

FICHES_DIR = "pages/moteur-audiobook"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"

def load_proposed_history():
    """Charge la liste des URLs déjà proposées."""
    if os.path.exists(PROPOSED_HISTORY_FILE):
        with open(PROPOSED_HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_proposed_history(proposed):
    """Sauvegarde la liste des URLs proposées."""
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed)), f, ensure_ascii=False, indent=2)

def score_fiche_quality(question):
    """Évalue si une fiche va attirer les auteurs (score 0-10)."""
    q_lower = question.lower()
    score = 5.0

    # Mots-clés positifs (indiquent une vraie question d'auteur)
    author_keywords = {
        "contrat": 3, "éditeur": 3, "droits": 3, "agent": 3, "agence": 3,
        "vente": 2, "vendre": 2, "public": 2, "lecteur": 2,
        "publier": 2, "avance": 2, "royalties": 3, "négociation": 3,
        "prix": 2, "coût": 2, "budget": 2,
    }

    # Mots-clés négatifs (trop généraux ou niche)
    weak_keywords = {
        "pourquoi": -1, "philosophie": -2, "universel": -2,
        "actrice": -3, "cinéaste": -3, "retraduction": -3,
    }

    for keyword, points in author_keywords.items():
        if keyword in q_lower:
            score += points

    for keyword, points in weak_keywords.items():
        if keyword in q_lower:
            score += points

    q_len = len(question)
    if q_len < 30:
        score -= 2
    elif q_len > 120:
        score -= 1

    return max(0, min(10, score))

def get_best_fiches():
    """Retourne les 5 meilleures fiches (score >= 6)."""

    if not os.path.isdir(FICHES_DIR):
        print("❌ Dossier de fiches non trouvé")
        return [], []

    fiche_files = sorted(
        [f for f in os.listdir(FICHES_DIR) if f.endswith(".html") and f not in ["sitemap.xml", "robots-fragment.txt"]],
        key=lambda f: os.path.getmtime(os.path.join(FICHES_DIR, f)),
        reverse=True
    )

    proposed_history = load_proposed_history()
    to_propose = []
    skipped_low_quality = []

    for filename in fiche_files:
        slug = filename[:-5]
        url = f"{SITE_BASE_URL}{slug}.html"

        if url not in proposed_history:
            question = slug.replace("-", " ")
            quality_score = score_fiche_quality(question)

            if quality_score >= 6:  # Bon score seulement
                to_propose.append({
                    "slug": slug,
                    "url": url,
                    "quality_score": quality_score
                })
            else:
                skipped_low_quality.append({
                    "url": url,
                    "quality_score": quality_score
                })

        if len(to_propose) >= 5:
            break

    # Enregistrer les fiches proposées + faible qualité (jamais les revoir)
    for fiche in to_propose:
        proposed_history.add(fiche["url"])
    for fiche in skipped_low_quality:
        proposed_history.add(fiche["url"])
    save_proposed_history(proposed_history)

    return to_propose, skipped_low_quality

def main():
    print("=" * 80)
    print(f"📋 FICHES À INDEXER - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    fiches, skipped = get_best_fiches()

    if not fiches:
        print("✅ Aucune nouvelle fiche pertinente à proposer.")
        if skipped:
            print(f"⚠️  {len(skipped)} fiche(s) filtrée(s) pour faible qualité.")
        return

    print(f"\n🎯 {len(fiches)} fiche(s) À INDEXER (score >= 6) :\n")

    for i, fiche in enumerate(fiches, 1):
        print(f"{i}. {fiche['url']}")
        print(f"   Score qualité: {fiche['quality_score']:.1f}/10")

    if skipped:
        print(f"\n⚠️  {len(skipped)} fiche(s) filtrée(s) pour faible qualité (non proposées)")

    print(f"\n🔍 Lien GSC : https://search.google.com/u/1/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
