import requests
import json
import os
from requests.auth import HTTPBasicAuth
from datetime import datetime
from pathlib import Path


# ======================================================================
# CONFIGURATION
# ======================================================================

# Chargement des identifiants depuis le fichier JSON
CREDENTIALS_FILE = Path(__file__).parent / "Piste_Credentials.json"
with open(CREDENTIALS_FILE, "r") as f:
    creds = json.load(f)
    CLIENT_ID = creds["CLIENT_ID"]
    CLIENT_SECRET = creds["CLIENT_SECRET"]

# URLs de production
TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
BASE_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

# Dossiers de sortie
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ======================================================================
# FONCTIONS D'AUTHENTIFICATION
# ======================================================================

def get_access_token():
    """Récupère un token OAuth valide pour l'API Legifrance"""
    print("\n🔑 Récupération du token OAuth...")
    
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "openid"},
        auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
        timeout=15
    )
    
    if response.status_code != 200:
        raise Exception(f"❌ Erreur OAuth ({response.status_code}): {response.text}")
    
    token = response.json()["access_token"]
    print("✅ Token récupéré avec succès\n")
    return token


# ======================================================================
# FONCTIONS DE RÉCUPÉRATION DES LOIS
# ======================================================================

def get_lois_list(token, start_date="2015-01-01", end_date="2025-12-31", page_size=50):
    """
    Récupère la liste des lois entre deux dates
    
    Args:
        token: Token OAuth
        start_date: Date de début (format YYYY-MM-DD)
        end_date: Date de fin (format YYYY-MM-DD)
        page_size: Nombre de résultats par page
    
    Returns:
        Liste des lois avec leurs métadonnées
    """
    print(f"📜 Récupération des lois de {start_date} à {end_date}...")
    
    url = f"{BASE_URL}/list/loda"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    all_lois = []
    page = 1
    
    while True:
        payload = {
            "sort": "PUBLICATION_DATE_ASC",
            "legalStatus": ["VIGUEUR", "ABROGE", "VIGUEUR_DIFF"],
            "pageNumber": page,
            "pageSize": page_size,
            "natures": ["LOI"],
            "signatureDate": {"start": start_date, "end": end_date},
            "publicationDate": {"start": start_date, "end": end_date}
        }
        
        print(f"   Page {page}...", end=" ")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"\n❌ Erreur API ({response.status_code}): {response.text}")
            break
        
        data = response.json()
        items = data.get("results") or data.get("items") or data.get("resultList") or []
        
        print(f"{len(items)} lois trouvées")
        
        if not items:
            break
        
        all_lois.extend(items)
        
        if len(items) < page_size:
            break
        
        page += 1
    
    print(f"✅ Total: {len(all_lois)} lois récupérées\n")
    return all_lois


