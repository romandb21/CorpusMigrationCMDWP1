import requests
import json
import os
import csv
import re
import shutil
from requests.auth import HTTPBasicAuth
from datetime import datetime
from pathlib import Path


# ======================================================================
# CONFIGURATION
# ======================================================================

CREDENTIALS_FILE = Path(__file__).parent / "Piste_Credentials.json"
with open(CREDENTIALS_FILE, "r") as f:
    creds = json.load(f)
    CLIENT_ID = creds["CLIENT_ID"]
    CLIENT_SECRET = creds["CLIENT_SECRET"]

TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CHECKPOINT_DIR = DATA_DIR / "checkpoints"


# ======================================================================
# UTILITAIRES
# ======================================================================

def write_json_atomic(file_path, data):
    """Écrit un JSON de manière atomique pour éviter les fichiers tronqués."""
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(file_path)


# ======================================================================
# AUTHENTIFICATION
# ======================================================================

def get_access_token():
    """Récupère un token OAuth valide pour l'API Legifrance."""
    print("\n🔑 Récupération du token OAuth...")
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "openid"},
        auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
        timeout=15
    )
    if response.status_code != 200:
        raise Exception(f"Erreur OAuth ({response.status_code}): {response.text}")
    token = response.json()["access_token"]
    print("✅ Token récupéré avec succès\n")
    return token


# ======================================================================
# CHECKPOINT PAR FICHIERS INDIVIDUELS
# ======================================================================

def save_checkpoint_debat(debat, index):
    """Sauvegarde un débat individuel dans son propre fichier."""
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    file = CHECKPOINT_DIR / f"debat_{index:05d}.json"
    write_json_atomic(file, debat)


def load_checkpoint_debats():
    """
    Recharge tous les débats sauvegardés individuellement.
    
    Returns:
        Tuple (debats: list, last_index: int)
    """
    if not CHECKPOINT_DIR.exists():
        return [], 0
    files = sorted(CHECKPOINT_DIR.glob("debat_*.json"))
    if not files:
        return [], 0
    debats = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                debats.append(json.load(fp))
        except json.JSONDecodeError:
            print(f"⚠️  Fichier checkpoint corrompu ignoré: {f.name}")
    last_index = int(files[-1].stem.split("_")[1])
    print(f"   {len(debats)} débats rechargés (dernier index: {last_index})")
    return debats, last_index


def clear_checkpoints():
    """Supprime le dossier de checkpoints une fois l'extraction terminée."""
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
        print("\n🗑️  Checkpoints individuels supprimés")


# ======================================================================
# RÉCUPÉRATION DES DÉBATS
# ======================================================================

def get_debats_list(token, start_date="01/01/2015", end_date="31/12/2025",
                    page_size=50, type_assemblee=None):
    """
    Récupère la liste des débats parlementaires.

    Args:
        token: Token OAuth
        start_date: Date de début (format DD/MM/YYYY)
        end_date: Date de fin (format DD/MM/YYYY)
        page_size: Nombre de résultats par page
        type_assemblee: "AN", "SE", ou None pour tous

    Returns:
        Liste des débats avec leurs métadonnées
    """
    print(f"📜 Récupération des débats parlementaires ({start_date} - {end_date})...")
    url = f"{BASE_URL}/list/debatsParlementaires"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    all_debats = []
    page = 1

    while True:
        payload = {
            "dateParution": f"{start_date} > {end_date}",
            "pageNumber": page,
            "pageSize": page_size,
            "sortValue": "DEBAT_PARLEMENTAIRE_DESC"
        }
        if type_assemblee:
            payload["typesPublication"] = type_assemblee

        print(f"   Page {page}...", end=" ")
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            print(f"\nErreur API ({response.status_code}): {response.text}")
            break

        data = response.json()
        results = data.get("results", [])
        print(f"{len(results)} débats trouvés")

        if not results:
            break

        all_debats.extend(results)

        if len(results) < page_size:
            break

        page += 1

    print(f"✅ Total: {len(all_debats)} débats récupérés\n")
    return all_debats


