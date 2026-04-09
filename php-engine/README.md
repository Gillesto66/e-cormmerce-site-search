# tagsearch-php — PHP Engine

In-memory tag search engine for e-commerce. PHP 8.2+, Laravel-ready.

## Installation

```bash
composer install
```

## Quick Start

```php
use TagSearch\SearchEngine;
use TagSearch\SearchPreferences;
use TagSearch\ProductType;

$engine = new SearchEngine(cacheSize: 200);
$engine->loadCatalog(__DIR__ . '/../shared-assets/catalog.json');

// Recherche simple
$result = $engine->search('gaming');
// $result['results'] = [...], $result['status'] = 'CALCULÉ'

// Avec préférences
$prefs  = new SearchPreferences(preferredType: ProductType::DIGITAL, maxPrice: 50.0);
$result = $engine->search('cuisine', prefs: $prefs, fuzzy: false);
```

## Intégration Laravel

Dans `AppServiceProvider::register()` :

```php
$this->app->singleton(SearchEngine::class, function () {
    $engine = new SearchEngine(cacheSize: 500);
    $engine->loadCatalog(storage_path('app/catalog.json'));
    return $engine;
});
```

Puis dans un contrôleur :

```php
public function search(Request $request, SearchEngine $engine): JsonResponse {
    $results = $engine->search($request->string('q'));
    return response()->json($results);
}
```

## API

### `SearchEngine::search(string $query, ?SearchPreferences $prefs, bool $fuzzy, int $maxDist, int $topK)`

Retourne `array{results: array[], status: string}` où `status` ∈ `'CALCULÉ' | 'CACHÉ' | 'MISS'`.

## Tests

```bash
./vendor/bin/phpunit tests/
```

## Note sur le DAWG en PHP

PHP n'a pas d'implémentation native de DAWG. Le moteur utilise `levenshtein()` natif (C)
pour la recherche floue et `str_starts_with()` pour l'autocomplétion.
Pour un corpus > 100k tags, envisager une extension C ou un service dédié (Meilisearch).
