"""
Bibliothèque Python In-Memory Search — Tags E-commerce
=======================================================
Phase 1 : Optimisation mémoire (DAWG, __slots__, VarInt, CompressedPostingsList)
Phase 2 : Ranking hybride multidimensionnel (BM25 + 5 dimensions)
"""

from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from enum import Enum
import math
import sys
import array as _array

# ============================================================
# CONSTANTES ALPHABET (Phase 1)
# ============================================================
ALPHA_SIZE = 38

def _char_index(c: str) -> int:
    if 'a' <= c <= 'z': return ord(c) - ord('a')
    if '0' <= c <= '9': return ord(c) - ord('0') + 26
    if c == '-': return 36
    if c == ' ': return 37
    return -1

def _index_to_char(idx: int) -> str:
    if idx <= 25: return chr(ord('a') + idx)
    if idx <= 35: return chr(ord('0') + idx - 26)
    if idx == 36: return '-'
    return ' '


# ============================================================
# PHASE 1 — TrieNode + Trie (1.1 + 1.2)
# ============================================================

class TrieNode:
    __slots__ = ('children', 'is_terminal', 'tag')

    def __init__(self):
        self.children: list | None = None
        self.is_terminal: bool = False
        self.tag: str | None = None

    def _ensure_children(self):
        if self.children is None:
            self.children = [None] * ALPHA_SIZE

    def get_child(self, c: str) -> 'TrieNode | None':
        if self.children is None: return None
        idx = _char_index(c)
        return None if idx == -1 else self.children[idx]

    def set_child(self, c: str, node: 'TrieNode'):
        self._ensure_children()
        idx = _char_index(c)
        if idx != -1: self.children[idx] = node

    def iter_children(self):
        if self.children is None: return
        for idx, child in enumerate(self.children):
            if child is not None: yield idx, child


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str):
        node = self.root
        for char in word.lower():
            child = node.get_child(char)
            if child is None:
                child = TrieNode()
                node.set_child(char, child)
            node = child
        node.is_terminal = True
        node.tag = word

    def autocomplete(self, prefix: str) -> list[str]:
        node = self.root
        for char in prefix.lower():
            node = node.get_child(char)
            if node is None: return []
        results: list[str] = []
        self._dfs(node, results)
        return results

    def _dfs(self, node: TrieNode, results: list):
        if node.is_terminal: results.append(node.tag)
        for _, child in node.iter_children():
            self._dfs(child, results)

    def fuzzy_search(self, query: str, max_distance: int = 1) -> list[str]:
        query = query.lower()
        results: list[tuple[str, int]] = []
        init_row = list(range(len(query) + 1))
        for idx, child in self.root.iter_children():
            self._fuzzy_dfs(child, _index_to_char(idx), query, init_row, max_distance, results)
        results.sort(key=lambda x: x[1])
        return [tag for tag, _ in results]

    def _fuzzy_dfs(self, node, char, query, prev_row, max_dist, results):
        cur = [prev_row[0] + 1]
        for col in range(1, len(query) + 1):
            cur.append(min(cur[col-1]+1, prev_row[col]+1,
                           prev_row[col-1] + (0 if query[col-1] == char else 1)))
        if min(cur) > max_dist: return
        if cur[-1] <= max_dist and node.is_terminal:
            results.append((node.tag, cur[-1]))
        for idx, child in node.iter_children():
            self._fuzzy_dfs(child, _index_to_char(idx), query, cur, max_dist, results)


# ============================================================
# PHASE 1 — DAWG / FST (1.3)
# ============================================================

