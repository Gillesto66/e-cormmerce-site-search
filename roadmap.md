# Roadmap — Bibliothèque Python In-Memory Search (Tags E-commerce)

---

## 🛠 Phase 1 : Optimisation de l'empreinte mémoire

**Statut : ✅ TERMINÉ**

### ✅ Étape 1.1 — `TrieNode` avec `__slots__` + Lazy Init

**Problème :** Chaque `TrieNode` instanciait un `dict` Python vide pour `children`, même sur les nœuds feuilles. Un `dict` vide = ~232 bytes. Sur 50k nœuds → ~11 MB de surcoût pur.

**Solution :**
- `__slots__ = ('children', 'is_terminal', 'tag')` → supprime le `__dict__` par instance.
- `children = None` par défaut (lazy init) → le tableau n'est alloué qu'à l'insertion du premier enfant.
- Court-circuit dans `_dfs` et `_fuzzy_dfs` : `if node.children is None: return`.

**Gain mesuré :** 56 bytes/nœud vs 344 bytes legacy → **83% de réduction**.

---

### ✅ Étape 1.2 — Tableau fixe de 38 slots pour `children` (O(1) sans hash)

**Problème :** Le `dict` Python pour `children` a un overhead de ~200 bytes dès le premier enfant + coût de hachage à chaque accès.

**Solution :**
- `children = [None] * ALPHA_SIZE` (38 slots : a-z, 0-9, tiret, espace).
- Accès `O(1)` garanti via `_char_index(c)` → `ord(c) - ord('a')`, zéro hash.
- Lazy init conservée : le tableau n'est alloué qu'au premier enfant réel.
- `iter_children()` court-circuite immédiatement si `children is None` (nœuds feuilles).

**Angle mort :** Le tableau fixe coûte 38 × 8 = 304 bytes dès qu'un nœud a au moins un enfant. Rentable vs dict dès 2+ enfants par nœud (cas typique dans un Trie de tags).

---

### ✅ Étape 1.3 — DAWG (Directed Acyclic Word Graph) via algorithme de Daciuk

**Problème :** Un Trie partage les préfixes mais duplique les suffixes. Les tags e-commerce ont des suffixes très fréquents (`-able`, `-ing`, `-eur`, `-tion`, `sans-`).

**Solution :**
- Implémentation du DAWG par l'algorithme de Daciuk (insertion en ordre lexicographique + minimisation incrémentale).
- Les nœuds structurellement identiques sont fusionnés via un registre `_minimized: dict[tuple, DAWGNode]`.
- `DAWG.build(tags)` trie automatiquement les tags et finalise la construction.
- Fuzzy search (Levenshtein + pruning) et autocomplete conservés avec la même interface que le Trie.

**Contrainte documentée :** Le DAWG est immutable après `finish()`. Stratégie de production : buffer Trie pour les insertions dynamiques + rebuild DAWG en batch.

**Gain mesuré :** Dépend du taux de suffixes communs dans le corpus. Sur un corpus e-commerce réel (10k+ tags), réduction attendue de 30-50% du nombre de nœuds.

---

### ✅ Étape 1.4 — Postings Lists compressées : Delta-encoding + VarInt

**Problème :** Les `set` Python dans `inverted_index` consomment ~200 bytes par set vide + 28 bytes/entier Python.

**Solution :**
- `CompressedPostingsList` : stocke les IDs triés en delta-encoding + VarInt (même principe que Protocol Buffers).
- Delta-encoding : `[1001, 1002, 1005, 1010]` → `[1001, 1, 3, 5]` → deltas encodés sur 1-2 bytes chacun.
- Dirty buffer : les nouveaux IDs s'accumulent dans `_pending` (list Python), compression déclenchée par `flush()` uniquement.
- `VarInt.encode/decode` : 0-127 → 1 byte, 128-16383 → 2 bytes, validé sur tous les cas limites.

**Gain mesuré (benchmark 500 IDs aléatoires) :**
- `set` Python : ~46 984 bytes
- `CompressedPostingsList` : ~500 bytes
- **Réduction : 98%**

---

## 🚀 Phase 2 : Fonctionnalités E-commerce & Avis

**Statut : ✅ TERMINÉ**

### Architecture du ranking multidimensionnel

Score final = `bm25_norm × quality_multiplier × type_factor × niche_boost × proximity_bonus × price_factor`

Le score est **multiplicatif** (pas additif) : un mauvais signal effondre le score final quelle que soit la pertinence textuelle. Un produit noté 2/5 obtient un `quality_multiplier` de 0.226 — il ne peut pas compenser avec un bon BM25.

### Dimension 1 — BM25 in-memory (`BM25Index`)

- Paramètres : `k1=1.5`, `b=0.75` (standard e-commerce).
- Normalisation par plafond empirique `BM25_CAP=10.0` → score dans [0.05, 1.0].
- Plancher à 0.05 pour que les tags très fréquents (IDF faible) restent visibles.

