#!/usr/bin/env python3
"""
Moteur 4 — "Auteur → Audiobook"
Pipeline : RSS (Bookmakers) → Whisper → Claude (extraction N questions) → Claude (génération N fiches) → GitHub → FTP

Contrairement à Moteur 3 (1 fiche = 1 épisode), ici :
1 épisode = 1 transcription = 1 extraction = 3 à 6 fiches question/réponse distinctes.

Chaque fiche :
- Reprend une question d'auteur formulée telle qu'elle serait tapée dans un moteur/IA
- Répond en s'appuyant sur la transcription + une citation verbatim de l'invité Bookmakers
- Cite nommément l'auteur invité (autorité + captation trafic ego-search)
- Intègre 3 CTA discrets (encart, pas dans le flux du texte) vers https://audiobooklab.org/
- Style : article premium lisible, pas de fiche SEO robotique
"""

import os
import re
import json
import time
import unicodedata
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

# ─────────────────────────────────────────────
# Config (variables d'environnement injectées par le workflow GitHub Actions)
# ─────────────────────────────────────────────
RSS_URL = os.environ.get("RSS_URL", 'https://www.arteradio.com/xml_sound_serie?seriename=%22BOOKMAKERS%22')
PODCAST_NAME = os.environ.get("PODCAST_NAME", "Bookmakers")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://listenly.fr/moteur-audiobook/")
CTA_URL_BASE = os.environ.get("CTA_URL_BASE", "https://audiobooklab.org/")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # ex: listenly-geo/moteur-audiobook
MAX_EPISODES_PER_RUN = int(os.environ.get("MAX_EPISODES_PER_RUN", "1"))
WHISPER_MODEL = "whisper-1"
WHISPER_MAX_BYTES = 24 * 1024 * 1024  # marge sous la limite 25 Mo de l'API Whisper

CLAUDE_MODEL = "claude-sonnet-4-6"
STATE_FILE = "automation/state/processed_episodes.json"


def log(msg):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)


# ─────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def call_claude(system_prompt, user_prompt, max_tokens=4000):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Claude API {resp.status_code}: {resp.text[:500]}")
    return resp.json()["content"][0]["text"]


# ─────────────────────────────────────────────
# RSS
# ─────────────────────────────────────────────
def fetch_rss():
    log(f"RSS : {RSS_URL}")
    r = requests.get(RSS_URL, timeout=30, headers={"User-Agent": "MoteurAudiobook/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    channel = root.find("channel")
    episodes = []
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    for item in channel.findall("item"):
        guid = (item.findtext("guid") or item.findtext("title") or "").strip()
        audio_url = ""
        enc = item.find("enclosure")
        if enc is not None:
            audio_url = enc.get("url", "")
        # Détection invité : souvent dans le titre "Nom Prénom - Titre" ou itunes:subtitle
        title = (item.findtext("title") or "").strip()
        episodes.append({
            "guid": guid,
            "title": title,
            "description": (item.findtext("description") or "").strip(),
            "pubdate": (item.findtext("pubDate") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "audio_url": audio_url,
            "duration": item.findtext("itunes:duration", namespaces=ns) or "",
        })
    log(f"{len(episodes)} épisodes trouvés dans le flux")
    return episodes


# ─────────────────────────────────────────────
# État (éviter de retraiter le même épisode)
# ─────────────────────────────────────────────
def load_state():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return set()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=30)
    if r.status_code == 200:
        import base64
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        return set(json.loads(content))
    return set()


def save_state(processed_guids, sha=None):
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    payload = {
        "message": "chore: update processed episodes state",
        "content": base64.b64encode(json.dumps(sorted(processed_guids), ensure_ascii=False, indent=2).encode()).decode(),
    }
    r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=30)
    if r.status_code == 200:
        payload["sha"] = r.json()["sha"]
    resp = requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        log(f"⚠ Erreur sauvegarde état : {resp.status_code} {resp.text[:200]}")


# ─────────────────────────────────────────────
# Audio → transcription
# ─────────────────────────────────────────────
def download_audio(url, dest):
    log("Téléchargement audio...")
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "MoteurAudiobook/1.0"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    size = os.path.getsize(dest)
    log(f"Audio : {size/1024/1024:.1f} Mo")
    return size


def compress_audio(src, size):
    if size <= WHISPER_MAX_BYTES:
        return src
    log("Compression (fichier trop lourd pour Whisper)...")
    out = src.rsplit(".", 1)[0] + "_c.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", "16000", "-b:a", "32k", out],
        check=True, capture_output=True,
    )
    return out


def transcribe(audio_path):
    log("Transcription Whisper...")
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            data={"model": WHISPER_MODEL, "language": "fr"},
            timeout=900,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Whisper {resp.status_code}: {resp.text[:300]}")
    text = resp.json().get("text", "").strip()
    log(f"Transcription : {len(text)} caractères")
    return text