class DAWGNode:
    __slots__ = ('children', 'is_terminal', 'tag', 'frozen', '_hash_cache')

    def __init__(self):
        self.children: dict[str, 'DAWGNode'] = {}
        self.is_terminal: bool = False
        self.tag: str | None = None
        self.frozen: bool = False
        self._hash_cache: int | None = None

    def structural_key(self) -> tuple:
        return (self.is_terminal, self.tag,
                tuple(sorted((c, id(n)) for c, n in self.children.items())))

    def __hash__(self):
        if self._hash_cache is None:
            self._hash_cache = hash(self.structural_key())
        return self._hash_cache

    def __eq__(self, other):
        return isinstance(other, DAWGNode) and self.structural_key() == other.structural_key()


class DAWG:
    def __init__(self):
        self.root = DAWGNode()
        self._minimized: dict[tuple, DAWGNode] = {}
        self._last_word: str = ""
        self._unchecked: list[tuple] = []

    def _minimize(self, down_to: int):
        for i in range(len(self._unchecked) - 1, down_to - 1, -1):
            parent, char, child = self._unchecked[i]
            key = child.structural_key()
            if key in self._minimized:
                parent.children[char] = self._minimized[key]
            else:
                child.frozen = True
                self._minimized[key] = child
            self._unchecked.pop()

    def insert(self, word: str):
        word = word.lower()
        if word <= self._last_word and self._last_word:
            raise ValueError(f"DAWG: insertion hors ordre — '{word}' après '{self._last_word}'.")
        common = 0
        for i, (c1, c2) in enumerate(zip(word, self._last_word)):
            if c1 != c2: break
            common = i + 1
        else:
            common = min(len(word), len(self._last_word))
        self._minimize(common)
        node = self.root if not self._unchecked else self._unchecked[-1][2]
        for char in word[common:]:
            new_node = DAWGNode()
            node.children[char] = new_node
            self._unchecked.append((node, char, new_node))
            node = new_node
        node.is_terminal = True
        node.tag = word
        self._last_word = word

    def finish(self):
        self._minimize(0)

    @classmethod
    def build(cls, tags: list[str]) -> 'DAWG':
        dawg = cls()
        for tag in sorted(set(t.lower() for t in tags)):
            dawg.insert(tag)
        dawg.finish()
        return dawg

    def contains(self, word: str) -> bool:
        node = self.root
        for char in word.lower():
            node = node.children.get(char)
            if node is None: return False
        return node.is_terminal

    def autocomplete(self, prefix: str) -> list[str]:
        node = self.root
        for char in prefix.lower():
            node = node.children.get(char)
            if node is None: return []
        results: list[str] = []
        self._dfs(node, results)
        return results

    def _dfs(self, node: DAWGNode, results: list):
        if node.is_terminal: results.append(node.tag)
        for child in node.children.values():
            self._dfs(child, results)

    def fuzzy_search(self, query: str, max_distance: int = 1) -> list[str]:
        query = query.lower()
        results: list[tuple[str, int]] = []
        init_row = list(range(len(query) + 1))
        for char, child in self.root.children.items():
            self._fuzzy_dfs(child, char, query, init_row, max_distance, results)
        results.sort(key=lambda x: x[1])
        return [tag for tag, _ in results]

    def _fuzzy_dfs(self, node, char, query, prev_row, max_dist, results):
        cur = [prev_row[0] + 1]
        for col in range(1, len(query) + 1):
            cur.append(min(cur[col-1]+1, prev_row[col]+1,
                           prev_row[col-1] + (0 if query[col-1] == char else 1)))
        if min(cur) > max_dist: return
        if cur[-1] <= max_dist and node.is_terminal:
            results.append((node.tag, cur[-1]))
        for next_char, child in node.children.items():
            self._fuzzy_dfs(child, next_char, query, cur, max_dist, results)

    def node_count(self) -> int:
        visited: set = set()
        self._count(self.root, visited)
        return len(visited)

    def _count(self, node, visited):
        if id(node) in visited: return
        visited.add(id(node))
        for child in node.children.values():
            self._count(child, visited)


# ============================================================
# PHASE 1 — VarInt + CompressedPostingsList (1.4)
# ============================================================

