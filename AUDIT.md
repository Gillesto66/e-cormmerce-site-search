# Audit d'amélioration — TagSearch 1.0.0

> Audit réalisé le 2026-10-09, **par exécution** (tests lancés, mesures faites, registres interrogés) et non par simple lecture.
> Périmètre : ce monorepo (`python-engine/`, `js-engine/`, `php-engine/`, `shared-assets/`), le dépôt Packagist voisin `../php-e-cormmerce-search`, et les trois paquets publiés.
> Aucun fichier de code n'a été modifié : les corrections sont **prescrites** ici, à appliquer ensuite.
> Machine de mesure : portable Windows 11, Python 3.13, Node 22, PHP 8.2. Les durées sont indicatives ; les **rapports** entre tailles, eux, sont fiables.

---

## 1. Verdict

**Une bibliothèque saine dans son idée et dans son scoring, mais dont l'indexation ne passe pas à l'échelle et dont la promesse « même moteur, trois langages » est en partie fausse.**

À corriger avant d'envoyer du public dessus : le coût d'indexation (C1), les affirmations de performance du README (C3, C4), l'absence de licence (C5) et le dépôt PHP qui échoue à ses propres tests (C6).

### Ce qui a été vérifié et tient

| Point | Résultat |
|---|---|
| Paquets publiés | `tagsearch` 1.0.0 sur PyPI (2026-04-09), `tagsearch-js` 1.0.0 sur npm (2026-04-10, mainteneur `gillesto66`), `tagsearch/php-engine` v1.0.0 sur Packagist (2026-04-10) |
| Tests Python | 19 passent |
| Tests JS (Vitest) | 13 passent ; `tsc --noEmit` sans erreur |
| Tests PHP (monorepo) | 36 tests, 61 assertions, tous verts |
| Zéro dépendance runtime | vrai pour les trois moteurs |
| Gain mémoire d'un nœud `__slots__` | **83 %** mesuré (336 octets pour un objet standard, 56 avec `__slots__`) : le README dit vrai |
| Compression delta + VarInt des postings | **98 %** mesuré (500 identifiants : 32 984 octets pour un `set`, 500 octets compressés) : le README dit vrai |
| Formule de scoring | publique, documentée, et identique dans les trois langages sur le jeu de test commun |

---

## 2. Constats, par gravité

### C1 — L'indexation est quadratique (critique)

`SearchEngine.add_product` (`python-engine/tagsearch/engine.py:95-127`) **reconstruit tout le DAWG et vide toutes les listes de postings à chaque produit ajouté**. `load_catalog` appelle `add_product` produit par produit. Le même défaut existe en JS (`js-engine/src/engine.ts:65`, `this.dawg = DAWG.build(this.allTags)` dans `addProduct`) — alors que le commentaire d'en-tête du fichier annonce « reconstruction DAWG en batch », ce qui est faux.

Mesure (5 tags par produit, vocabulaire de 1 500 mots, Python) :

| Produits | Temps d'indexation | Rapport au palier précédent |
|---:|---:|---:|
| 100 | 4,5 s | — |
| 200 | 20,4 s | ×4,5 |
| 400 | 67,8 s | ×3,3 |
| 800 | 242,3 s | ×3,6 |

Chaque doublement coûte environ ×3,5 : c'est du **quadratique**. À 10 000 produits (un petit catalogue réel), l'extrapolation donne plusieurs heures. Pour une bibliothèque vendue comme « intégration directe dans une application existante », c'est le défaut principal.

**Correction prescrite.**
1. Séparer l'ajout de l'indexation : `add_product` ne fait que remplir `catalog`, `inverted_index` et BM25, et marque l'index « sale ».
2. Reconstruire le DAWG **une seule fois**, paresseusement au premier `search()` si l'index est sale, ou explicitement via `commit()` / `rebuild()`.
3. `load_catalog` appelle une méthode d'ajout en lot (`add_products(iterable)`) qui reconstruit une fois à la fin.
4. Ne vider (`flush`) que les listes de postings modifiées, pas toutes.
5. Appliquer la même correction en JS et en PHP. Ajouter un test de non-régression de complexité : indexer N puis 2N produits et exiger un rapport de temps inférieur à ×3.

### C2 — Les dépôts versionnent `node_modules` et `vendor` (élevé)

`git ls-files` du monorepo contient **1 154 fichiers de `node_modules`** et 72 de `vendor/`, plus `js-engine/dist/`, `php-engine/.phpunit.result.cache` et des caches Vite. Le dépôt `php-e-cormmerce-search` versionne 44 fichiers de `vendor/`. Il n'existe **aucun `.gitignore`**. Conséquences : dépôt gonflé, diff illisibles, et chaque lancement de tests modifie des fichiers suivis (cela s'est produit pendant cet audit ; les fichiers ont été remis à l'état commité).