def get_loi_details(token, loi_id, cid=None):
    """
    Récupère le détail d'une loi et ses articles
    
    Args:
        token: Token OAuth
        loi_id: ID de la loi (LEGITEXT...)
        cid: CID de la loi (JORFTEXT...) si disponible
    
    Returns:
        Détails de la loi avec ses articles
    """
    url = f"{BASE_URL}/consult/loda"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Test avec différents formats
    payloads_to_try = [
        {"textId": loi_id},  # Format 1: textId avec LEGITEXT
        {"textId": cid} if cid else None,  # Format 2: textId avec JORFTEXT
        {"id": loi_id},  # Format 3: id avec LEGITEXT
        {"cid": cid} if cid else None,  # Format 4: cid avec JORFTEXT
    ]
    
    for i, payload in enumerate([p for p in payloads_to_try if p], 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            
            # Si première tentative échoue, afficher l'erreur
            if i == 1:
                try:
                    error_detail = response.json()
                    print(f"⚠️  Erreur {response.status_code}: {error_detail.get('message', response.text[:100])}")
                except:
                    print(f"⚠️  Erreur {response.status_code}: {response.text[:100]}")
        
        except Exception as e:
            if i == 1:
                print(f"⚠️  Exception: {str(e)[:100]}")
            continue
    
    return None


# ======================================================================
# FONCTIONS DE CONSTRUCTION DU CORPUS
# ======================================================================

def extract_articles_metadata(loi_details, loi_metadata):
    """
    Extrait les métadonnées des articles d'une loi
    
    Args:
        loi_details: Détails complets de la loi
        loi_metadata: Métadonnées de base de la loi
    
    Returns:
        Liste d'articles avec métadonnées
    """
    articles = []
    
    if not loi_details:
        return articles
    
    # Navigation dans la structure (peut varier selon la réponse API)
    text = loi_details.get("text") or loi_details
    sections = text.get("sections") or text.get("articles") or []
    
    def extract_from_section(section, parent_title=""):
        """Fonction récursive pour extraire les articles"""
        for article in section.get("articles", []):
            article_data = {
                "loi_id": loi_metadata.get("id"),
                "loi_titre": loi_metadata.get("title"),
                "loi_num": loi_metadata.get("num"),
                "loi_date_signature": loi_metadata.get("dateSignature"),
                "loi_date_publication": loi_metadata.get("datePubli"),
                "article_id": article.get("id"),
                "article_num": article.get("num"),
                "article_titre": article.get("title"),
                "section": parent_title,
                "contenu": article.get("content") or article.get("htmlContent") or "",
                "etat": article.get("etat"),
                "date_debut": article.get("dateDebut"),
                "date_fin": article.get("dateFin")
            }
            articles.append(article_data)
        
        # Traitement récursif des sous-sections
        for subsection in section.get("sections", []):
            section_title = subsection.get("title", parent_title)
            extract_from_section(subsection, section_title)
    
    # Extraction à partir de chaque section
    for section in sections:
        extract_from_section(section)
    
    return articles


def build_corpus(token, lois_list, max_lois=None):
    """
    Construit le corpus complet des articles de lois
    
    Args:
        token: Token OAuth
        lois_list: Liste des lois à traiter
        max_lois: Nombre maximum de lois à traiter (pour tests)
    
    Returns:
        Liste complète des articles avec métadonnées
    """
    print(f"🏗️  Construction du corpus...")
    
    corpus = []
    lois_to_process = lois_list[:max_lois] if max_lois else lois_list
    
    for i, loi in enumerate(lois_to_process, 1):
        titre_court = loi.get('titre', loi.get('num', 'Sans titre'))[:50]
        print(f"   [{i}/{len(lois_to_process)}] {titre_court}...", end=" ")
        
        # Récupération des détails - utiliser l'ID (LEGITEXT) en priorité
        loi_id = loi.get("id")
        cid = loi.get("cid")
        
        if not loi_id:
            print("⚠️  Pas d'ID")
            continue
        
        details = get_loi_details(token, loi_id, cid)
        articles = extract_articles_metadata(details, loi)
        
        print(f"{len(articles)} articles")
        corpus.extend(articles)
    
    print(f"✅ Corpus construit: {len(corpus)} articles\n")
    return corpus


# ======================================================================
# SAUVEGARDE
# ======================================================================

def save_data(lois_list, corpus, start_date, end_date):
    """Sauvegarde les données en JSON et CSV"""
    period = f"{start_date[:4]}_{end_date[:4]}"
    
    # Sauvegarde liste des lois
    lois_file = DATA_DIR / f"liste_lois_{period}.json"
    with open(lois_file, "w", encoding="utf-8") as f:
        json.dump(lois_list, f, ensure_ascii=False, indent=2)
    print(f"💾 Lois sauvegardées: {lois_file}")
    
    # Sauvegarde corpus articles
    corpus_file = DATA_DIR / f"corpus_articles_{period}.json"
    with open(corpus_file, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    print(f"💾 Corpus sauvegardé: {corpus_file}")
    
    # Export CSV pour exploitation facile
    if corpus:
        import csv
        csv_file = DATA_DIR / f"corpus_articles_{period}.csv"
        keys = corpus[0].keys()
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(corpus)
        print(f"💾 CSV exporté: {csv_file}")


# ======================================================================
# MAIN
# ======================================================================

if __name__ == "__main__":
    # Paramètres
    START_DATE = "2015-01-01"
    END_DATE = "2025-12-31"
    MAX_LOIS_TEST = 3  # Mettre un nombre (ex: 3) pour tester sur quelques lois
    
    print("=" * 70)
    print("🏛️  EXTRACTION CORPUS LÉGISLATIF LEGIFRANCE")
    print("=" * 70)
    
    # 1. Authentification
    token = get_access_token()
    
    # 2. Récupération de la liste des lois
    lois_list = get_lois_list(token, START_DATE, END_DATE)
    
    # 3. Construction du corpus (articles + métadonnées)
    corpus = build_corpus(token, lois_list, max_lois=MAX_LOIS_TEST)
    
    # 4. Sauvegarde
    save_data(lois_list, corpus, START_DATE, END_DATE)
    
    print("\n" + "=" * 70)
    print(f"✅ TERMINÉ - {len(lois_list)} lois, {len(corpus)} articles extraits")
    print("=" * 70) 