class VarInt:
    @staticmethod
    def encode(value: int) -> bytes:
        buf = []
        while True:
            byte = value & 0x7F
            value >>= 7
            buf.append(byte | 0x80 if value else byte)
            if not value: break
        return bytes(buf)

    @staticmethod
    def decode(data: bytes, offset: int = 0) -> tuple[int, int]:
        result, shift = 0, 0
        while True:
            byte = data[offset]; offset += 1
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80): break
            shift += 7
        return result, offset


class CompressedPostingsList:
    def __init__(self):
        self._compressed: bytes = b''
        self._pending: list[int] = []
        self._dirty: bool = False

    def add(self, product_id: int):
        self._pending.append(product_id)
        self._dirty = True

    def flush(self):
        if not self._dirty: return
        all_ids = sorted(set(self.decompress()) | set(self._pending))
        buf = bytearray()
        prev = 0
        for pid in all_ids:
            buf += VarInt.encode(pid - prev)
            prev = pid
        self._compressed = bytes(buf)
        self._pending.clear()
        self._dirty = False

    def decompress(self) -> list[int]:
        ids, offset, current = [], 0, 0
        while offset < len(self._compressed):
            delta, offset = VarInt.decode(self._compressed, offset)
            current += delta
            ids.append(current)
        if self._pending:
            ids = sorted(set(ids) | set(self._pending))
        return ids

    def __contains__(self, pid: int) -> bool:
        return pid in self.decompress()

    def memory_bytes(self) -> int:
        return len(self._compressed) + len(self._pending) * 28


# ============================================================
# CACHE LRU
# ============================================================

class LRUCache:
    def __init__(self, capacity: int):
        self.cache: OrderedDict = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache: return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache: self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)



# ============================================================
# PHASE 2 — MÉTADONNÉES PRODUIT (structures mémoire-efficaces)
# ============================================================

class ProductType(Enum):
    """
    Encodé comme uint8 (0/1) dans ProductMeta.
    Permet un filtre O(1) par comparaison d'entier, sans string matching.
    """
    PHYSICAL = 0
    DIGITAL  = 1


@dataclass
class ProductMeta:
    """
    Métadonnées produit stockées dans un dataclass compact.

    Choix de types :
        - product_type : Enum → 1 byte logique (comparaison O(1))
        - niche        : str interné (sys.intern) → pointeur partagé si même niche
        - price        : float → 8 bytes, accès O(1) pour les comparaisons de plage
        - location     : str | None → None si non applicable (produits digitaux)
        - avg_rating   : float → 8 bytes
        - review_count : int → pondère la fiabilité de avg_rating (loi des grands nombres)

    Pourquoi ne pas utiliser __slots__ ici ?
        dataclass + __slots__ est supporté depuis Python 3.10 via @dataclass(slots=True).
        On l'active pour économiser ~200 bytes/instance sur de grands catalogues.
    """
    name         : str
    product_type : ProductType
    niche        : str
    price        : float
    location     : str | None   # None pour les produits digitaux
    avg_rating   : float        # 0.0 – 5.0
    review_count : int          # Nombre d'avis : pondère la fiabilité du rating
    tags         : list[str]


# ============================================================
# PHASE 2 — BM25 IN-MEMORY
# ============================================================

