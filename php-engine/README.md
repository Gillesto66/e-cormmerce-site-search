# tagsearch-php — PHP Engine

> Réalisé par **Gillesto66** & **Kiro** | Portage PHP 8.2+ du moteur TagSearch

Portage fidèle du moteur Python en PHP moderne. Conçu pour s'intégrer nativement dans **Laravel** via un Service Provider, ou dans tout projet PHP 8.2+ sans framework.

---

## Objectif du module

Exposer le même moteur de recherche TagSearch dans l'écosystème PHP, avec :

- **PHP 8.2+** : `readonly class`, `enum` backed, `match`, named arguments
- **PSR-4** : chaque classe dans son propre fichier, autoloading Composer standard
- **Laravel-ready** : injection de dépendances via Service Provider
- **Résultats identiques** au moteur Python (tolérance `1e-9` sur les scores)

---

## Architecture des modules

```
src/
├── ProductType.php         Enum backed int (PHYSICAL=0, DIGITAL=1)
├── ProductMeta.php         métadonnées produit (readonly, niche normalisée)
├── Unicode.php             minuscules / découpage / tri / arrondi 4 décimales (parité Python)
├── DAWG.php, DAWGNode.php  graphe acyclique minimal
├── VarInt.php, CompressedPostingsList.php   postings delta + VarInt
├── SearchPreferences.php   Préférences utilisateur pour le re-ranking
├── ScoringConstants.php    Constantes BM25 + scoring (chargées via composer files)
├── BM25Index.php           Okapi BM25 in-memory
├── Scorer.php              calculateFinalScore — 5 dimensions
└── SearchEngine.php        Point d'entrée public + LRU cache
```

Note : `DAWG.php` est un vrai DAWG (algorithme de Daciuk), et `CompressedPostingsList.php` compresse les postings en delta + VarInt (−94 % mesuré sur 500 identifiants). Le moteur n'utilise **pas** `levenshtein()` ni `strtolower()` natifs : ils travaillent sur des octets, donc « pâtisserie » serait à distance 2 de « patisserie » (« â » = 2 octets) et « É » ne serait pas abaissé. Tout passe par `Unicode` (`mb_strtolower`, `mb_str_split`) : l'extension **mbstring est requise**.

---

## Installation

```bash
composer install
```

---

## Quick Start

```php
use TagSearch\{SearchEngine, SearchPreferences, ProductType};

$engine = new SearchEngine(cacheSize: 200);
$engine->loadCatalog(__DIR__ . '/tests/fixtures/catalog.json');   // ou votre propre catalogue JSON

// Recherche simple
$result = $engine->search('gaming');

// Avec préférences
$prefs = new SearchPreferences(
    preferredType: ProductType::DIGITAL,
    maxPrice: 50.0,
    minRating: 4.0,
    userLocation: 'France',
);
$result = $engine->search('cuisine', prefs: $prefs, fuzzy: false);
```

---

## Intégration Laravel

Dans `AppServiceProvider::register()` :

```php
$this->app->singleton(SearchEngine::class, function () {
    $engine = new SearchEngine(cacheSize: 500);
    $engine->loadCatalog(storage_path('app/catalog.json'));
    return $engine;
});
```

Dans un contrôleur :

```php
public function __invoke(Request $request, SearchEngine $engine): JsonResponse
{
    $prefs  = new SearchPreferences(maxPrice: $request->float('max_price'));
    $result = $engine->search($request->string('q'), prefs: $prefs);
    return response()->json($result);
}
```

---

## API

### `SearchEngine::search()`

```php
public function search(
    string             $query,
    ?SearchPreferences $prefs   = null,
    bool               $fuzzy   = true,
    int                $maxDist = 1,
    int                $topK    = 10,
): array  // ['results' => [...], 'status' => 'CALCULÉ'|'CACHÉ'|'MISS']
```

### `SearchPreferences`

| Propriété | Type | Effet |
|-----------|------|-------|
| `preferredType` | `?ProductType` | Filtre doux x0.1 si mismatch |
| `preferredNiche` | `?string` | Boost x1.2 si match |
| `maxPrice` | `?float` | Filtre dur : exclusion |
| `minPrice` | `?float` | Filtre dur : exclusion |
| `userLocation` | `?string` | Bonus x1.15 si match |
| `minRating` | `float` | Filtre dur (défaut 0.0) |

---

## Tests

```bash
vendor/bin/phpunit --testdox
```

55 tests PHPUnit : les 36 tests historiques (BM25Index, ProductMeta, Scorer, SearchEngine TC01-TC05, robustesse), `IndexingTest` (indexation en lot, remplacement/retrait, cache, DAWG, VarInt, Unicode) et `ReferenceTest` (rejeu des 261 requêtes de `tests/fixtures/reference.json`, généré par le moteur Python).

Les fixtures sont **dans le paquet** (`tests/fixtures/`) : les tests passent hors du monorepo. Elles sont copiées depuis `shared-assets/` par `scripts/sync_fixtures.py`.

---

## Constantes de scoring

Définies dans `ScoringConstants.php`, synchronisées avec `shared-assets/catalog.json` :

```php
const BM25_K1 = 1.5;  const BM25_B = 0.75;  const BM25_CAP = 10.0;
const QUALITY_EXPONENT = 1.5;  const PRIOR_MEAN = 3.5;  const PRIOR_WEIGHT = 10.0;
const TYPE_MISMATCH = 0.1;  const NICHE_BOOST = 1.2;
const PROXIMITY_BONUS = 1.15;  const PRICE_BUDGET_BOOST = 1.1;
```
