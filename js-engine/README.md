# tagsearch-js — TypeScript Engine

> Réalisé par **Gillesto66** & **Kiro** | Portage TypeScript du moteur TagSearch

Portage fidèle du moteur Python en TypeScript strict. Conçu pour les environnements **Serverless** (Vercel, Cloudflare Workers, AWS Lambda) où l'état in-memory est naturel et les dépendances externes sont à éviter.

---

## Objectif du module

Exposer le même moteur de recherche TagSearch dans l'écosystème JavaScript/TypeScript, avec :

- **Types stricts** (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) — zéro `any`
- **Compatibilité ESM** native (`"type": "module"`, imports `.js`)
- **Résultats identiques** au moteur Python (tolérance `1e-9` sur les scores)
- **Zéro dépendance runtime** — uniquement des devDependencies (TypeScript, Vitest)

---

## Architecture des modules

```
src/
├── models.ts       ProductMeta, ProductType, SearchPreferences
├── structures.ts   DAWG, LRUCache
├── scoring.ts      BM25Index, calculateFinalScore + constantes
├── engine.ts       SearchEngine — point d'entrée public
└── index.ts        Exports publics du package
```

**Différences vs Python :**
- Pas de `__slots__` (inutile en JS — les objets V8 sont déjà optimisés)
- `Map` au lieu de `dict` pour les structures internes (meilleure performance sur les clés string)
- `DAWG.structuralKey()` utilise une string sérialisée au lieu d'un tuple Python

---

## Installation

```bash
npm install          # installe TypeScript + Vitest
npm run build        # compile src/ → dist/
npm test             # lance Vitest
```

### Utilisation depuis un projet externe

```bash
npm install tagsearch-js
```

```typescript
import { SearchEngine, ProductType } from "tagsearch-js";
```

---

## Quick Start

```typescript
import { SearchEngine, ProductType } from "tagsearch-js";
import { readFileSync } from "fs";

// Chargement depuis le dataset partagé
const engine = new SearchEngine();
const catalog = JSON.parse(readFileSync("../shared-assets/catalog.json", "utf-8"));
engine.loadCatalog(catalog);

// Recherche simple
const [results, status] = engine.search("gaming");
// status: "CALCULÉ" | "CACHÉ" | "MISS"

// Avec préférences
const [digital, s] = engine.search("cuisine", {
  preferredType: ProductType.DIGITAL,   // Filtre doux
  maxPrice: 50,                          // Filtre dur
  minRating: 4.0,                        // Filtre dur
  userLocation: "France",                // Bonus proximité
});

// Ajout manuel d'un produit
import { createProductMeta } from "tagsearch-js";
const meta = createProductMeta({
  name: "Casque VR Pro", type: "PHYSICAL", niche: "gaming",
  price: 299.0, location: "France", avg_rating: 4.7,
  review_count: 89, tags: ["casque", "vr", "gaming"],
});
engine.addProduct(11, meta);
```

---

## API

### `SearchEngine.search(query, prefs?, fuzzy?, maxDist?, topK?)`

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `query` | `string` | — | Requête utilisateur |
| `prefs` | `Partial<SearchPreferences>` | `{}` | Préférences de re-ranking |
| `fuzzy` | `boolean` | `true` | Recherche floue (Levenshtein) |
| `maxDist` | `number` | `1` | Distance de Levenshtein max |
| `topK` | `number` | `10` | Nombre de résultats |

Retourne `[SearchResult[], SearchStatus]`.

```typescript
interface SearchResult {
  id: number; name: string; type: string;
  niche: string; price: number; rating: number;
  reviews: number; score: number;
}

type SearchStatus = "CACHÉ" | "CALCULÉ" | "MISS";
```

### `SearchPreferences`

```typescript
interface SearchPreferences {
  preferredType?  : ProductType;   // Filtre doux ×0.1 si mismatch
  preferredNiche? : string;        // Boost ×1.2 si match
  maxPrice?       : number;        // Filtre dur
  minPrice?       : number;        // Filtre dur
  userLocation?   : string;        // Bonus ×1.15 si match
  minRating        : number;       // Filtre dur (défaut 0)
}
```

---

## Tests

```bash
npm test
```

13 tests Vitest, miroir exact des tests Python. Chargent `shared-assets/catalog.json` comme source de vérité.

---

## Précision flottante cross-langage

`Math.log()` en V8 et `math.log()` en Python utilisent tous deux IEEE 754 double précision mais peuvent diverger au 15e chiffre significatif. Les scores sont arrondis à 4 décimales (`Math.round(x * 10000) / 10000`). Tolérance des tests : `1e-9` sur les composants isolés, `1e-3` sur les ratios post-arrondi.

---

## Benchmark

Identique au moteur Python. Le DAWG est reconstruit à chaque `addProduct()`. En production avec des insertions fréquentes, utiliser un buffer Trie et reconstruire en batch.