class BM25Index:
    """
    BM25 (Okapi BM25) in-memory sur les tags des produits.

    Pourquoi BM25 plutôt que TF-IDF simple ?
        TF-IDF récompense linéairement la fréquence des termes.
        BM25 sature la fréquence (paramètre k1) : un tag répété 10 fois
        ne vaut pas 10× un tag répété 1 fois. Plus réaliste pour des tags.

    Paramètres MVP :
        k1 = 1.5  — saturation de la fréquence des termes (standard e-commerce)
        b  = 0.75 — normalisation par longueur du document (standard)

    Structure mémoire :
        - tf   : dict[tag → dict[product_id → count]]  (fréquence brute)
        - df   : dict[tag → int]                        (document frequency)
        - N    : int                                     (nombre de produits)
        - avgdl: float                                   (longueur moyenne des docs)

    Complexité :
        Indexation : O(|tags|) par produit
        Score BM25  : O(|matched_tags|) par requête
    """

    K1 = 1.5
    B  = 0.75

    def __init__(self):
        self.tf:    dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.df:    dict[str, int]            = defaultdict(int)
        self.dl:    dict[int, int]            = {}   # longueur doc (nb tags) par produit
        self.N:     int                       = 0
        self.avgdl: float                     = 0.0

    def index(self, product_id: int, tags: list[str]):
        """Indexe les tags d'un produit. Recalcule avgdl à chaque ajout."""
        tags_lower = [t.lower() for t in tags]
        self.dl[product_id] = len(tags_lower)
        self.N += 1
        self.avgdl = sum(self.dl.values()) / self.N

        for tag in tags_lower:
            self.tf[tag][product_id] += 1
            # df : on ne compte qu'une fois par produit
            if self.tf[tag][product_id] == 1:
                self.df[tag] += 1

    def score(self, product_id: int, query_tags: list[str]) -> float:
        """
        Calcule le score BM25 pour un produit donné et une liste de tags requête.

        Formule :
            BM25(d, Q) = Σ IDF(qi) × [ tf(qi,d) × (k1+1) ] / [ tf(qi,d) + k1×(1-b+b×dl/avgdl) ]

        IDF(qi) = log( (N - df(qi) + 0.5) / (df(qi) + 0.5) + 1 )
            Le +1 évite les valeurs négatives pour les termes très fréquents.
        """
        if self.N == 0 or self.avgdl == 0:
            return 0.0

        total = 0.0
        dl_d  = self.dl.get(product_id, 0)

        for tag in query_tags:
            tag = tag.lower()
            tf_val = self.tf[tag].get(product_id, 0)
            if tf_val == 0:
                continue
            df_val = self.df.get(tag, 0)
            idf = math.log((self.N - df_val + 0.5) / (df_val + 0.5) + 1)
            norm = tf_val * (self.K1 + 1) / (tf_val + self.K1 * (1 - self.B + self.B * dl_d / self.avgdl))
            total += idf * norm

        return total



# ============================================================
# PHASE 2 — PRÉFÉRENCES UTILISATEUR & SCORING MULTIDIMENSIONNEL
# ============================================================

@dataclass
class SearchPreferences:
    """
    Préférences utilisateur injectées au moment de la requête.
    Toutes les valeurs sont optionnelles (None = neutre, pas de filtre).

    Coefficients par défaut (MVP) — justification :
        w_bm25     = 1.0  : base normalisée, les autres sont des multiplicateurs
        w_quality  = 1.5  : exposant sur (rating/5)^1.5 — pénalise sévèrement < 3/5
        w_type     = 0.1  : pénalité si type mismatch (filtre doux, pas dur)
        w_price    = 0.2  : ajustement ±20% selon budget
        w_proximity= 0.15 : bonus +15% si dans la zone de livraison
    """
    preferred_type    : ProductType | None = None   # Filtre doux sur Physical/Digital
    preferred_niche   : str | None         = None   # Boost si même niche
    max_price         : float | None       = None   # Exclusion si prix > max
    min_price         : float | None       = None   # Exclusion si prix < min
    user_location     : str | None         = None   # Zone de livraison préférée
    min_rating        : float              = 0.0    # Seuil dur : exclut les produits en dessous


