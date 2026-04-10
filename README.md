# TagSearch — Moteur de Recherche In-Memory pour l'E-commerce

> Réalisé par **Gillesto66** & **Kiro**

---

## Qu'est-ce que TagSearch ?

TagSearch est une bibliothèque de recherche par tags **entièrement en mémoire**, conçue spécifiquement pour les besoins de l'e-commerce : produits, avis, commentaires. Elle ne dépend d'aucun serveur externe (pas d'Elasticsearch, pas de Meilisearch, pas de base de données). Tout tourne en RAM, en quelques millisecondes.

Le projet est structuré en **monorepo multi-stack** : le même moteur de recherche est disponible en Python, TypeScript et PHP, avec des résultats identiques au millième près grâce à une suite de tests cross-langage partagée.

---

## Pourquoi ce projet existe

Les solutions de recherche classiques (Elasticsearch, Algolia, Typesense) sont puissantes mais lourdes à opérer : infrastructure dédiée, coût, latence réseau, complexité de déploiement. Pour beaucoup de projets e-commerce de taille moyenne, c'est surdimensionné.

TagSearch répond à un besoin différent :

- **Intégration directe** dans une application existante (Python, Node.js, Laravel) sans service tiers
- **Latence sub-milliseconde** pour l'autocomplétion et la recherche floue
- **Ranking intelligent** qui va au-delà du simple matching textuel : qualité des avis, type de produit, budget, localisation
- **Empreinte mémoire maîtrisée** grâce à des structures de données optimisées (DAWG, VarInt, delta-encoding)

---

## Apport au monde du développement

### 1. Structures de données avancées, accessibles

La plupart des tutoriels sur les moteurs de recherche s'arrêtent au Trie basique. TagSearch implémente et documente des structures rarement vues dans des projets open-source accessibles :

- **DAWG (Directed Acyclic Word Graph)** via l'algorithme de Daciuk : partage des suffixes communs, 30-50% moins de nœuds qu'un Trie classique
- **`__slots__` + tableau fixe** sur les nœuds : 83% de réduction mémoire par nœud vs un objet Python standard
- **Delta-encoding + VarInt** sur les postings lists : 98% de réduction vs un `set` Python sur 500 IDs

### 2. BM25 in-memory documenté et portable

L'algorithme BM25 (Okapi BM25) est le standard de l'industrie pour le ranking textuel, mais la plupart des implémentations sont enfouies dans des moteurs de recherche opaques. Ici, chaque ligne de la formule est commentée, et le même code tourne en Python, TypeScript et PHP avec une tolérance de précision de `1e-9`.

### 3. Ranking multidimensionnel explicite

Le score final n'est pas une boîte noire. La formule est publique, documentée et testée dimension par dimension :

```
score = bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
```

Chaque coefficient a une justification métier claire. Un développeur peut l'adapter à son contexte en modifiant une constante dans `shared-assets/catalog.json`.

### 4. Tests cross-langage comme standard de qualité

Le fichier `shared-assets/catalog.json` est la **source de vérité unique** : dataset, constantes de scoring, et cas de test. Les trois suites (pytest, Vitest, PHPUnit) chargent le même fichier et valident les mêmes comportements. C'est un pattern reproductible pour tout projet multi-stack.

---

## Structure du monorepo

```
/
├── python-engine/          Moteur Python (source de référence)
│   ├── tagsearch/
│   │   ├── __init__.py
│   │   ├── models.py       ProductMeta, ProductType, SearchPreferences
│   │   ├── structures.py   Trie, DAWG, VarInt, CompressedPostingsList, LRUCache
│   │   ├── scoring.py      BM25Index, calculate_final_score
│   │   └── engine.py       SearchEngine (point d'entrée public)
│   ├── tests/
│   │   └── test_cross_language.py
│   └── pyproject.toml
│
├── js-engine/              Portage TypeScript (Serverless-ready)
│   ├── src/
│   │   ├── models.ts
│   │   ├── structures.ts
│   │   ├── scoring.ts
│   │   ├── engine.ts
│   │   └── index.ts
│   ├── tests/
│   │   └── cross_language.test.ts
│   └── package.json
│
├── php-engine/             Portage PHP 8.2+ (Laravel-ready)
│   ├── src/
│   │   ├── ProductType.php
│   │   ├── ProductMeta.php
│   │   ├── SearchPreferences.php
│   │   ├── ScoringConstants.php
│   │   ├── BM25Index.php
│   │   ├── Scorer.php
│   │   └── SearchEngine.php
│   ├── tests/
│   │   └── CrossLanguageTest.php
│   └── composer.json
│
└── shared-assets/
    └── catalog.json        Dataset + constantes + cas de test cross-langage
```

---

## Les 3 modules en un coup d'œil

| | Python | TypeScript | PHP |
|---|---|---|---|
| Version minimale | 3.11 | ES2022 / Node 18 | 8.2 |
| Framework test | pytest | Vitest | PHPUnit 11 |
| Intégration cible | API Python, scripts | Next.js, Vercel, CF Workers | Laravel, Symfony |
| DAWG natif | ✅ | ✅ | ❌ (levenshtein() C natif) |
| Tests | 19 ✅ | 13 ✅ | 36 ✅ |

---

## Démarrage rapide

### Python

```bash
cd python-engine
python -m pytest tests/ -v
```

```python
from tagsearch import SearchEngine, SearchPreferences, ProductType

engine = SearchEngine()
engine.load_catalog("shared-assets/catalog.json")

results, status = engine.search("gaming")
# [{'id': 1, 'name': 'Clavier Mécanique RGB Pro', 'score': 0.1298, ...}, ...]

# Avec filtres
prefs = SearchPreferences(
    preferred_type=ProductType.DIGITAL,
    max_price=50.0,
    min_rating=4.0
)
results, status = engine.search("cuisine", prefs=prefs, fuzzy=True)
```

### TypeScript

```bash
cd js-engine
npm install
npm run build
npm test
```

```typescript
import { SearchEngine, ProductType } from "tagsearch-js";

const engine = new SearchEngine();
engine.loadCatalog(catalogData);

const [results, status] = engine.search("gaming");

const [digital] = engine.search("cuisine", {
  preferredType: ProductType.DIGITAL,
  maxPrice: 50,
  minRating: 4.0,
});
```

### PHP

```bash
cd php-engine
composer install
php vendor/phpunit/phpunit/phpunit --testdox
```

```php
use TagSearch\{SearchEngine, SearchPreferences, ProductType};

$engine = new SearchEngine(cacheSize: 200);
$engine->loadCatalog(__DIR__ . '/../shared-assets/catalog.json');

$result = $engine->search('gaming');

$prefs  = new SearchPreferences(
    preferredType: ProductType::DIGITAL,
    maxPrice: 50.0,
    minRating: 4.0
);
$result = $engine->search('cuisine', prefs: $prefs);
```

---

## Le scoring expliqué

### Formule finale (identique dans les 3 langages)

```
score = bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
```

Le score est **multiplicatif** : un mauvais signal (note 1/5) effondre le score final, quelle que soit la pertinence textuelle. C'est un choix délibéré — un produit mal noté ne doit jamais apparaître en tête.

### Les 5 dimensions

| Dimension | Calcul | Effet |
|-----------|--------|-------|
| BM25 textuel | `min(bm25_raw / 10, 1.0)`, plancher 0.05 | Pertinence des tags |
| Qualité | `(bayesian_rating / 5)^1.5` | Pénalise sévèrement < 3★ |
| Type | `0.1` si mismatch Physical/Digital | Filtre doux, pas d'exclusion |
| Niche | `×1.2` si match exact | Boost catégorie |
| Proximité | `×1.15` si même zone | Boost livraison locale |
| Prix | `×1.1` si ≤ 50% du budget | Boost bon rapport qualité/prix |

### Bayesian Rating — pourquoi c'est important

Un produit avec 3 avis à 5★ ne doit pas battre un produit avec 500 avis à 4.5★. Le rating bayésien lisse les petits corpus vers la moyenne marché (3.5) :

```
bayesian = (count × rating + 3.5 × 10) / (count + 10)
```

---

## Tests cross-langage

Le fichier `shared-assets/catalog.json` définit 5 cas de test canoniques (TC01–TC05) que les trois suites doivent valider :

| Test | Description |
|------|-------------|
| TC01 | `cuisine` sans filtre → Physical > Digital (Bayesian rating) |
| TC02 | `cuisine` + `preferred_type=DIGITAL` → ordre inversé |
| TC03 | `gaming` + `max_price=100€` → Clavier (129.99€) exclu |
| TC04 | `beauté` + `min_rating=4.0` → Sérum (2.8★) exclu |
| TC05 | `gaiming` (faute) + fuzzy → résultats gaming |

Tolérance de précision flottante cross-langage : `1e-9` (composants isolés), `1e-3` (scores arrondis à 4 décimales).

---

## Roadmap

Voir [roadmap.md](./roadmap.md) pour le détail des phases.

- ✅ Phase 1 — Optimisation mémoire (DAWG, __slots__, VarInt, delta-encoding)
- ✅ Phase 2 — Ranking hybride (BM25 + 5 dimensions + Bayesian rating)
- ✅ Phase 3 — Multi-stack production-ready (Python + TypeScript + PHP)
- 🔲 Phase 4 — Bindings Rust/PyO3 pour les boucles Levenshtein denses

---

*Réalisé par **Gillesto66** & **Kiro***