**Correction prescrite.**
1. Créer un `.gitignore` : `node_modules/`, `vendor/`, `dist/` (si publié par CI), `__pycache__/`, `*.egg-info/`, `.phpunit.result.cache`, `.vite/`, `coverage/`.
2. `git rm -r --cached js-engine/node_modules php-engine/vendor` (et le même dans le dépôt PHP), puis commit.
3. Garder `package-lock.json` et `composer.lock` (utiles pour des builds reproductibles) ; décider si `dist/` est compilé par la CI plutôt que commité.

### C3 — « Même moteur dans trois langages » : vrai pour le scoring, faux pour la structure (élevé)

| | Python | JavaScript | PHP |
|---|---|---|---|
| Autocomplétion / flou | DAWG (algorithme de Daciuk) | DAWG | **Trie en tableau associatif**, pas de DAWG (`SearchEngine.php:145`) |
| Postings | delta + VarInt (98 % mesurés) | `Set` natif | tableaux PHP |
| Nœuds `__slots__` | oui | sans objet | sans objet |
| Cache LRU | oui | oui | oui |

Les gains mémoire vantés dans le README (DAWG, VarInt, `__slots__`) ne concernent donc **que Python**. Un utilisateur de `tagsearch-js` ou de `tagsearch/php-engine` n'en bénéficie pas. Les deux autres moteurs sont des portages fonctionnels du scoring, pas des portages de l'optimisation.

**Correction prescrite.** Réécrire la section « Apport au monde du développement » du README en distinguant ce qui est vrai pour chaque langage (tableau ci-dessus). Annoncer Python comme moteur de référence **optimisé** et JS/PHP comme portages **fonctionnels** ; ou porter réellement le DAWG et la compression, en tant que chantier annoncé.

### C4 — La latence « sub-milliseconde » n'est pas tenue (moyen)

Le README promet une « latence sub-milliseconde pour l'autocomplétion et la recherche floue » (et « < 0,5 ms » pour scorer 100 candidats). Mesure Python, requêtes préfixées de 2 à 5 lettres, 300 requêtes par taille :

| Produits | Recherche p50 / p99 | Recherche floue p50 / p99 | Mémoire de l'index |
|---:|---:|---:|---:|
| 100 | 1,04 / 1,82 ms | 1,15 / 1,83 ms | 1,7 Mo |
| 200 | 2,04 / 11,41 ms | 2,22 / 5,25 ms | 2,4 Mo |
| 400 | 3,06 / 6,71 ms | 3,08 / 7,66 ms | 3,8 Mo |
| 800 | 3,61 / 7,59 ms | 3,61 / 8,87 ms | 4,7 Mo |

La latence est de l'ordre de **1 à 4 ms** et croît avec la taille du catalogue. Les requêtes sont tirées au hasard (donc très majoritairement **sans cache**) ; un résultat en cache est bien plus rapide. Le vocabulaire de ce test (1 500 mots aléatoires) est défavorable à la recherche floue : un vrai catalogue de tags aura une distribution différente. Ces chiffres restent un ordre de grandeur honnête, pas un benchmark officiel.

**Correction prescrite.** Remplacer « sub-milliseconde » par la mesure réelle avec sa méthode ; publier un script de benchmark reproductible (`benchmarks/run.py`) et un tableau par taille de catalogue ; ajouter une vérification de la borne dans la CI.

### C5 — Aucune licence, métadonnées de paquet vides (élevé pour une diffusion publique)

Il n'y a **pas de fichier `LICENSE`** dans le monorepo. Sans licence, le code est légalement « tous droits réservés » : personne ne peut l'utiliser. Les paquets publiés affichent des métadonnées vides : PyPI sans auteur ni URL de projet, npm sans `repository`, Packagist sans auteurs. Aucun lien du paquet vers le dépôt ou la documentation.

**Correction prescrite.**
1. Choisir une licence (MIT ou Apache-2.0, comme SafeRoute qui est en MIT) et ajouter `LICENSE` à la racine **et** dans chaque paquet.
2. Renseigner `license`, `authors`, `urls` / `homepage`, `repository`, `keywords`, `classifiers` dans `pyproject.toml`, `package.json` et `composer.json`.
3. Publier une version corrective **1.0.1** de chaque paquet pour que les métadonnées apparaissent sur les registres.

### C6 — Le dépôt Packagist échoue à ses propres tests, et le code est dupliqué (élevé)

Le paquet Packagist est servi par le dépôt `php-e-cormmerce-search`, distinct de `php-engine/` du monorepo. Lancer ses tests donne :