def calculate_final_score(
    product_id   : int,
    meta         : ProductMeta,
    bm25_raw     : float,
    prefs        : SearchPreferences,
) -> float | None:
    """
    Fonction de re-ranking multidimensionnel Phase 2.

    Retourne None si le produit doit être EXCLU (filtres durs).
    Retourne un float (score final) sinon.

    Architecture du score :
        final = bm25_normalized × quality_multiplier × type_factor × proximity_bonus × price_factor

    Pourquoi multiplicatif et non additif ?
        Un score additif permet à un produit mal noté de compenser avec un bon BM25.
        Un score multiplicatif garantit qu'un mauvais signal (ex: note 1/5) effondre
        le score final, quelle que soit la pertinence textuelle.

    Détail de chaque dimension :

    1. BM25 normalisé (0–1) :
        On normalise par un plafond empirique (BM25_CAP=10.0) pour rester dans [0,1].
        Évite qu'un produit avec 50 tags domine juste par volume.

    2. quality_multiplier = (rating / 5.0) ** 1.5 :
        Courbe convexe. Exemples :
            5.0/5 → 1.000  (neutre)
            4.5/5 → 0.882
            3.0/5 → 0.465  (pénalité significative)
            2.0/5 → 0.226  (quasi-exclu)
            1.0/5 → 0.057  (exclu de facto)
        Le review_count pondère la fiabilité : un produit avec 3 avis à 5.0
        est moins fiable qu'un produit avec 500 avis à 4.5.
        → bayesian_rating = (count × rating + prior_mean × prior_weight) / (count + prior_weight)

    3. type_factor :
        1.0 si pas de préférence ou si match.
        0.1 si mismatch (filtre doux : le produit reste visible mais relégué).
        Permet de distinguer E-book (Digital) vs Robot pâtissier (Physical)
        même s'ils partagent le tag "cuisine".

    4. proximity_bonus :
        1.15 si user_location correspond à product.location.
        1.0  sinon (neutre).
        None location sur produit digital → toujours 1.0 (livraison universelle).

    5. price_factor :
        Filtre dur : exclut si hors plage [min_price, max_price].
        Filtre doux : léger boost pour les produits dans la moitié basse du budget.
    """

    BM25_CAP      = 10.0   # Plafond de normalisation BM25
    PRIOR_MEAN    = 3.5    # Note a priori (moyenne marché e-commerce)
    PRIOR_WEIGHT  = 10.0   # Équivalent à 10 avis fictifs pour lisser les petits corpus

    # ── Filtres DURS (exclusion immédiate) ──────────────────────────────────

    # Filtre prix
    if prefs.max_price is not None and meta.price > prefs.max_price:
        return None
    if prefs.min_price is not None and meta.price < prefs.min_price:
        return None

    # Filtre note minimale
    if meta.avg_rating < prefs.min_rating:
        return None

    # ── Dimension 1 : BM25 normalisé ────────────────────────────────────────
    bm25_norm = min(bm25_raw / BM25_CAP, 1.0)
    # Plancher à 0.05 pour que les produits avec correspondance exacte de tag
    # (mais BM25 faible car tag très fréquent) restent visibles
    bm25_norm = max(bm25_norm, 0.05)

    # ── Dimension 2 : Qualité (Bayesian rating + review_count) ──────────────
    bayesian_rating = (
        (meta.review_count * meta.avg_rating + PRIOR_MEAN * PRIOR_WEIGHT)
        / (meta.review_count + PRIOR_WEIGHT)
    )
    quality_multiplier = (bayesian_rating / 5.0) ** 1.5

    # ── Dimension 3 : Type (Physical vs Digital) ────────────────────────────
    if prefs.preferred_type is not None and meta.product_type != prefs.preferred_type:
        type_factor = 0.1   # Filtre doux : relégué, pas exclu
    else:
        type_factor = 1.0

    # Boost niche : +20% si la niche correspond exactement
    niche_boost = 1.2 if (
        prefs.preferred_niche is not None
        and meta.niche.lower() == prefs.preferred_niche.lower()
    ) else 1.0

    # ── Dimension 4 : Proximité ─────────────────────────────────────────────
    if meta.location is None:
        # Produit digital : livraison universelle
        proximity_bonus = 1.0
    elif prefs.user_location is not None and meta.location.lower() == prefs.user_location.lower():
        proximity_bonus = 1.15
    else:
        proximity_bonus = 1.0

    # ── Dimension 5 : Prix (filtre doux) ────────────────────────────────────
    # Léger boost si le produit est dans la moitié basse du budget max
    if prefs.max_price is not None and prefs.max_price > 0:
        price_ratio = meta.price / prefs.max_price
        price_factor = 1.1 if price_ratio <= 0.5 else 1.0
    else:
        price_factor = 1.0

    # ── Score final (multiplicatif) ──────────────────────────────────────────
    final = bm25_norm * quality_multiplier * type_factor * niche_boost * proximity_bonus * price_factor
    return round(final, 4)



