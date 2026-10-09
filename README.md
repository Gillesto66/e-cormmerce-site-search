# TagSearch — Moteur de Recherche In-Memory pour l'E-commerce

> Réalisé par **Gillesto66** & **Kiro** — licence [MIT](./LICENSE)

---

## Qu'est-ce que TagSearch ?

TagSearch est une bibliothèque de recherche par tags **entièrement en mémoire**, conçue pour l'e-commerce (produits, avis, commentaires). Elle ne dépend d'aucun serveur externe (pas d'Elasticsearch, pas de Meilisearch, pas de base de données) et n'a **aucune dépendance runtime**.

Le projet est un **monorepo multi-stack** : le même moteur est disponible en Python, TypeScript et PHP. Les trois implémentations sont vérifiées contre un jeu de référence commun (voir [Garanties](#garanties-de-parité-entre-les-langages)).

---

## Pourquoi ce projet existe

Les solutions classiques (Elasticsearch, Algolia, Typesense) sont puissantes mais lourdes à opérer. Pour beaucoup de projets e-commerce de taille moyenne, c'est surdimensionné. TagSearch propose :

- **Intégration directe** dans une application existante (Python, Node.js, Laravel) sans service tiers
- **Latence de l'ordre de la milliseconde** — mesurée, pas promise : voir [docs/benchmarks.md](./docs/benchmarks.md)
- **Ranking multidimensionnel** : qualité des avis, type de produit, budget, localisation
- **Empreinte mémoire maîtrisée** : DAWG et postings compressés (delta + VarInt) dans les trois langages

> Limite à connaître : l'index vit en mémoire d'un processus. Il se reconstruit au démarrage depuis le catalogue ; il n'est pas partagé entre processus.

---

## Ce qui est vrai, langage par langage

| | Python | TypeScript | PHP |
|---|:---:|:---:|:---:|
| DAWG (partage de suffixes, algorithme de Daciuk) | ✅ | ✅ | ✅ |
| Postings compressés (delta + VarInt) | ✅ −97,5 % | ✅ −96,1 % | ✅ −93,8 % |
| Nœuds `__slots__` (−83,7 %) | ✅ | sans objet | sans objet |
| Indexation en lot (linéaire) | ✅ | ✅ | ✅ |
| Cache LRU | ✅ | ✅ | ✅ |
| Distance de Levenshtein sur points de code Unicode | ✅ | ✅ | ✅ |
| Tests | 41 | 30 | 55 |

Les gains mémoire sont **mesurés** sur 500 identifiants (détail, méthode et limites dans [docs/benchmarks.md](./docs/benchmarks.md)).
Le DAWG de la version 1.0.0 ne partageait en réalité aucun suffixe (0 % de gain) ; il est corrigé en 1.0.1. Le gain dépend du vocabulaire : 85 % sur un vocabulaire synthétique à suffixes répétés, 50 % en pire cas sur lettres aléatoires, **non mesuré sur un vrai catalogue**.

---

## Ranking multidimensionnel, explicite

```
score = bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
```

Le score est **multiplicatif** : un mauvais signal (note 1/5) effondre le score final, quelle que soit la pertinence textuelle. Les constantes sont publiques (`scoring_constants` dans `shared-assets/catalog.json`, et dans `scoring.py` / `scoring.ts` / `ScoringConstants.php`).

### Règles de départage (définies, identiques dans les trois langages)

- Résultats triés par **score décroissant, puis `id` croissant**.
- Tags appariés par recherche floue : triés par **(distance de Levenshtein, tag)** ; par autocomplétion : ordre lexicographique des points de code Unicode.
- Scores arrondis à 4 décimales **exactement comme Python** (`round(x, 4)`), y compris sur les égalités exactes.
- Le cache est indexé par (requête, préférences, `fuzzy`, `max_dist`, `top_k`) ; les résultats rendus sont des copies.

### Les 5 dimensions

| Dimension | Calcul | Effet |
|-----------|--------|-------|
| BM25 textuel | `min(bm25_raw / 10, 1.0)`, plancher 0.05 | Pertinence des tags |
| Qualité | `(bayesian_rating / 5)^1.5` | Pénalise sévèrement < 3★ |
| Type | `0.1` si mismatch Physical/Digital | Filtre doux, pas d'exclusion |
| Niche | `×1.2` si match exact | Boost catégorie |
| Proximité | `×1.15` si même zone | Boost livraison locale |
| Prix | `×1.1` si ≤ 50% du budget | Boost bon rapport qualité/prix |

### Bayesian rating

Un produit avec 3 avis à 5★ ne doit pas battre un produit avec 500 avis à 4.5★ :

```
bayesian = (count × rating + 3.5 × 10) / (count + 10)
```

---

## Structure du monorepo

```
/
├── python-engine/     Moteur Python (référence) — pip install tagsearch
├── js-engine/         Portage TypeScript       — npm install tagsearch-js
├── php-engine/        Portage PHP 8.2+         — composer require tagsearch/php-engine
├── shared-assets/
│   ├── catalog.json            Dataset de démonstration + constantes (10 produits, TC01–TC05)
│   ├── reference.json          Jeu de référence croisé (229 produits, 261 requêtes, 7 063 arrondis)
│   └── generate_reference.py   Régénère reference.json depuis le moteur Python
├── benchmarks/        Mesures reproductibles (indexation, latence, mémoire, DAWG vs Trie)
├── scripts/           sync_fixtures.py (fixtures PHP), sync_php_repo.py (dépôt Packagist)
├── docs/              roadmap, revue de littérature, benchmarks
└── .github/workflows/ CI (3 suites × Linux/Windows, parité, benchmark de complexité)
```

---

## Démarrage rapide

### Python (≥ 3.11)

```bash
cd python-engine
python -m pytest tests/ -v
```

```python
from tagsearch import SearchEngine, SearchPreferences, ProductType

engine = SearchEngine()
engine.load_catalog("shared-assets/catalog.json")   # indexation en lot, atomique

results, status = engine.search("gaming")           # status : "CALCULÉ" | "CACHÉ" | "MISS"

prefs = SearchPreferences(preferred_type=ProductType.DIGITAL, max_price=50.0, min_rating=4.0)
results, status = engine.search("cuisine", prefs=prefs, fuzzy=True)

# Ajouts au fil de l'eau : l'index est reconstruit une seule fois, au prochain search()
engine.add_product(42, meta)      # ou engine.add_products([...]) puis commit() implicite
```

### TypeScript (Node ≥ 18)

```bash
cd js-engine && npm install && npm run build && npm test
```

```typescript
import { SearchEngine, ProductType } from "tagsearch-js";

const engine = new SearchEngine();
engine.loadCatalog(catalogData);
const [results, status] = engine.search("gaming");
const [digital] = engine.search("cuisine", { preferredType: ProductType.DIGITAL, maxPrice: 50, minRating: 4.0 });
```

### PHP (≥ 8.2, extension `mbstring`)

```bash
cd php-engine && composer install && vendor/bin/phpunit
```

```php
use TagSearch\{SearchEngine, SearchPreferences, ProductType};

$engine = new SearchEngine(cacheSize: 200);
$engine->loadCatalog('/chemin/vers/catalog.json');
$result = $engine->search('gaming');                       // ['results' => [...], 'status' => '...']
$result = $engine->search('cuisine', new SearchPreferences(preferredType: ProductType::DIGITAL, maxPrice: 50.0));
```

---

## Garanties de parité entre les langages

`shared-assets/reference.json` est **généré par le moteur Python** (source de vérité) : 229 produits, 261 requêtes (accents, majuscules, emoji et CJK, tags numériques, ex æquo parfaits, filtres combinés, `max_dist` de 0 à 3, `top_k`, cache, erreurs attendues) et 7 063 valeurs d'arrondi. Les trois suites le rejouent **dans l'ordre**, sur un moteur neuf, et exigent : mêmes statuts, mêmes identifiants dans le même ordre, mêmes scores (tolérance `1e-9`), mêmes erreurs.

```bash
python shared-assets/generate_reference.py --check   # échoue si le fichier est périmé
python scripts/sync_fixtures.py --check              # échoue si les fixtures PHP dérivent
```

Les cinq cas canoniques TC01–TC05 de `catalog.json` restent validés dans chaque suite.

Hypothèse documentée : les chaînes d'entrée sont supposées en forme Unicode NFC (« é » en un seul point de code).

---

## Mesures

Voir [docs/benchmarks.md](./docs/benchmarks.md). En résumé (portable de développement, 3 200 produits) :

- Indexation : quasi linéaire (×1,3 à ×1,9 par doublement ; ×3,3 à ×3,8 avant la 1.0.1).
- Recherche, cache vide : Python ≈ 0,7 ms (préfixe) / 2,1 ms (floue) au p50 ; JS ≈ 0,06 / 0,11 ms ; PHP ≈ 0,19 / 0,69 ms.

---

## Roadmap

Voir [docs/roadmap.md](./docs/roadmap.md).

- ✅ Phase 1 — Optimisation mémoire (DAWG réel, `__slots__`, VarInt, delta-encoding) dans les trois langages
- ✅ Phase 2 — Ranking hybride (BM25 + 5 dimensions + Bayesian rating)
- ✅ Phase 3 — Multi-stack production-ready, parité vérifiée sur un jeu de référence
- 🔲 Phase 4 — Bindings Rust/PyO3 pour les boucles Levenshtein denses

---

*Réalisé par **Gillesto66** & **Kiro***
