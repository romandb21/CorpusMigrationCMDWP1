# Guide d'utilisation : Collection des discours publics

## Description
Outil de scraping des discours publics depuis le site vie-publique.fr.
Le processus se déroule en 3 étapes : collecte des liens, téléchargement des documents, puis extraction/analyse du corpus.

## Installation
```bash
cd "code/code"
pip install click requests beautifulsoup4 loguru joblib
```

## Utilisation

### Étape 1 : Collecter les liens des discours
Récupère tous les liens vers les discours disponibles pour une période donnée.

```bash
python -m discours.cli download links \
  --output-file links.json \
  --start-year 2015 \
  --end-year 2025 \
  --n-jobs 4
```

**Options :**
- `--output-file` (obligatoire) : Fichier JSON de sortie contenant les liens
- `--start-year` (obligatoire) : Première année à inclure
- `--end-year` (obligatoire) : Dernière année à inclure
- `--n-jobs` : Nombre de processus parallèles (défaut : -1 = tous les CPU)

**Sortie :** Fichier JSON avec les liens structurés par année

### Étape 2 : Télécharger les documents
Télécharge le contenu textuel de chaque discours à partir des liens collectés.

```bash
python -m discours.cli download documents --input-file links.json --output-dir documents --n-jobs 4
```

**Options :**
- `--input-file` (obligatoire) : Fichier JSON contenant les liens (créé à l'étape 1)
- `--output-dir` (obligatoire) : Dossier où stocker les documents téléchargés
- `--n-jobs` : Nombre de processus parallèles (défaut : -1 = tous les CPU)

**Sortie :** Documents texte organisés par année dans `documents/YYYY/`
**Reprise :** Si interrompu, le script peut reprendre là où il s'est arrêté

### Étape 3 : Construire le corpus analysé
Extrait et structure les informations des documents téléchargés dans un corpus JSON.

```bash
python -m discours.cli analyze build --input-dir documents --output-file corpus.json \
--n-jobs 4
```

**Options :**
- `--input-dir` (obligatoire) : Dossier contenant les documents téléchargés (étape 2)
- `--output-file` (obligatoire) : Fichier JSON de sortie avec le corpus structuré
- `--n-jobs` : Nombre de processus parallèles (défaut : -1 = CPU-1)

**Sortie :** Corpus JSON avec métadonnées et contenu structuré

## Exemple complet (2015-2025)
```bash
# Étape 1 : Collecter les liens
python -m discours.cli download links \
  --output-file links.json \
  --start-year 2015 \
  --end-year 2025

# Étape 2 : Télécharger les documents
python -m discours.cli download documents \
  --input-file links.json \
  --output-dir documents

# Étape 3 : Construire le corpus
python -m discours.cli analyze build \
  --input-dir documents \
  --output-file corpus.json
```

## Structure des fichiers
```
code/code/src/discours/
├── cli.py              # Interface en ligne de commande
├── download/           # Modules de téléchargement
│   ├── links.py       # Collecte des liens
│   └── documents.py   # Téléchargement des documents
├── parsing/            # Module d'extraction
│   └── extract.py     # Parsing et structuration
├── links.json          # Liens collectés (sortie étape 1)
├── corpus.json         # Corpus final (sortie étape 3)
└── documents/          # Documents téléchargés (sortie étape 2)
    ├── 2015/
    ├── 2016/
    └── ...
```

## Ordre des opérations
⚠️ **Important** : Respecter l'ordre des 3 étapes :
1. `download links` → génère `links.json`
2. `download documents` → génère les fichiers dans `documents/`
3. `analyze build` → génère `corpus.json`

## Options de débogage
Ajouter `--debug` pour un logging détaillé :
```bash
python -m discours.cli --debug download links ...
```

## Parallélisation
- `-n-jobs -1` : Utilise tous les CPU disponibles (par défaut)
- `-n-jobs 4` : Limite à 4 processus parallèles
- `-n-jobs 1` : Exécution séquentielle (utile pour le débogage)

