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
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://audiobooklab.fr/blog-audiobook/")
CTA_URL_BASE = os.environ.get("CTA_URL_BASE", "https://audiobooklab.org/")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Migration cout du 02/09/2026 (alignee sur podcast-btb) : Groq remplace OpenAI Whisper par
# defaut (~9x moins cher, qualite quasi identique) ; OPENAI_API_KEY reste supporte en fallback
# via TRANSCRIPTION_PROVIDER=openai. OPENAI_API_KEY n'est donc plus obligatoire (avant : acces
# direct au dict qui plantait si absente).
TRANSCRIPTION_PROVIDER = os.environ.get("TRANSCRIPTION_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # ex: listenly-geo/moteur-audiobook
MAX_EPISODES_PER_RUN = int(os.environ.get("MAX_EPISODES_PER_RUN", "2"))

if TRANSCRIPTION_PROVIDER == "groq":
    TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
    TRANSCRIPTION_API_KEY = GROQ_API_KEY
else:
    TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
    TRANSCRIPTION_MODEL = "whisper-1"
    TRANSCRIPTION_API_KEY = OPENAI_API_KEY

WHISPER_MAX_BYTES = 24 * 1024 * 1024  # marge sous la limite 25 Mo de l'API Whisper/Groq

# Migration cout du 02/09/2026 : Sonnet -> Haiku, alignee sur podcast-btb (~7x moins cher).
# ATTENTION (signale a Etienne) : contrairement au moteur B2B (fiches factuelles), ce moteur
# genere du contenu editorial soigne ("style article premium, pas de fiche SEO robotique") --
# tache differente, non testee avec Haiku. Recommande de valider la qualite sur quelques
# fiches reelles avant de faire confiance a l'aveugle (voir echange avec Claude du 02/09/2026).
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
STATE_FILE = "automation/state/processed_episodes.json"
# Stock de questions en attente de publication (02/09/2026) : le mining (transcription +
# extraction) reste groupe par episode comme avant, mais la PUBLICATION passe a 1 fiche/jour
# -- meme principe que le Moteur Trafic B2B (podcast-btb). Cout total identique (chaque fiche
# a deja son propre appel Claude, seul le rythme de publication change), juste etale dans le
# temps plutot que publie d'un coup (3-6 fiches simultanees par episode mine).
STOCK_FILE = "automation/state/question_stock.json"


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
# Le script tourne dans le checkout git (voir workflow) : on lit/écrit un
# fichier local, c'est le step "git commit & push" du workflow qui le persiste.
# ─────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_state(processed_guids):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(processed_guids), f, ensure_ascii=False, indent=2)


def load_stock():
    if os.path.exists(STOCK_FILE):
        with open(STOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_stock(stock):
    os.makedirs(os.path.dirname(STOCK_FILE), exist_ok=True)
    with open(STOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(stock, f, ensure_ascii=False, indent=2)


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
    log(f"Transcription {TRANSCRIPTION_PROVIDER}...")
    with open(audio_path, "rb") as f:
        resp = requests.post(
            TRANSCRIPTION_URL,
            headers={
                "Authorization": f"Bearer {TRANSCRIPTION_API_KEY}",
                # Fix connu (podcast-btb, 01/09/2026) : Groq/Cloudflare rejette les requetes
                # sans User-Agent explicite (erreur Cloudflare 1010) -- Python/requests envoie
                # un User-Agent par defaut generique, souvent bloque.
                "User-Agent": "Mozilla/5.0 (compatible; ListenlyGEO/1.0; +https://listenly.fr)",
            },
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            data={"model": TRANSCRIPTION_MODEL, "language": "fr"},
            timeout=900,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Transcription erreur ({TRANSCRIPTION_PROVIDER}) {resp.status_code}: {resp.text[:300]}")
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

Ensuite, identifie entre 4 et 6 questions fortes (privilégie la fourchette haute si
l'épisode le permet, mais ne force JAMAIS une question faible juste pour atteindre
un quota) que tout auteur en cours d'écriture ou de publication se pose sur SON
PROPRE PARCOURS (processus créatif, relation avec l'éditeur, contrat, droits,
doutes, légitimité, réception du public, vie après publication...).
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
   <meta name="robots" content="index, follow, max-image-preview:large">,
   Open Graph (og:title, og:description, og:url, og:type=article), Twitter Card
2. <header> : badge "Basé sur un témoignage réel · {podcast_name}", H1 = la question,
   méta (date, auteur cité : {guest_name})
2bis. Juste après le header, un petit bandeau discret (texte gris, petite taille) :
   "Article lisible par les modèles IA : ChatGPT · Perplexity · Gemini · Claude · Copilot"
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

    # Fix du 02/09/2026 : Claude n'a pas conscience de la date reelle du jour malgre la
    # consigne "datePublished=aujourd'hui" -- il reprenait souvent la date de diffusion
    # originale de l'episode (visible dans le prompt), faussant tout l'historique du
    # dashboard (ex: "derniere generation" affichait juillet 2025 alors que le run venait
    # de tourner). Injection deterministe (Python) de la vraie date de generation.
    today_iso = datetime.now().strftime("%Y-%m-%d")
    html = re.sub(r'("datePublished"\s*:\s*")[^"]*(")', r"\g<1>" + today_iso + r"\g<2>", html)

    return html


# ─────────────────────────────────────────────
# Publication locale (le dossier est ensuite committé par git puis déployé
# par FTP-Deploy-Action dans le workflow — voir moteur-audiobook.yml)
# ─────────────────────────────────────────────
FICHES_DIR = "pages/moteur-audiobook"


def write_fiche_locally(slug, html_content):
    os.makedirs(FICHES_DIR, exist_ok=True)
    path = os.path.join(FICHES_DIR, f"{slug}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    log(f"✅ Fiche écrite : {path}")
    return path


# ─────────────────────────────────────────────
# Sitemap.xml — régénéré à chaque run à partir de toutes les fiches présentes
# dans le dossier (source de vérité = ce qui est réellement déployé).
# ─────────────────────────────────────────────
def generate_sitemap():
    if not os.path.isdir(FICHES_DIR):
        log("⚠ Aucun dossier de fiches, sitemap non généré.")
        return

    fiche_files = sorted(f for f in os.listdir(FICHES_DIR) if f.endswith(".html"))
    today = datetime.utcnow().strftime("%Y-%m-%d")

    urls = []
    for filename in fiche_files:
        slug = filename[:-5]
        loc = f"{SITE_BASE_URL.rstrip('/')}/{slug}.html"
        mtime = datetime.utcfromtimestamp(
            os.path.getmtime(os.path.join(FICHES_DIR, filename))
        ).strftime("%Y-%m-%d")
        urls.append(
            f"  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{mtime}</lastmod>\n"
            f"    <changefreq>monthly</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n"
        "</urlset>\n"
    )

    sitemap_path = os.path.join(FICHES_DIR, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    log(f"✅ Sitemap régénéré ({len(fiche_files)} fiches) : {sitemap_path}")

    # robots.txt local dédié au sous-dossier — complète (sans écraser) le
    # robots.txt racine du site, qui est géré par WordPress séparément.
    robots_path = os.path.join(FICHES_DIR, "robots-fragment.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(
            "# Fragment à ajouter au robots.txt racine du site (audiobooklab.fr/robots.txt) :\n"
            "# User-agent: *\n"
            "# Allow: /blog-audiobook/\n"
            f"# Sitemap: {SITE_BASE_URL.rstrip('/')}/sitemap.xml\n"
        )


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    stock = load_stock()

    if stock:
        # Stock disponible : on publie UNE seule fiche aujourd'hui, pas de minage necessaire.
        item = stock.pop(0)
        log(f"Publication depuis le stock ({len(stock)} restante(s) apres celle-ci) : {item['question']['question'][:70]}...")
        html = generate_fiche(
            PODCAST_NAME, item["episode_title"], item["guest_name"], item["bio_courte"],
            item["question"], item["slug"],
        )
        write_fiche_locally(item["slug"], html)
        save_stock(stock)
        generate_sitemap()
        log("Run terminé (1 fiche publiée depuis le stock).")
        return

    # Stock vide : miner de(s) nouvel(aux) episode(s).
    episodes = fetch_rss()
    processed = load_state()

    todo = [e for e in episodes if e["guid"] not in processed][:MAX_EPISODES_PER_RUN]
    if not todo:
        log("Aucun nouvel épisode à traiter — redéploiement des fiches existantes uniquement.")
        # Fix du 02/09/2026 : ce cas restait invisible (le run affichait juste succes vert,
        # comme un run normal) -- personne ne l'a remarque pendant 14 mois. Desormais, une
        # annotation warning apparait directement sur la page du run GitHub Actions (triangle
        # jaune), et un resume persistant est ecrit dans l'onglet Summary du run.
        print(f"::warning::Aucun nouvel episode trouve dans le flux RSS ({len(episodes)} episodes vus, "
              f"{len(processed)} deja traites). Si ca persiste plusieurs semaines, verifier si le podcast "
              f"source publie encore de nouveaux episodes, ou si le flux RSS a change de format.")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(
                    f"## ⚠️ Aucun nouvel épisode traité\n\n"
                    f"- Épisodes vus dans le flux RSS : {len(episodes)}\n"
                    f"- Déjà traités (historique) : {len(processed)}\n"
                    f"- Ce run n'a donc rien miné de nouveau — fiches existantes redéployées uniquement.\n\n"
                    f"Si ce message revient plusieurs semaines de suite, vérifier si le podcast source "
                    f"publie encore de nouveaux épisodes.\n"
                )
        generate_sitemap()
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

            new_items = []
            for q in extraction.get("questions", []):
                slug = slugify(q["question"])
                if not slug:
                    continue
                new_items.append({
                    "episode_title": ep["title"],
                    "guest_name": guest_name,
                    "bio_courte": bio_courte,
                    "question": q,
                    "slug": slug,
                })

            processed.add(ep["guid"])
            save_state(processed)

            if new_items:
                # Publie IMMEDIATEMENT la 1ere fiche de ce lot fraichement mine (garde le
                # rythme 1/jour meme le jour du minage) ; le reste rejoint le stock pour les
                # jours suivants.
                first = new_items.pop(0)
                log(f"Publication immédiate (1ère fiche de l'épisode) : {first['question']['question'][:70]}...")
                html = generate_fiche(
                    PODCAST_NAME, first["episode_title"], first["guest_name"], first["bio_courte"],
                    first["question"], first["slug"],
                )
                write_fiche_locally(first["slug"], html)
                stock.extend(new_items)

        except Exception as e:
            log(f"❌ Erreur sur l'épisode {ep['title']} : {e}")
            continue

    save_stock(stock)
    generate_sitemap()
    log(f"Run terminé ({len(stock)} question(s) en stock pour les prochains jours).")


if __name__ == "__main__":
    main()
