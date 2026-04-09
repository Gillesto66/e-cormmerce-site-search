# tagsearch — Python Engine

In-memory tag search engine for e-commerce. DAWG + BM25 + 5-dimension hybrid ranking.

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from tagsearch import SearchEngine, ProductMeta, ProductType, SearchPreferences

engine = SearchEngine(cache_size=200)
engine.load_catalog("../shared-assets/catalog.json")

# Recherche simple
results, status = engine.search("gaming")

# Recherche avec préférences
prefs = SearchPreferences(preferred_type=ProductType.DIGITAL, max_price=50.0)
results, status = engine.search("cuisine", prefs=prefs, fuzzy=True, max_dist=1)
```

## API

### `SearchEngine.search(query, prefs, fuzzy, max_dist, top_k)`

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `query`   | `str` | — | Requête utilisateur |
| `prefs`   | `SearchPreferences` | `None` | Préférences de re-ranking |
| `fuzzy`   | `bool` | `True` | Active la recherche floue (Levenshtein) |
| `max_dist`| `int` | `1` | Distance de Levenshtein maximale |
| `top_k`   | `int` | `10` | Nombre de résultats retournés |

Retourne `(list[dict], status)` où `status` ∈ `{"CALCULÉ", "CACHÉ", "MISS"}`.

### Score final (formule canonique)

```
score = bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
```

- `bm25_norm` = `min(bm25_raw / 10.0, 1.0)`, plancher à `0.05`
- `quality_mult` = `(bayesian_rating / 5.0) ** 1.5`
- `bayesian_rating` = `(count × rating + 3.5 × 10) / (count + 10)`

## Tests

```bash
pytest --cov=tagsearch
```

## Benchmark attendu

| Opération | Complexité | Temps typique (10k tags) |
|-----------|-----------|--------------------------|
| Autocomplete | O(L) | < 0.1 ms |
| Fuzzy search (max_dist=1) | O(L × 5%) | < 1 ms |
| Scoring 100 candidats | O(n) | < 0.5 ms |
| Cache HIT | O(1) | < 0.01 ms |
