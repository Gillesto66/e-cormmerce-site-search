# tagsearch-js — TypeScript Engine

In-memory tag search engine for e-commerce. Portage fidèle du moteur Python.
Optimisé pour environnements Serverless (Vercel, Cloudflare Workers).

## Installation

```bash
npm install
```

## Quick Start

```typescript
import { SearchEngine, ProductType } from "./src/index.js";
import catalogData from "../shared-assets/catalog.json" assert { type: "json" };

const engine = new SearchEngine();
engine.loadCatalog(catalogData);

// Recherche simple
const [results, status] = engine.search("gaming");

// Avec préférences
const [digital] = engine.search("cuisine", {
  preferredType: ProductType.DIGITAL,
  maxPrice: 50,
});
```

## API

### `SearchEngine.search(query, prefs?, fuzzy?, maxDist?, topK?)`

Retourne `[SearchResult[], SearchStatus]` où `SearchStatus` ∈ `"CACHÉ" | "CALCULÉ" | "MISS"`.

```typescript
interface SearchResult {
  id: number; name: string; type: string;
  niche: string; price: number; rating: number;
  reviews: number; score: number;
}
```

## Tests

```bash
npm test
```

## Précision flottante cross-langage

`Math.log()` en V8 et `math.log()` en Python peuvent diverger au 15e chiffre significatif (IEEE 754).
Les tests cross-langage utilisent une tolérance de `1e-9`. Les scores sont arrondis à 4 décimales.

## Benchmark attendu

Identique au moteur Python. Le DAWG est reconstruit à chaque `addProduct()` — en production,
utiliser un buffer et reconstruire en batch.