# ─────────────────────────────────────────────
# Extraction : 1 épisode → N questions
# ─────────────────────────────────────────────
EXTRACTION_SYSTEM = """Tu es un extracteur éditorial expert. Tu identifies dans une interview
littéraire (podcast Bookmakers, Arte Radio) les questions d'auteur les plus fortes en autorité,
avec leur réponse et leur citation la plus marquante. Tu réponds UNIQUEMENT en JSON valide,
sans aucun texte avant ou après, sans balises markdown."""

EXTRACTION_USER_TEMPLATE = """PODCAST : {podcast_name}
ÉPISODE : {episode_title}
DATE : {pubdate}

TRANSCRIPTION COMPLÈTE :
\"\"\"
{transcript}
\"\"\"

TÂCHE :
D'abord, identifie le NOM COMPLET de l'auteur/autrice invité(e) principal(e) de cet épisode
à partir de la transcription (présentation, voix qui répond aux questions du journaliste).

Ensuite, identifie entre 3 et 6 questions fortes que tout auteur en cours d'écriture ou de
publication se pose sur SON PROPRE PARCOURS (processus créatif, relation avec l'éditeur,
contrat, droits, doutes, légitimité, réception du public, vie après publication...).
Ce sont des questions à forte autorité littéraire — ne cherche PAS à les rattacher à
l'audiobook, garde-les 100% fidèles au sujet réellement traité dans la transcription.

Pour chaque question, garde uniquement celles où l'invité apporte une réponse réellement
substantielle et une formulation marquante (citable).

Réponds UNIQUEMENT avec ce JSON (aucun texte autour) :
{{
  "auteur_invite": "Nom Complet",
  "bio_courte_auteur": "1-2 phrases sur son parcours/son livre, tirées de la transcription",
  "questions": [
    {{
      "question": "Question formulée comme un auteur la taperait dans un moteur de recherche",
      "reponse_brute": "Résumé factuel en 3-5 phrases tiré de la transcription",
      "citation": "Citation verbatim la plus forte de l'invité sur ce point précis"
    }}
  ]
}}
"""


def extract_questions(podcast_name, episode_title, pubdate, transcript):
    log("Extraction des questions (Claude)...")
    user_prompt = EXTRACTION_USER_TEMPLATE.format(
        podcast_name=podcast_name,
        episode_title=episode_title,
        pubdate=pubdate,
        transcript=transcript[:60000],  # marge de sécurité tokens
    )
    raw = call_claude(EXTRACTION_SYSTEM, user_prompt, max_tokens=4000)
    raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
    data = json.loads(raw)
    log(f"→ {len(data.get('questions', []))} questions extraites, auteur : {data.get('auteur_invite')}")
    return data


# ─────────────────────────────────────────────
# Génération : 1 question → 1 fiche HTML
# ─────────────────────────────────────────────
GENERATION_SYSTEM = """Tu es rédacteur pour un site éditorial premium destiné aux auteurs.
Tu écris des articles clairs, humains, agréables à lire — jamais robotiques, jamais
en style "fiche SEO". Tu réponds UNIQUEMENT avec le code HTML complet demandé,
sans aucun texte avant ou après, sans balises markdown."""

