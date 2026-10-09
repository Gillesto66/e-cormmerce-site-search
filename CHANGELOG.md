# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage sémantique.
Les trois paquets (`tagsearch`, `tagsearch-js`, `tagsearch/php-engine`) partagent le même numéro de version.

## [1.0.1] — 2026-10-09

Version corrective issue de l'audit `AUDIT.md`. Aucune rupture d'API ; les scores restent identiques
(le jeu de référence a été généré **après** correction et rejoué dans les trois langages).

### Corrigé
- **C1 — Indexation quadratique.** `add_product` reconstruisait tout le DAWG et rechargeait tous les postings à chaque
  produit. Désormais paresseux : une seule reconstruction au premier `search()` (ou `commit()`), nouveaux
  `add_products()` / `addProducts()` en lot. 800 produits : 242 s → 0,78 s ; croissance quasi linéaire.
  `load_catalog()` est atomique (un produit invalide n'ajoute rien).
- **DAWG qui n'en était pas un (découvert pendant la correction).** Le mot était stocké dans la clé structurelle des
  nœuds, ce qui interdisait tout partage de suffixes : 6 827 nœuds pour le DAWG comme pour un Trie (0 % de gain).
  Le mot est maintenant reconstruit par le chemin. Corrigé en Python, JS et PHP.
- **Clé de cache incomplète.** `fuzzy`, `max_dist` et `top_k` ne faisaient pas partie de la clé : une recherche exacte
  pouvait renvoyer le résultat mis en cache d'une recherche floue. Les résultats rendus sont désormais des copies.
- **PHP : distance de Levenshtein et minuscules sur octets.** « patisserie » / « pâtisserie » était à distance 2 (au lieu
  de 1) et « É » n'était pas abaissé. Tout passe par `Unicode` (mbstring). **`ext-mbstring` devient requis.**
- **JS : clé structurelle récursive** (coût proportionnel au sous-arbre, exponentiel sur certains vocabulaires) → identifiants de nœuds.
- **C8 — Erreurs avalées.** `search()` ne convertit plus les vraies erreurs (bug de scoring, postings corrompus) en
  « aucun résultat » ; seules les validations d'entrée lèvent volontairement.
- **Remplacement d'un produit.** Réindexer un identifiant existant doublait `N` dans BM25 et laissait des postings
  obsolètes ; le produit est maintenant remplacé proprement. Nouveau `remove_product()`.
- `avgdl` BM25 calculé en O(1) (somme courante) au lieu de O(N) par produit.
- **C7 — Ex æquo non définis.** Règle explicite et commune : score décroissant puis `id` croissant ; tags appariés par (distance, tag).
- Arrondi des scores à 4 décimales exactement égal à `round(x, 4)` de Python dans les trois langages.
- Validation de `top_k < 1` ; en JS, validation de type des champs du catalogue ; en PHP, champ manquant signalé par une exception claire.

### Ajouté
- **C3 — Parité réelle des structures.** DAWG réel et postings delta + VarInt en JavaScript et en PHP (gain mesuré
  −96 % / −94 % sur 500 identifiants).
- **C7 — Jeu de référence croisé** `shared-assets/reference.json` : 229 produits, 261 requêtes, 7 063 arrondis, généré
  par le moteur Python et rejoué par les trois suites.
- **C6 — Dépôt Packagist autonome.** Fixtures embarquées dans `php-engine/tests/fixtures/`, `scripts/sync_php_repo.py`
  pour garder une source unique. Les tests passent hors du monorepo.
- **C4 — Mesures reproductibles** : `benchmarks/` (Python, Node, PHP, DAWG vs Trie) et `docs/benchmarks.md`.
- **C9 — CI GitHub Actions** : trois suites × Linux/Windows, fichiers partagés à jour, garde-fou de complexité
  de l'indexation, workflow de publication par tag.
- **C5 — Licence MIT** et métadonnées complètes (auteur, URLs, classificateurs, `engines`, `sideEffects`).

### Modifié
- **C2 — Hygiène des dépôts.** `.gitignore` ; `node_modules/`, `vendor/`, `dist/`, `egg-info`, caches retirés de l'index git.
- `roadmap.md` et la revue de littérature rangées dans `docs/`.
- README réécrit : tableau fidèle par langage, latences mesurées (la promesse « sub-milliseconde » est retirée), gain du
  DAWG présenté avec ses limites.

## [1.0.0] — 2026-04-09

Première publication : moteur Python, portages TypeScript et PHP.