def get_debat_details(token, debat_id):
    """
    Récupère le détail complet d'un débat incluant le contenu textuel.

    Args:
        token: Token OAuth
        debat_id: ID du débat (ex: "AN_2020-090.pdf")

    Returns:
        Dictionnaire avec le contenu du débat, ou None en cas d'erreur
    """
    url = f"{BASE_URL}/consult/debat"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {"id": debat_id}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "debat" in data and data["debat"] is not None:
                return data["debat"]
            else:
                print(f"      ⚠️  Réponse vide pour {debat_id}")
                return None
        else:
            print(f"      ⚠️  Erreur {response.status_code} pour {debat_id}")
            return None

    except requests.exceptions.Timeout:
        print(f"      ⚠️  Timeout pour {debat_id} (>30s)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"      ⚠️  Erreur réseau pour {debat_id}: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        print(f"      ⚠️  Réponse JSON invalide pour {debat_id}: {str(e)}")
        return None


# ======================================================================
# GESTION DES DÉBATS ÉCHOUÉS
# ======================================================================

def load_failed_debats():
    """Charge la liste des débats ayant échoué lors des tentatives précédentes."""
    failed_file = DATA_DIR / "failed_debats.json"
    if failed_file.exists():
        with open(failed_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_failed_debats(failed_list):
    """Sauvegarde la liste des débats ayant échoué."""
    failed_file = DATA_DIR / "failed_debats.json"
    write_json_atomic(failed_file, failed_list)


def retry_failed_debats(token, enriched_debats):
    """
    Retry les débats qui ont échoué lors des tentatives précédentes.
    Met à jour le checkpoint individuel du débat si récupéré avec succès.

    Args:
        token: Token OAuth
        enriched_debats: Liste des débats déjà enrichis (modifiée en place)

    Returns:
        Tuple (enriched_debats, failed_debats_restants)
    """
    failed_debats = load_failed_debats()
    if not failed_debats:
        return enriched_debats, []

    print(f"\n🔄 Retry des {len(failed_debats)} débats échoués précédents...\n")
    updated_failed = []

    for item in failed_debats:
        debat_id = item.get("attachmentUrl") or item.get("id")
        original_index = item.get("index")
        print(f"   ↻ {debat_id}...", end=" ")

        details = get_debat_details(token, debat_id)

        if details and details.get("attachment"):
            for d in enriched_debats:
                if d.get("attachmentUrl") == debat_id or d.get("id") == debat_id:
                    content = details.get("attachment", {}).get("content", "")
                    try:
                        if content and "\u00c3" in content:
                            content = content.encode('latin1').decode('utf-8')
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        pass
                    d["attachment"] = details.get("attachment")
                    # Mettre à jour le checkpoint individuel
                    if original_index:
                        save_checkpoint_debat(d, original_index)
                    print(f"✓ RÉCUPÉRÉ ({len(content):,} caractères)")
                    break
        else:
            print("✗ Toujours échoué")
            updated_failed.append(item)

    save_failed_debats(updated_failed)

    if updated_failed:
        print(f"\n⚠️  {len(updated_failed)} débats restent en attente de retry\n")
    else:
        print(f"\n✅ Tous les débats échoués ont été récupérés!\n")

    return enriched_debats, updated_failed


# ======================================================================
# ENRICHISSEMENT
# ======================================================================

def enrich_debats_with_content(token, debats_list, max_debats=None):
    """
    Enrichit la liste des débats avec leur contenu complet.
    Sauvegarde chaque débat dans un fichier individuel dès sa récupération.
    Enregistre les débats échoués pour retry automatique au prochain lancement.

    Args:
        token: Token OAuth
        debats_list: Liste des débats (métadonnées)
        max_debats: Nombre maximum de débats à enrichir (None = tous)

    Returns:
        Liste des débats enrichis avec le contenu
    """
    # Reprise depuis les checkpoints individuels
    enriched_debats, start_index = load_checkpoint_debats()
    if start_index > 0:
        print(f"\n📂 Reprise à partir du débat #{start_index + 1}")
        enriched_debats, _ = retry_failed_debats(token, enriched_debats)

    print(f"\n📝 Récupération du contenu des débats...")
    total = len(debats_list) if max_debats is None else min(max_debats, len(debats_list))
    failed_debats = []

    for i, debat in enumerate(debats_list[start_index:total], start=start_index + 1):
        debat_id = debat.get("attachmentUrl") or debat.get("id")

        if not debat_id:
            print(f"   [{i}/{total}] ⚠️  Débat sans ID, ignoré")
            enriched_debats.append(debat)
            save_checkpoint_debat(debat, i)
            continue

        print(f"   [{i}/{total}] {debat_id}...", end=" ")

        details = get_debat_details(token, debat_id)

        if details and details.get("attachment"):
            debat_enriched = {**debat, **details}

            content = details.get("attachment", {}).get("content", "")
            try:
                if content and "\u00c3" in content:
                    content = content.encode('latin1').decode('utf-8')
                    debat_enriched["attachment"]["content"] = content
            except (UnicodeDecodeError, UnicodeEncodeError) as e:
                print(f"      ⚠️  Erreur encodage pour {debat_id}: {str(e)}")

            enriched_debats.append(debat_enriched)
            save_checkpoint_debat(debat_enriched, i)
            print(f"✓ ({len(content):,} caractères)")

        else:
            enriched_debats.append(debat)
            save_checkpoint_debat(debat, i)
            print("✗ Pas de contenu")
            failed_debats.append({
                "index": i,
                "attachmentUrl": debat.get("attachmentUrl"),
                "id": debat.get("id"),
                "dateSeance": debat.get("dateSeance")
            })

    # Gestion des échoués
    if failed_debats:
        save_failed_debats(failed_debats)
        print(f"\n⚠️  {len(failed_debats)} débats échoués enregistrés dans failed_debats.json")
        print("   Relancez le script pour retry automatiquement\n")
    else:
        failed_file = DATA_DIR / "failed_debats.json"
        if failed_file.exists():
            failed_file.unlink()

    print(f"\n✅ {len(enriched_debats)} débats enrichis\n")
    return enriched_debats


# ======================================================================
# PARSING DU CONTENU
# ======================================================================

def parse_content(content):
    """
    Extrait les métadonnées structurées depuis le contenu brut d'un débat.

    Returns:
        dict avec:
            - titre_seance: str
            - sujets: list[str]
            - intervenants: list[dict] dédupliqués avec uid/str/pos
    """
    if not content:
        return {"titre_seance": None, "sujets": [], "intervenants": []}

    # ------------------------------------------------------------------
    # 1. TITRE DE LA SÉANCE
    # ------------------------------------------------------------------
    titre_seance = None
    titre_match = re.search(
        r'[SséÉ]éance du\s+(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)'
        r'\s+\d{1,2}\s+\w+\s+\d{4}',
        content,
        re.IGNORECASE
    )
    if titre_match:
        titre_seance = titre_match.group(0).strip()

    # ------------------------------------------------------------------
    # 2. SUJETS / ORDRE DU JOUR
    # Repère les titres en majuscules isolés sur leur ligne
    # ------------------------------------------------------------------
    sujets = []
    seen_sujets = set()
    for line in content.splitlines():
        line = line.strip()
        if (
            line
            and line == line.upper()
            and 10 <= len(line) <= 120
            and not re.match(r'^\d+\s*$', line)
            and not re.match(r'^[A-Z]{1,3}\s*$', line)
        ):
            if line not in seen_sujets:
                sujets.append(line)
                seen_sujets.add(line)

    # ------------------------------------------------------------------
    # 3. INTERVENANTS
    # Pattern: "M./Mme Prénom(s) Nom, fonction." ou "M./Mme Prénom(s) Nom."
    # ------------------------------------------------------------------
    intervenants = []
    seen_noms = set()

    pattern_intervenant = re.compile(
        r'\b(M\.|Mme)\s+'
        r'([A-ZÀ-Ÿa-zà-ÿ\-]+(?:\s+[A-ZÀ-Ÿa-zà-ÿ\-]+)*)'
        r'(?:,\s*([^.(][^.]{3,80}?))?'
        r'\.',
        re.UNICODE
    )

    for match in pattern_intervenant.finditer(content):
        nom_complet = match.group(2).strip()
        fonction = match.group(3).strip() if match.group(3) else None

        if not nom_complet or len(nom_complet) < 3:
            continue
        if nom_complet.lower() in {"la présidente", "le président", "la ministre", "le ministre"}:
            continue

        if nom_complet not in seen_noms:
            seen_noms.add(nom_complet)
            intervenants.append({
                "uid": None,
                "str": nom_complet,
                "pos": fonction
            })

    return {
        "titre_seance": titre_seance,
        "sujets": sujets,
        "intervenants": intervenants
    }


# ======================================================================
# SAUVEGARDE
# ======================================================================

def save_data(debats_list, start_date, end_date):
    """Sauvegarde les données en deux fichiers: liste JSON (métadonnées) et corpus CSV (contenu)."""
    period = f"{start_date[-4:]}_{end_date[-4:]}"

    # 1. Liste JSON (métadonnées sans contenu)
    liste_file = DATA_DIR / f"liste_debats_{period}.json"
    debats_metadata = []
    for debat in debats_list:
        metadata = {k: v for k, v in debat.items() if k != "attachment"}
        if debat.get("attachment"):
            attachment_info = {k: v for k, v in debat["attachment"].items() if k != "content"}
            metadata["attachment_info"] = attachment_info
        debats_metadata.append(metadata)

    write_json_atomic(liste_file, debats_metadata)
    print(f"💾 Liste des débats sauvegardée: {liste_file}")

    # 2. Corpus CSV avec contenu complet + colonnes parsées
    if debats_list:
        corpus_file = DATA_DIR / f"corpus_debats_{period}.csv"
        keys = [
            "id", "attachmentUrl", "dateSeance", "dateParution", "anneeParution",
            "typeAssemblee", "origine", "legislature", "session", "nomSession",
            "pathToFile", "attachment_title", "attachment_name",
            "attachment_content_length", "attachment_content_type",
            "titre_seance", "sujets", "intervenants", "content"
        ]

        csv_data = []
        for debat in debats_list:
            attachment = debat.get("attachment") or {}
            content = attachment.get("content", "")
            parsed = parse_content(content)

            csv_data.append({
                "id": debat.get("id"),
                "attachmentUrl": debat.get("attachmentUrl"),
                "dateSeance": debat.get("dateSeance"),
                "dateParution": debat.get("dateParution"),
                "anneeParution": debat.get("anneeParution"),
                "typeAssemblee": debat.get("typeAssemblee"),
                "origine": debat.get("origine"),
                "legislature": debat.get("legislature"),
                "session": debat.get("session"),
                "nomSession": debat.get("nomSession"),
                "pathToFile": debat.get("pathToFile"),
                "attachment_title": attachment.get("title"),
                "attachment_name": attachment.get("name"),
                "attachment_content_length": attachment.get("content_length"),
                "attachment_content_type": attachment.get("content_type"),
                "titre_seance": parsed["titre_seance"],
                "sujets": json.dumps(parsed["sujets"], ensure_ascii=False),
                "intervenants": json.dumps(parsed["intervenants"], ensure_ascii=False),
                "content": content
            })

        with open(corpus_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(csv_data)

        print(f"✅ Corpus exporté: {corpus_file}")
        print(f"   {len(csv_data)} débats avec contenu")


# ======================================================================
# MAIN
# ======================================================================

if __name__ == "__main__":
    START_DATE = "01/01/2015"
    END_DATE = "31/12/2025"

    # ------------------------------------------------------------------
    # MODE REPARSE : génère le CSV depuis les checkpoints existants,
    # sans appel API. Lancer avec : $env:REPARSE_ONLY="1"; python script.py
    # ------------------------------------------------------------------
    if os.getenv("REPARSE_ONLY") == "1":
        print("=" * 70)
        print(" MODE REPARSE - Génération CSV depuis checkpoints existants")
        print("=" * 70)

        debats_list, _ = load_checkpoint_debats()

        if debats_list:
            print(f"\n✅ {len(debats_list)} débats chargés")
            save_data(debats_list, START_DATE, END_DATE)
            print("\n" + "=" * 70)
            print(f" TERMINÉ - CSV généré avec {len(debats_list)} débats")
        else:
            print("❌ Aucun checkpoint trouvé dans data/checkpoints/")
        print("=" * 70)

    # ------------------------------------------------------------------
    # MODE NORMAL : extraction complète depuis l'API
    # ------------------------------------------------------------------
    else:
        TYPE_ASSEMBLEE = None  # "AN", "SE", ou None pour tous

        print("=" * 70)
        print(" EXTRACTION DÉBATS PARLEMENTAIRES - LEGIFRANCE")
        print("=" * 70)

        token = get_access_token()
        debats_list = get_debats_list(token, START_DATE, END_DATE, type_assemblee=TYPE_ASSEMBLEE)

        if not debats_list:
            print("❌ Aucun débat récupéré. Vérifiez les paramètres de recherche.")
        else:
            # MAX_DEBATS: None = tous, ou un entier pour limiter (ex: 10 pour tester)
            MAX_DEBATS = None
            debats_enriched = enrich_debats_with_content(token, debats_list, max_debats=MAX_DEBATS)
            save_data(debats_enriched, START_DATE, END_DATE)

            # Nettoyage des checkpoints après succès complet
            clear_checkpoints()

        print("\n" + "=" * 70)
        print(f" TERMINÉ - {len(debats_list)} débats récupérés")
        print("=" * 70)