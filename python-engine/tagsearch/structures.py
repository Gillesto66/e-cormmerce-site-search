"""
tagsearch.structures
====================
Réalisée par Gillesto66 & Kiro
Structures de données bas niveau (Phase 1) :
  - TrieNode / Trie       : __slots__ + tableau fixe O(1)
  - DAWGNode / DAWG       : graphe acyclique minimal (Daciuk), partage de suffixes
  - VarInt                : encodage variable-length integer
  - CompressedPostingsList: delta-encoding + VarInt
  - LRUCache              : OrderedDict-based O(1) get/put
"""

from __future__ import annotations
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

# ── Alphabet ────────────────────────────────────────────────────────────────
ALPHA_SIZE = 38  # a-z(0-25), 0-9(26-35), -(36), espace(37)


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


# ── Trie (Phase 1.1 + 1.2) ──────────────────────────────────────────────────

class TrieNode:
    """Nœud Trie : __slots__ + tableau fixe de 38 pointeurs (lazy init)."""
    __slots__ = ('children', 'is_terminal', 'tag')

    def __init__(self) -> None:
        self.children: list | None = None
        self.is_terminal: bool = False
        self.tag: str | None = None

    def get_child(self, c: str) -> TrieNode | None:
        if self.children is None: return None
        idx = _char_index(c)
        return None if idx == -1 else self.children[idx]

    def set_child(self, c: str, node: TrieNode) -> None:
        if self.children is None:
            self.children = [None] * ALPHA_SIZE
        idx = _char_index(c)
        if idx != -1:
            self.children[idx] = node

    def iter_children(self):
        if self.children is None: return
        for idx, child in enumerate(self.children):
            if child is not None: yield idx, child


class Trie:
    """Trie optimisé mémoire (alphabet restreint a-z 0-9 - espace). Sert de référence de comparaison au DAWG."""

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        node = self.root
        for char in word.lower():
            child = node.get_child(char)
            if child is None:
                child = TrieNode()
                node.set_child(char, child)
            node = child
        node.is_terminal = True
        node.tag = word

    def node_count(self) -> int:
        count, stack = 0, [self.root]
        while stack:
            node = stack.pop()
            count += 1
            stack.extend(child for _, child in node.iter_children())
        return count

    def autocomplete(self, prefix: str) -> list[str]:
        node = self.root
        for char in prefix.lower():
            node = node.get_child(char)
            if node is None: return []
        results: list[str] = []
        self._dfs(node, results)
        return results

    def _dfs(self, node: TrieNode, results: list[str]) -> None:
        if node.is_terminal: results.append(node.tag)  # type: ignore[arg-type]
        for _, child in node.iter_children():
            self._dfs(child, results)

    def fuzzy_search(self, query: str, max_distance: int = 1) -> list[str]:
        """Levenshtein DP avec pruning : coupe les branches si min(row) > max_distance."""
        query = query.lower()
        results: list[tuple[str, int]] = []
        init_row = list(range(len(query) + 1))
        for idx, child in self.root.iter_children():
            self._fuzzy_dfs(child, _index_to_char(idx), query, init_row, max_distance, results)
        results.sort(key=lambda x: x[1])
        return [tag for tag, _ in results]

    def _fuzzy_dfs(self, node: TrieNode, char: str, query: str,
                   prev_row: list[int], max_dist: int,
                   results: list[tuple[str, int]]) -> None:
        cur = [prev_row[0] + 1]
        for col in range(1, len(query) + 1):
            cur.append(min(cur[col-1]+1, prev_row[col]+1,
                           prev_row[col-1] + (0 if query[col-1] == char else 1)))
        if min(cur) > max_dist: return
        if cur[-1] <= max_dist and node.is_terminal:
            results.append((node.tag, cur[-1]))  # type: ignore[arg-type]
        for idx, child in node.iter_children():
            self._fuzzy_dfs(child, _index_to_char(idx), query, cur, max_dist, results)


# ── DAWG (Phase 1.3) ────────────────────────────────────────────────────────

class DAWGNode:
    """
    Nœud DAWG. Le mot n'est PAS stocké dans le nœud : il est reconstruit par le
    chemin parcouru. Le stocker dans la clé structurelle rendait chaque nœud
    terminal unique et supprimait tout partage de suffixes (le « DAWG » de la
    1.0.0 n'était alors qu'un Trie : 0 % de gain mesuré).
    """
    __slots__ = ('children', 'is_terminal')

    def __init__(self) -> None:
        self.children: dict[str, DAWGNode] = {}
        self.is_terminal: bool = False

    def structural_key(self) -> tuple:
        """Identité structurelle : deux nœuds de même clé ont le même langage de suffixes."""
        return (self.is_terminal,
                tuple((c, id(n)) for c, n in sorted(self.children.items())))