### Dimension 2 — Qualité avec Bayesian Rating

- `quality_multiplier = (bayesian_rating / 5.0) ** 1.5`
- Bayesian rating : `(count × rating + 3.5 × 10) / (count + 10)` — lisse les produits avec peu d'avis vers la moyenne marché (3.5).
- Résultat mesuré : Sérum (2.8★, 12 avis) → `quality_mult=0.492` vs Palette (4.5★, 276 avis) → `quality_mult=0.844`.

### Dimension 3 — Type Physical/Digital (`ProductType` Enum)

- `type_factor=1.0` si match ou pas de préférence, `0.1` si mismatch (filtre doux).
- Permet de distinguer E-book Cuisine (Digital) vs Robot Pâtissier (Physical) sur le même tag "cuisine".
- Test validé : avec `preferred_type=DIGITAL`, l'E-book passe de 0.1082 à 0.1082 et le Robot chute de 0.1354 à 0.0135 (×0.1).

### Dimension 4 — Proximité / Localisation

- `proximity_bonus=1.15` si `user_location` correspond à `product.location`.
- Produits digitaux (`location=None`) → toujours 1.0 (livraison universelle).

### Dimension 5 — Prix (filtres dur + doux)

- Filtre dur : exclusion si hors plage `[min_price, max_price]`.
- Filtre doux : `price_factor=1.1` si le produit est dans la moitié basse du budget.
- Test validé : budget 100€ → Clavier (129.99€) exclu, Souris (79.99€) seule.

### `SearchPreferences` — Coefficients MVP par défaut

| Dimension   | Mécanisme          | Valeur par défaut |
|-------------|--------------------|--------------------|
| BM25        | Base normalisée    | 1.0 (base)         |
| Qualité     | Multiplicateur exp | `(r/5)^1.5`        |
| Type        | Filtre doux        | 0.1 si mismatch    |
| Niche       | Boost              | +20% si match      |
| Proximité   | Bonus              | +15% si match      |
| Prix        | Filtre dur + doux  | +10% si ≤ 50% budget |

### Dataset de test (10 produits)

Mix Physical/Digital, 6 niches (gaming, audio, cuisine, saas, beauté, sport), plage de prix 9.99€–349€, volume d'avis de 12 à 1200.

---

## 🧪 Phase 3 : Production-Ready & Multi-Stack

**Statut : ✅ TERMINÉ**

### Monorepo structure

```
/root
├── /python-engine   — tagsearch (PyProject.toml, src modulaire, pytest)
├── /js-engine       — tagsearch-js (TypeScript strict, Vitest)
├── /php-engine      — tagsearch-php (PHP 8.2+, PHPUnit, Laravel-ready)
└── /shared-assets   — catalog.json (dataset + constantes de scoring + cas de test)
```

### Python — Refactoring modulaire

- `tagsearch/models.py`     : `ProductMeta` (slots=True), `ProductType`, `SearchPreferences`
- `tagsearch/structures.py` : `Trie`, `DAWG`, `VarInt`, `CompressedPostingsList`, `LRUCache`
- `tagsearch/scoring.py`    : `BM25Index`, `calculate_final_score` — constantes exportées
- `tagsearch/engine.py`     : `SearchEngine` — gestion d'erreurs exhaustive, logging, `load_catalog()`
- 19 tests pytest : 19/19 ✅

### TypeScript — Portage fidèle

- Types stricts (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)
- `DAWG`, `LRUCache`, `BM25Index`, `calculateFinalScore`, `SearchEngine` — même interface que Python
- Optimisé Serverless : état in-memory, pas d'I/O bloquant
- Tests Vitest miroir des tests Python

### PHP — Portage fidèle + Laravel-ready

- PHP 8.2+ : `readonly class`, `enum`, `match`, named arguments
- `SearchEngine::loadCatalog()` + intégration via Service Provider Laravel
- `levenshtein()` natif C pour la recherche floue (pas de DAWG en PHP pur)
- Tests PHPUnit miroir des tests Python

### Stratégie de précision flottante cross-langage

IEEE 754 double précision sur les 3 langages. `log()` peut diverger au 15e chiffre.
- Scores arrondis à 4 décimales (arrondi Python `round()`, JS `Math.round(x*10000)/10000`, PHP `round($x, 4)`)
- Tolérance des tests cross-langage : `1e-9` pour les composants isolés, `1e-3` pour les ratios post-arrondi
- `shared-assets/catalog.json` contient les constantes canoniques et les cas de test — source de vérité unique

### Commandes de test

```bash
# Python
cd python-engine && pytest tests/ -v

# TypeScript
cd js-engine && npm test

# PHP
cd php-engine && ./vendor/bin/phpunit tests/
```