```
RuntimeException: Catalogue introuvable : …/php-e-cormmerce-search/tests/../../shared-assets/catalog.json
```

Le test croisé cherche `shared-assets/catalog.json`, qui n'existe que dans le monorepo. Le code source des deux copies PHP est identique aux commentaires d'en-tête près (une ligne d'attribution, plus des fins de ligne), mais **rien n'empêche leur dérive**.

**Correction prescrite.**
1. Une seule source de vérité : soit publier Packagist depuis le monorepo (sous-dépôt en lecture seule via `git subtree split` ou un workflow CI), soit copier automatiquement `php-engine/` dans le dépôt Packagist à chaque release.
2. Dans tous les cas, copier `catalog.json` dans `tests/fixtures/` du paquet PHP, et faire pointer le test dessus, pour qu'il passe en dehors du monorepo.
3. Aligner la section « Installation » du README PHP, qui référence aussi `../shared-assets/catalog.json`.

### C7 — La preuve de parité entre langages est mince (moyen)

Le jeu partagé `shared-assets/catalog.json` contient **10 produits et 5 cas de test croisés**. C'est peu pour garantir des résultats « identiques au millième près » : les cas limites (requête vide, accents, ex æquo de score, produits sans localisation, `max_dist` > 1, cache) ne sont pas couverts de façon croisée.

**Correction prescrite.**
1. Générer un jeu de référence plus large (au moins 200 produits, 100 requêtes, avec ex æquo, accents et fautes de frappe) **depuis le moteur Python**, le figer en JSON avec ses scores attendus, et le faire rejouer par JS et PHP.
2. Définir explicitement la règle de départage des ex æquo (aujourd'hui dépendante du tri de chaque langage).

### C8 — Erreurs avalées dans la recherche (moyen)

`engine.py` (lignes 190, 204, 220) capture `Exception` et renvoie `[], "MISS"`. Une vraie erreur (bug de scoring, donnée corrompue) est donc indiscernable d'une recherche sans résultat.

**Correction prescrite.** Ne capturer que les exceptions attendues ; laisser les autres remonter, ou renvoyer un statut distinct (`"ERREUR"`) et journaliser au niveau `error` avec la requête.

### C9 — Pas de CI, pas de tests de performance (moyen)

Aucun `.github/`. Les trois suites ne tournent nulle part automatiquement, les paquets ont été publiés à la main.

**Correction prescrite.** Un workflow GitHub Actions avec trois jobs (pytest, vitest + `tsc`, phpunit) sur Linux et Windows ; un job de benchmark qui échoue si l'indexation de 2N produits dépasse ×3 le temps de N ; publication automatisée par tag (PyPI et npm en « trusted publishing », Packagist par webhook).

### C10 — Points mineurs

- `python-engine/pyproject.toml` : pas de `license`, `readme`, `authors`, `classifiers`.
- `js-engine/package.json` : pas de champ `engines` ni de `sideEffects: false` ; `files` n'inclut pas `LICENSE`.
- `revu_de_litérature.txt` (55 Ko) et `roadmap.md` sont à la racine du dépôt public ; les ranger dans `docs/`.
- Le DAWG « 30-50 % moins de nœuds qu'un Trie » du README **n'a pas été vérifié** ici (mesurable avec `DAWG.node_count()` contre un Trie de même vocabulaire) : à mesurer ou à reformuler.

---

## 3. Plan d'exécution recommandé

| Ordre | Chantier | Constats | Effort |
|---:|---|---|---|
| 1 | Licence, `.gitignore`, retrait de `node_modules`/`vendor` | C2, C5 | 1 h |
| 2 | Indexation en lot + test de complexité (Python, JS, PHP) | C1 | 0,5 à 1 jour |
| 3 | Dépôt PHP : source unique et fixture locale | C6 | 2 h |
| 4 | README honnête (tableau par langage, latences mesurées) + script de benchmark | C3, C4 | 3 h |
| 5 | Jeu de référence croisé élargi | C7 | 0,5 jour |
| 6 | Erreurs explicites, CI GitHub Actions | C8, C9 | 0,5 jour |
| 7 | Release 1.0.1 de chaque paquet avec métadonnées complètes | C5 | 1 h |

## 4. Limites de cet audit

- Les latences sont celles d'une machine de développement, sur un catalogue synthétique. Aucun test en charge concurrente.
- Seul le moteur Python a été mesuré à l'échelle ; la croissance de l'indexation JS et PHP est déduite du code, pas mesurée.
- Le DAWG « 30-50 % » n'a pas été vérifié (voir C10).
- La sécurité n'a pas été auditée (la bibliothèque n'a ni réseau, ni accès disque en dehors de `load_catalog`).