# ============================================================
# PHASE 2 — MOTEUR DE RECHERCHE MULTIDIMENSIONNEL
# ============================================================

class SearchEngineV2:
    """
    Moteur Phase 2 : DAWG + BM25 + scoring multidimensionnel.

    Flux de recherche :
        1. DAWG fuzzy/autocomplete → matched_tags (O(L) avec pruning)
        2. CompressedPostingsList  → candidate product_ids (O(n) décompression)
        3. BM25Index.score()       → score textuel par produit
        4. calculate_final_score() → re-ranking avec les 5 dimensions
        5. LRUCache                → mise en cache du résultat final
    """

    def __init__(self, cache_size: int = 200):
        self._all_tags: list[str] = []
        self.dawg: DAWG = DAWG()
        self.inverted_index: dict[str, CompressedPostingsList] = {}
        self.catalog: dict[int, ProductMeta] = {}
        self.bm25: BM25Index = BM25Index()
        self.cache: LRUCache = LRUCache(capacity=cache_size)

    def add_product(self, product_id: int, meta: ProductMeta):
        """
        Indexe un produit avec ses métadonnées complètes.
        Interne sys.intern sur la niche pour partager les pointeurs de string.
        """
        meta.niche = sys.intern(meta.niche.lower())
        self.catalog[product_id] = meta

        for tag in meta.tags:
            tag_lower = tag.lower()
            if tag_lower not in self.inverted_index:
                self.inverted_index[tag_lower] = CompressedPostingsList()
                self._all_tags.append(tag_lower)
            self.inverted_index[tag_lower].add(product_id)

        self.bm25.index(product_id, meta.tags)

        for pl in self.inverted_index.values():
            pl.flush()
        self.dawg = DAWG.build(self._all_tags)
        self.cache = LRUCache(capacity=self.cache.capacity)

    def search(
        self,
        query       : str,
        prefs       : SearchPreferences | None = None,
        fuzzy       : bool = True,
        max_dist    : int  = 1,
        top_k       : int  = 10,
    ) -> list[dict]:
        """
        Recherche multidimensionnelle.

        Retourne une liste de dicts triés par score décroissant :
            [{ id, name, type, niche, price, rating, score }, ...]
        """
        if prefs is None:
            prefs = SearchPreferences()

        cache_key = f"{query.lower()}|{prefs}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached, "CACHÉ"

        # 1. Récupération des tags via DAWG
        query_lower = query.lower()
        if fuzzy:
            matched_tags = self.dawg.fuzzy_search(query_lower, max_dist)
        else:
            matched_tags = self.dawg.autocomplete(query_lower)

        if not matched_tags:
            return [], "MISS"

        # 2. Collecte des candidats via inverted index
        candidate_ids: set[int] = set()
        for tag in matched_tags:
            if tag in self.inverted_index:
                candidate_ids.update(self.inverted_index[tag].decompress())

        # 3. BM25 + re-ranking multidimensionnel
        results = []
        for pid in candidate_ids:
            meta = self.catalog[pid]
            bm25_raw = self.bm25.score(pid, matched_tags)
            final_score = calculate_final_score(pid, meta, bm25_raw, prefs)

            if final_score is None:
                continue  # Exclu par filtre dur

            results.append({
                'id'    : pid,
                'name'  : meta.name,
                'type'  : meta.product_type.name,
                'niche' : meta.niche,
                'price' : meta.price,
                'rating': meta.avg_rating,
                'reviews': meta.review_count,
                'score' : final_score,
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        final_list = results[:top_k]

        self.cache.put(cache_key, final_list)
        return final_list, "CALCULÉ"



# ============================================================
# PHASE 2 — DATASET E-COMMERCE (10 produits variés)
# ============================================================

CATALOG = [
    # id, ProductMeta(name, type, niche, price, location, rating, reviews, tags)
    (1, ProductMeta(
        name="Clavier Mécanique RGB Pro",
        product_type=ProductType.PHYSICAL,
        niche="gaming",
        price=129.99,
        location="France",
        avg_rating=4.8, review_count=342,
        tags=["clavier", "gaming", "rgb", "mécanique", "tech"]
    )),
    (2, ProductMeta(
        name="Souris Gaming Sans Fil",
        product_type=ProductType.PHYSICAL,
        niche="gaming",
        price=79.99,
        location="France",
        avg_rating=4.2, review_count=187,
        tags=["souris", "gaming", "sans-fil", "tech"]
    )),
    (3, ProductMeta(
        name="Casque Audio Bluetooth",
        product_type=ProductType.PHYSICAL,
        niche="audio",
        price=89.99,
        location="Belgique",
        avg_rating=3.9, review_count=95,
        tags=["casque", "audio", "bluetooth", "sans-fil"]
    )),
    (4, ProductMeta(
        name="Robot Pâtissier 1200W",
        product_type=ProductType.PHYSICAL,
        niche="cuisine",
        price=349.00,
        location="France",
        avg_rating=4.6, review_count=521,
        tags=["robot", "cuisine", "pâtisserie", "électroménager"]
    )),
    (5, ProductMeta(
        name="E-book : Maîtriser la Pâtisserie",
        product_type=ProductType.DIGITAL,
        niche="cuisine",
        price=14.99,
        location=None,   # Digital : livraison universelle
        avg_rating=4.3, review_count=88,
        tags=["ebook", "cuisine", "pâtisserie", "recettes", "digital"]
    )),
    (6, ProductMeta(
        name="Formation SaaS : Growth Hacking",
        product_type=ProductType.DIGITAL,
        niche="saas",
        price=199.00,
        location=None,
        avg_rating=4.7, review_count=63,
        tags=["formation", "saas", "growth", "marketing", "digital"]
    )),
    (7, ProductMeta(
        name="Sérum Visage Anti-Âge",
        product_type=ProductType.PHYSICAL,
        niche="beauté",
        price=45.00,
        location="France",
        avg_rating=2.8, review_count=12,   # Peu d'avis, note faible → Bayesian pénalise
        tags=["sérum", "beauté", "soin", "visage"]
    )),
    (8, ProductMeta(
        name="Palette Maquillage Pro",
        product_type=ProductType.PHYSICAL,
        niche="beauté",
        price=32.50,
        location="Belgique",
        avg_rating=4.5, review_count=276,
        tags=["maquillage", "beauté", "palette", "cosmétique"]
    )),
    (9, ProductMeta(
        name="Tapis de Yoga Antidérapant",
        product_type=ProductType.PHYSICAL,
        niche="sport",
        price=29.99,
        location="France",
        avg_rating=4.1, review_count=430,
        tags=["yoga", "sport", "tapis", "fitness"]
    )),
    (10, ProductMeta(
        name="Abonnement App Méditation",
        product_type=ProductType.DIGITAL,
        niche="sport",
        price=9.99,
        location=None,
        avg_rating=4.4, review_count=1200,
        tags=["méditation", "sport", "bien-être", "digital", "abonnement"]
    )),
]


# ============================================================
# PHASE 2 — TESTS & DÉMONSTRATIONS
# ============================================================

def run_phase2_tests():
    engine = SearchEngineV2(cache_size=50)
    for pid, meta in CATALOG:
        engine.add_product(pid, meta)

    sep = "=" * 60

    print(sep)
    print("PHASE 2 — TESTS RANKING MULTIDIMENSIONNEL")
    print(sep)

    # ── Test 1 : Conflit "pertinent mais mal noté" vs "populaire" ──────────
    print("\n── Test 1 : Tag 'cuisine' — Physical vs Digital, sans filtre ──")
    print("   Attendu : Robot pâtissier (4.6★, 521 avis) > E-book (4.3★, 88 avis)")
    print("   Le sérum beauté NE doit PAS apparaître.\n")
    results, status = engine.search("cuisine")
    for r in results:
        print(f"   [{r['score']:.4f}] {r['name']} ({r['type']}) — {r['rating']}★ ({r['reviews']} avis) — {r['price']}€")

    # ── Test 2 : Filtre TYPE Digital — E-book doit passer devant ───────────
    print(f"\n── Test 2 : Tag 'cuisine' avec préférence TYPE=DIGITAL ──")
    print("   Attendu : E-book en tête, Robot pâtissier relégué (×0.1)\n")
    prefs_digital = SearchPreferences(preferred_type=ProductType.DIGITAL)
    results, status = engine.search("cuisine", prefs=prefs_digital)
    for r in results:
        print(f"   [{r['score']:.4f}] {r['name']} ({r['type']}) — {r['rating']}★")

    # ── Test 3 : Filtre prix + localisation ────────────────────────────────
    print(f"\n── Test 3 : Tag 'gaming' — Budget max 100€, localisation France ──")
    print("   Attendu : Souris (79.99€) > Clavier (129.99€, exclu par prix)\n")
    prefs_budget = SearchPreferences(max_price=100.0, user_location="France")
    results, status = engine.search("gaming", prefs=prefs_budget)
    for r in results:
        print(f"   [{r['score']:.4f}] {r['name']} — {r['price']}€ — {r['rating']}★")

    # ── Test 4 : Note minimale (filtre dur) ────────────────────────────────
    print(f"\n── Test 4 : Tag 'beauté' — Note minimale 4.0 ──")
    print("   Attendu : Sérum (2.8★) exclu, Palette (4.5★) seule\n")
    prefs_quality = SearchPreferences(min_rating=4.0)
    results, status = engine.search("beauté", prefs=prefs_quality)
    for r in results:
        print(f"   [{r['score']:.4f}] {r['name']} — {r['rating']}★ ({r['reviews']} avis)")

    # ── Test 5 : Fuzzy search + ranking ────────────────────────────────────
    print(f"\n── Test 5 : Fuzzy 'gaiming' (faute) — max_dist=1 ──")
    print("   Attendu : résultats gaming malgré la faute de frappe\n")
    results, status = engine.search("gaiming", fuzzy=True, max_dist=1)
    for r in results:
        print(f"   [{r['score']:.4f}] {r['name']} — {r['rating']}★")

    # ── Test 6 : Bayesian rating — produit peu noté pénalisé ───────────────
    print(f"\n── Test 6 : Démonstration Bayesian Rating ──")
    print("   Sérum (2.8★, 12 avis) vs Palette (4.5★, 276 avis)")
    from dataclasses import replace
    PRIOR_MEAN, PRIOR_WEIGHT = 3.5, 10.0
    for pid, label in [(7, "Sérum"), (8, "Palette")]:
        m = engine.catalog[pid]
        br = (m.review_count * m.avg_rating + PRIOR_MEAN * PRIOR_WEIGHT) / (m.review_count + PRIOR_WEIGHT)
        qm = (br / 5.0) ** 1.5
        print(f"   {label:10s} : raw={m.avg_rating}★ ({m.review_count} avis) → bayesian={br:.3f} → quality_mult={qm:.3f}")


if __name__ == "__main__":
    run_phase2_tests()