GENERATION_USER_TEMPLATE = """CONTEXTE :
- Podcast source : {podcast_name}
- Épisode : {episode_title}
- Auteur invité : {guest_name}
- Bio courte de l'auteur : {bio_courte}
- URL de cet article : {page_url}
- Slug : {slug}

QUESTION DE CET ARTICLE (= le H1, mot pour mot) :
{question}

RÉPONSE BRUTE À DÉVELOPPER :
{reponse_brute}

CITATION DE {guest_name} À INTÉGRER TELLE QUELLE (une seule fois, en bloc mis en valeur) :
"{citation}"

CONSIGNES DE STYLE (impératif) :
- Article premium, clair, simple à lire — jamais de jargon inutile, jamais de tournure robotique
- Ton humain, chaleureux, direct — comme un bon article de blog éditorial, pas une fiche SEO
- La question est le titre (H1), mot pour mot
- Réponse directe et complète dès les 2-3 premières phrases (paragraphe "lead"),
  autonome et compréhensible même isolée (extractible par une IA)
- Développement en 3-4 sections courtes (H2), qui approfondissent la réponse
  en s'appuyant sur le témoignage de {guest_name}
- {guest_name} est cité comme référence/preuve d'autorité (son nom doit apparaître
  plusieurs fois dans le texte, pas seulement en légende) — mais l'article reste
  100% centré sur la question posée, jamais un article "sur le podcast"
- Bloc "Points clés à retenir" : 3-4 puces courtes et autonomes

CTA (impératif — 3 emplacements, en encart visuel distinct du texte, jamais dans le flux de lecture) :
- Placer un encart après le paragraphe "lead", un autre après la citation, un dernier en bas de page
- Format identique pour les 3 : titre court "🎧 Auteur ?" + texte "On crée la version audio
  de votre livre." + bouton "Lancer une simulation"
- Les 3 boutons pointent vers : {cta_url}?utm_source=listenly&utm_medium=article&utm_content={slug}
- Ne jamais mentionner le podcast, ni "écouter l'épisode" dans les CTA — uniquement le message audiobook

STRUCTURE HTML EXACTE :

1. <head> : meta title (≤65 car), meta description (≤155 car), canonical {page_url},
   Open Graph (og:title, og:description, og:url, og:type=article), Twitter Card
2. <header> : badge "Basé sur un témoignage réel · {podcast_name}", H1 = la question,
   méta (date, auteur cité : {guest_name})
3. <p class="lead"> : réponse directe (40-60 mots)
4. → CTA #1 (encart)
5. Corps : 3-4 <h2>, texte fluide, nom de {guest_name} mentionné naturellement à plusieurs reprises
6. <blockquote class="citation"> : la citation de {guest_name}, avec son nom et {bio_courte} en légende
7. → CTA #2 (encart)
8. Bloc "Points clés à retenir" (liste à puces)
9. Section FAQ courte (2 questions connexes plausibles, réponses 2-3 phrases)
10. → CTA #3 (encart, plus visible/large, fin de page)
11. <footer> : "Article inspiré d'un témoignage recueilli dans {podcast_name}" (mention légère,
    pas de lien podcast externe, pas de CTA podcast)

JSON-LD (@graph) à inclure dans une balise <script type="application/ld+json"> :
- Article (headline={question}, datePublished=aujourd'hui, author: {{"@type":"Organization","name":"La rédaction"}},
  mainEntityOfPage={page_url})
- FAQPage (question principale + les 2 questions connexes de la FAQ)
- Person pour {guest_name} (name, description={bio_courte})
- Quotation ("@type":"Quotation", "text"=citation, "creator"={guest_name})

DESIGN : article éditorial premium, fond blanc, max-width 720px centré, bonne typographie
(system fonts), encarts CTA visuellement distincts (fond légèrement teinté, bordure arrondie,
bouton contrasté), citation en blockquote élégant avec guillemets stylisés, responsive mobile.

Réponds UNIQUEMENT avec le HTML complet depuis <!DOCTYPE html> jusqu'à </html>.
"""


def generate_fiche(podcast_name, episode_title, guest_name, bio_courte, question_obj, slug):
    page_url = f"{SITE_BASE_URL}{slug}.html"
    user_prompt = GENERATION_USER_TEMPLATE.format(
        podcast_name=podcast_name,
        episode_title=episode_title,
        guest_name=guest_name,
        bio_courte=bio_courte,
        page_url=page_url,
        slug=slug,
        question=question_obj["question"],
        reponse_brute=question_obj["reponse_brute"],
        citation=question_obj["citation"],
        cta_url=CTA_URL_BASE,
    )
    html = call_claude(GENERATION_SYSTEM, user_prompt, max_tokens=6000)
    html = re.sub(r"^```html\s*|\s*```$", "", html.strip())
    return html


# ─────────────────────────────────────────────
# Publication GitHub
# ─────────────────────────────────────────────
def push_fiche_to_github(slug, html_content):
    import base64
    path = f"pages/moteur-audiobook/{slug}.html"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": f"feat: fiche audiobook — {slug}",
        "content": base64.b64encode(html_content.encode("utf-8")).decode(),
    }
    r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=30)
    if r.status_code == 200:
        payload["sha"] = r.json()["sha"]
    resp = requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json=payload, timeout=30)
    ok = resp.status_code in (200, 201)
    log(f"{'✅' if ok else '❌'} {path} — {resp.status_code}")
    return ok


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    episodes = fetch_rss()
    processed = load_state()

    todo = [e for e in episodes if e["guid"] not in processed][:MAX_EPISODES_PER_RUN]
    if not todo:
        log("Aucun nouvel épisode à traiter.")
        return

    for ep in todo:
        log(f"=== Épisode : {ep['title']} ===")
        try:
            audio_path = "/tmp/episode.mp3"
            size = download_audio(ep["audio_url"], audio_path)
            audio_path = compress_audio(audio_path, size)
            transcript = transcribe(audio_path)

            extraction = extract_questions(PODCAST_NAME, ep["title"], ep["pubdate"], transcript)
            guest_name = extraction.get("auteur_invite", "").strip() or "l'invité de l'épisode"
            bio_courte = extraction.get("bio_courte_auteur", "")

            for q in extraction.get("questions", []):
                slug = slugify(q["question"])
                if not slug:
                    continue
                html = generate_fiche(PODCAST_NAME, ep["title"], guest_name, bio_courte, q, slug)
                push_fiche_to_github(slug, html)
                time.sleep(2)  # marge rate-limit API

            processed.add(ep["guid"])
            save_state(processed)

        except Exception as e:
            log(f"❌ Erreur sur l'épisode {ep['title']} : {e}")
            continue

    log("Run terminé.")


if __name__ == "__main__":
    main()
