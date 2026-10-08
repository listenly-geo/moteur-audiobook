#!/usr/bin/env python3
"""
Évalue la qualité des fiches pour attirer les auteurs.
Score = probabilité qu'un auteur tape cette question dans Google.
"""

import json
import os
from pathlib import Path

PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"

# Mots-clés d'auteurs (indiquent une vraie question d'auteur)
AUTHOR_KEYWORDS = {
    "contrat": 3, "éditeur": 3, "droits": 3, "agent": 3, "agence": 3,
    "vente": 2, "vendre": 2, "public": 2, "lecteur": 2,
    "publier": 2, "publication": 2, "avance": 2, "royalties": 3,
    "négociation": 3, "prix": 2, "coût": 2, "budget": 2,
    "manuscrit": 2, "rédaction": 1, "écriture": 1,
}

# Mots-clés faibles (questions trop générales ou philosophiques)
WEAK_KEYWORDS = {
    "pourquoi": -1, "philosophie": -2, "universel": -2, "particulier": -2,
    "choix": -1, "pourquoi choisir": -2,
}

def score_fiche(question):
    """Calcule un score de pertinence (0-10)."""
    q_lower = question.lower()
    score = 5.0  # Base neutre

    # Bonus pour mots-clés d'auteurs
    for keyword, points in AUTHOR_KEYWORDS.items():
        if keyword in q_lower:
            score += points

    # Malus pour questions faibles
    for keyword, points in WEAK_KEYWORDS.items():
        if keyword in q_lower:
            score += points  # points est négatif

    # Longueur (questions trop courtes ou trop longues ne performent pas)
    q_len = len(question)
    if q_len < 30:
        score -= 2  # Trop courte
    elif q_len > 120:
        score -= 1  # Trop longue

    # Pénalité pour questions trop niche
    niche_words = ["actrice", "cinéaste", "retraduction", "langue"]
    for word in niche_words:
        if word in q_lower:
            score -= 3

    return max(0, min(10, score))  # Clamp 0-10

def load_proposed_history():
    """Charge les fiches proposées."""
    if os.path.exists(PROPOSED_HISTORY_FILE):
        with open(PROPOSED_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def main():
    fiches_urls = load_proposed_history()

    print("=" * 80)
    print("🔍 QUALITÉ DES FICHES PROPOSÉES")
    print("=" * 80)

    for url in fiches_urls[-5:]:  # Dernières 5 fiches proposées
        # Extraire la question du slug
        slug = url.split("/")[-1].replace(".html", "")
        question = slug.replace("-", " ").title()

        score = score_fiche(question)
        emoji = "✅" if score >= 6 else "⚠️" if score >= 4 else "❌"

        print(f"\n{emoji} Score: {score:.1f}/10")
        print(f"   Question: {question[:70]}...")
        print(f"   URL: {url}")

        if score < 4:
            print(f"   → RISQUÉE: peu de volume de recherche probable")
        elif score < 6:
            print(f"   → ACCEPTABLE: mais pourrait être mieux ciblée")
        else:
            print(f"   → PERTINENTE: bonne probabilité de clics auteurs")

if __name__ == "__main__":
    main()
