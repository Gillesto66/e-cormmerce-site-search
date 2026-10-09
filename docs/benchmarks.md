# Mesures de performance — TagSearch 1.0.1

Toutes les valeurs ci-dessous sont **mesurées**, avec les scripts du dossier [`benchmarks/`](../benchmarks/).
Elles décrivent une machine de développement (portable Windows 11, Python 3.13, Node 22, PHP 8.2), pas un
serveur de production : seuls les **rapports** entre tailles sont transposables, pas les millisecondes.

## Méthode

- Catalogue synthétique déterministe (`benchmarks/synth.py`) : 5 tags par produit, vocabulaire de 1 500 mots.
- Recherche : 300 requêtes préfixées de 2 à 5 lettres tirées dans le vocabulaire, **cache vidé avant chaque requête**
  (les chiffres sont donc ceux du cas non mis en cache).
- Les préfixes courts (2 lettres) ramènent beaucoup de tags et de produits candidats : c'est ce qui explique le p99
  de la recherche préfixée, qui croît avec la taille du catalogue.
- Reproduire : `python benchmarks/run.py`, `node --expose-gc benchmarks/run.mjs`, `php benchmarks/run.php`
  (détail des arguments en tête de chaque script).

## Indexation (constat C1) — Python, avant / après

| Produits | Avant (s) | Rapport | Après (s) | Rapport |
|---:|---:|---:|---:|---:|
| 100 | 3,40 | — | 0,16 | — |
| 200 | 11,05 | ×3,25 | 0,30 | ×1,85 |
| 400 | 42,05 | ×3,81 | 0,41 | ×1,36 |
| 800 | non remesuré ici (242 s dans l'audit) | — | 0,78 | ×1,92 |
| 1 600 | — | — | 0,99 | ×1,26 |
| 3 200 | — | — | 1,60 | ×1,62 |

Avant : chaque doublement coûtait ×3,3 à ×3,8 (quadratique). Après : environ ×1,3 à ×1,9 par doublement (quasi linéaire).
Le garde-fou `python benchmarks/run.py --check-ratio 3.0` échoue si un doublement dépasse ×3 ; il est exécuté par la CI.

## Latence de recherche (cache vide), par langage

Python (3 200 produits) : autocomplétion p50 0,66 ms / p99 26,2 ms ; recherche floue p50 2,10 ms / p99 9,24 ms.
JavaScript (3 200 produits) : autocomplétion p50 0,06 ms / p99 4,5 ms ; floue p50 0,11 ms / p99 1,2 ms.
PHP (3 200 produits) : autocomplétion p50 0,19 ms / p99 19,4 ms ; floue p50 0,69 ms / p99 3,9 ms.

**La promesse « sub-milliseconde » du README 1.0.0 n'est pas tenue partout** : en Python, la recherche floue est de
l'ordre de 1 à 2 ms dès 100 produits, et le p99 des préfixes courts dépasse la milliseconde. JS la tient au p50, pas au p99.

## Mémoire des postings (500 identifiants dans [1 ; 100 000])

| Langage | Structure naïve | delta + VarInt | Gain |
|---|---:|---:|---:|
| Python | `set` : 30 600 octets | 756 octets | −97,5 % |
| JavaScript | `Set` : ≈ 20 560 octets | 806 octets | −96,1 % |
| PHP | `array` : ≈ 12 390 octets | 770 octets | −93,8 % |

## Partage de suffixes du DAWG (constat C10) — **le DAWG de la 1.0.0 n'en était pas un**

La clé structurelle des nœuds contenait le mot entier (`tag`) : aucun nœud terminal ne pouvait être partagé, donc aucun
nœud parent non plus. Mesure sur le code 1.0.0 : **6 827 nœuds pour le DAWG, 6 827 pour un Trie (gain 0 %)**.
Corrigé en 1.0.1 (le mot est reconstruit par le chemin). Nœuds, `python benchmarks/dawg_vs_trie.py` :

| Vocabulaire | Mots | Trie | DAWG | Gain |
|---|---:|---:|---:|---:|
| Synthétique à suffixes répétés | 1 500 | 6 822 | 1 019 | 85,1 % |
| Synthétique à suffixes répétés | 5 000 | 21 120 | 2 249 | 89,4 % |
| Lettres aléatoires (pire cas) | 1 500 | 7 230 | 3 570 | 50,6 % |

Le vocabulaire synthétique est construit à partir d'un petit nombre de syllabes et de suffixes : il **surestime** le
gain réel. Le gain sur un vrai vocabulaire de catalogue n'a pas été mesuré ; il dépend du nombre de suffixes communs.

## `__slots__` (Python uniquement)

Objet standard : 344 octets ; avec `__slots__` : 56 octets (−83,7 %).
