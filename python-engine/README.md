# tagsearch — Python Engine

> Réalisé par **Gillesto66** & **Kiro** | Moteur de référence du projet TagSearch

Le moteur Python est la **source de vérité** du projet. C'est ici que les algorithmes sont définis, documentés et validés avant d'être portés en TypeScript et PHP. Toute modification de la formule de scoring doit partir de ce module.

---

## Objectif du module

Fournir un moteur de recherche par tags **entièrement in-memory**, sans dépendance externe, capable de :

- Indexer des produits e-commerce avec leurs métadonnées (type, niche, prix, localisation, avis)
- Répondre à des requêtes textuelles avec **autocomplétion** (O(L)) et **recherche floue** (Levenshtein + pruning)
- Classer les résultats selon 5 dimensions : pertinence BM25, qualité des avis, type de produit, niche, proximité géographique, budget

---

## Architecture des modules

```
tagsearch/
├── models.py       ProductMeta, ProductType, SearchPreferences
├── structures.py   Trie, DAWG, VarInt, CompressedPostingsList, LRUCache
├── scoring.py      BM25Index, calculate_final_score + constantes canoniques
└── engine.py       SearchEngine — point d'entrée public
```

**`structures.py`** — Phase 1 (mémoire)
- `TrieNode` avec `__slots__` + tableau fixe de 38 slots : 83% moins de RAM qu'un objet standard
- `DAWG` via algorithme de Daciuk : partage des suffixes, 30-50% moins de nœuds vs Trie
- `CompressedPostingsList` : delta-encoding + VarInt, 98% moins de RAM vs `set` Python

**`scoring.py`** — Phase 2 (intelligence)
- `BM25Index` : Okapi BM25 in-memory, paramètres `k1=1.5`, `b=0.75`
- `calculate_final_score` : formule multiplicative 5 dimensions avec Bayesian rating

---

## Installation

```bash
# Développement (pas d'installation nécessaire)
cd python-engine
python -m pytest tests/ -v

# Installation dans un autre projet
pip install -e .
```

> Pas besoin de `pip install -e .` pour développer — `pytest` trouve le package via `pythonpath = ["."]` dans `pyproject.toml`.

---

## Quick Start

```python
from tagsearch import SearchEngine, ProductMeta, ProductType, SearchPreferences

# Chargement depuis le dataset partagé
engine = SearchEngine(cache_size=200)
engine.load_catalog("../shared-assets/catalog.json")

# Recherche simple
results, status = engine.search("gaming")
# status = "CALCULÉ" | "CACHÉ" | "MISS"

# Recherche avec préférences utilisateur
prefs = SearchPreferences(
    preferred_type=ProductType.DIGITAL,   # Filtre doux : relègue les Physical
    max_price=50.0,                        # Filtre dur : exclut > 50€
    min_rating=4.0,                        # Filtre dur : exclut < 4★
    user_location="France",                # Bonus +15% si même zone
)
results, status = engine.search("cuisine", prefs=prefs, fuzzy=True, max_dist=1)

# Ajout manuel d'un produit
from tagsearch.models import ProductMeta, ProductType
meta = ProductMeta(
    name="Casque VR Pro",
    product_type=ProductType.PHYSICAL,
    niche="gaming",
    price=299.0,
    location="France",
    avg_rating=4.7,
    review_count=89,
    tags=["casque", "vr", "gaming", "tech"],
)
engine.add_product(11, meta)
```

---

## API

### `SearchEngine.search(query, prefs, fuzzy, max_dist, top_k)`

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `query` | `str` | — | Requête (normalisée en interne) |
| `prefs` | `SearchPreferences` | `None` | Préférences de re-ranking |
| `fuzzy` | `bool` | `True` | Recherche floue (Levenshtein + pruning) |
| `max_dist` | `int` | `1` | Distance de Levenshtein max |
| `top_k` | `int` | `10` | Nombre de résultats |

Retourne `(list[dict], status)` où chaque dict contient : `id`, `name`, `type`, `niche`, `price`, `rating`, `reviews`, `score`.

### `SearchPreferences`

| Champ | Type | Effet |
|-------|------|-------|
| `preferred_type` | `ProductType \| None` | Filtre doux : `×0.1` si mismatch |
| `preferred_niche` | `str \| None` | Boost `×1.2` si match |
| `max_price` | `float \| None` | Filtre dur : exclusion |
| `min_price` | `float \| None` | Filtre dur : exclusion |
| `user_location` | `str \| None` | Bonus `×1.15` si match |
| `min_rating` | `float` | Filtre dur : exclusion (défaut `0.0`) |

### Formule de scoring

```
score = bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
```

- `bm25_norm` = `max(min(bm25_raw / 10.0, 1.0), 0.05)`
- `quality_mult` = `(bayesian_rating / 5.0) ** 1.5`
- `bayesian_rating` = `(count × rating + 3.5 × 10) / (count + 10)`

---

## Tests

```bash
python -m pytest tests/ -v
python -m pytest tests/ -v --tb=short   # affichage compact
```

19 tests, organisés en 4 sections :
- `TestBM25Components` — composants IDF/TF isolés
- `TestScoringDimensions` — TC01 à TC05 cross-langage
- `TestCrossLanguageFixtures` — scores de référence stables
- `TestRobustness` — gestion d'erreurs exhaustive

---

## Benchmark

| Opération | Complexité | Temps typique (10k tags) |
|-----------|-----------|--------------------------|
| Autocomplete | O(L) | < 0.1 ms |
| Fuzzy search (max_dist=1) | O(L × ~5% nœuds) | < 1 ms |
| Scoring 100 candidats | O(n) | < 0.5 ms |
| Cache HIT | O(1) | < 0.01 ms |

*L = longueur du préfixe/requête*