class DAWG:
    """
    DAWG (Directed Acyclic Word Graph) via l'algorithme de Daciuk et al.
    Partage les suffixes communs : moins de nœuds qu'un Trie sur un vocabulaire
    à suffixes répétés (mesuré par benchmarks/dawg_vs_trie.py).
    IMMUTABLE après finish() : reconstruire (DAWG.build) quand le vocabulaire change.
    """

    def __init__(self) -> None:
        self.root = DAWGNode()
        self._minimized: dict[tuple, DAWGNode] = {}
        self._last_word: str = ""
        self._has_word: bool = False
        self._unchecked: list[tuple[DAWGNode, str, DAWGNode]] = []

    def _minimize(self, down_to: int) -> None:
        for i in range(len(self._unchecked) - 1, down_to - 1, -1):
            parent, char, child = self._unchecked[i]
            key = child.structural_key()
            existing = self._minimized.get(key)
            if existing is not None:
                parent.children[char] = existing
            else:
                self._minimized[key] = child
            self._unchecked.pop()

    def insert(self, word: str) -> None:
        word = word.lower()
        if self._has_word and word <= self._last_word:
            raise ValueError(f"DAWG: insertion hors ordre — '{word}' après '{self._last_word}'.")
        common = 0
        for c1, c2 in zip(word, self._last_word):
            if c1 != c2:
                break
            common += 1
        self._minimize(common)
        node = self.root if not self._unchecked else self._unchecked[-1][2]
        for char in word[common:]:
            new_node = DAWGNode()
            node.children[char] = new_node
            self._unchecked.append((node, char, new_node))
            node = new_node
        node.is_terminal = True
        self._last_word = word
        self._has_word = True

    def finish(self) -> None:
        self._minimize(0)

    @classmethod
    def build(cls, tags) -> DAWG:
        """Construit un DAWG depuis un itérable de tags (dédoublonnés et triés)."""
        dawg = cls()
        for tag in sorted({t.lower() for t in tags}):
            dawg.insert(tag)
        dawg.finish()
        return dawg

    def contains(self, word: str) -> bool:
        node = self.root
        for char in word.lower():
            node = node.children.get(char)  # type: ignore[assignment]
            if node is None:
                return False
        return node.is_terminal

    def autocomplete(self, prefix: str) -> list[str]:
        """Tags commençant par `prefix`, triés par ordre lexicographique."""
        prefix = prefix.lower()
        node = self.root
        for char in prefix:
            node = node.children.get(char)  # type: ignore[assignment]
            if node is None:
                return []
        results: list[str] = []
        self._dfs(node, prefix, results)
        results.sort()
        return results

    def _dfs(self, node: DAWGNode, path: str, results: list[str]) -> None:
        if node.is_terminal:
            results.append(path)
        for char, child in node.children.items():
            self._dfs(child, path + char, results)

    def fuzzy_search(self, query: str, max_distance: int = 1) -> list[str]:
        """Tags à distance de Levenshtein <= max_distance, triés par (distance, tag)."""
        query = query.lower()
        results: list[tuple[int, str]] = []
        init_row = list(range(len(query) + 1))
        for char, child in self.root.children.items():
            self._fuzzy_dfs(child, char, char, query, init_row, max_distance, results)
        results.sort()
        return [tag for _, tag in results]

    def _fuzzy_dfs(self, node: DAWGNode, char: str, path: str, query: str,
                   prev_row: list[int], max_dist: int,
                   results: list[tuple[int, str]]) -> None:
        cur = [prev_row[0] + 1]
        for col in range(1, len(query) + 1):
            cur.append(min(cur[col-1]+1, prev_row[col]+1,
                           prev_row[col-1] + (0 if query[col-1] == char else 1)))
        if min(cur) > max_dist:
            return
        if cur[-1] <= max_dist and node.is_terminal:
            results.append((cur[-1], path))
        for next_char, child in node.children.items():
            self._fuzzy_dfs(child, next_char, path + next_char, query, cur, max_dist, results)

    def node_count(self) -> int:
        """Nombre de nœuds distincts (parcours itératif, sans limite de récursion)."""
        seen = {id(self.root)}
        stack = [self.root]
        while stack:
            for child in stack.pop().children.values():
                if id(child) not in seen:
                    seen.add(id(child))
                    stack.append(child)
        return len(seen)


# ── VarInt + CompressedPostingsList (Phase 1.4) ─────────────────────────────

class VarInt:
    """Encodage variable-length integer (Protocol Buffers style)."""

    @staticmethod
    def encode(value: int) -> bytes:
        if value < 0:
            raise ValueError(f"VarInt: valeur négative non supportée : {value}")
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
            if offset >= len(data):
                raise ValueError("VarInt: données tronquées (offset hors limites).")
            byte = data[offset]; offset += 1
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80): break
            shift += 7
        return result, offset


class CompressedPostingsList:
    """
    Postings list compressée : delta-encoding + VarInt.
    ~98% de réduction vs set Python sur 500 IDs aléatoires.
    Tampon d'écriture : add() est O(1), flush() compresse en lot.
    """

    def __init__(self) -> None:
        self._compressed: bytes = b''
        self._pending: list[int] = []

    @staticmethod
    def _encode(sorted_ids: list[int]) -> bytes:
        buf = bytearray()
        prev = 0
        for pid in sorted_ids:
            buf += VarInt.encode(pid - prev)
            prev = pid
        return bytes(buf)

    def add(self, product_id: int) -> None:
        if product_id < 0:
            raise ValueError(f"product_id doit être >= 0, reçu : {product_id}")
        self._pending.append(product_id)

    def remove(self, product_id: int) -> bool:
        """Retire un identifiant. Retourne False s'il était absent."""
        ids = self.decompress()
        if product_id not in ids:
            return False
        ids.remove(product_id)
        self._compressed = self._encode(ids)
        self._pending.clear()
        return True

    def flush(self) -> None:
        if not self._pending:
            return
        self._compressed = self._encode(self.decompress())
        self._pending.clear()

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

    def __len__(self) -> int:
        return len(self.decompress())

    def memory_bytes(self) -> int:
        return len(self._compressed) + len(self._pending) * 28


# ── LRU Cache ────────────────────────────────────────────────────────────────

class LRUCache:
    """Cache LRU O(1) get/put via OrderedDict."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"LRUCache capacity doit être > 0, reçu : {capacity}")
        self._cache: OrderedDict = OrderedDict()
        self.capacity = capacity

    def get(self, key: str):
        if key not in self._cache: return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: str, value) -> None:
        if key in self._cache: self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def invalidate(self) -> None:
        self._cache.clear()
