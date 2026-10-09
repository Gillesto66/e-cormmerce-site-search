/**
 * tagsearch/structures.ts
 * Réalisée par Gillesto66 & Kiro
 * DAWG + VarInt/CompressedPostingsList + LRUCache — portage de structures.py
 *
 * Unicode : les mots sont découpés en POINTS DE CODE (Array.from), comme en Python,
 * et comparés par point de code — jamais par unité UTF-16 — pour que la distance de
 * Levenshtein et l'ordre des tags soient identiques dans les trois langages.
 */

/** Compare deux chaînes par points de code Unicode (équivalent de `<` en Python). */
export function compareCodePoints(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = x[i]!.codePointAt(0)! - y[i]!.codePointAt(0)!;
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return x.length === y.length ? 0 : x.length < y.length ? -1 : 1;
}

// ── DAWG ─────────────────────────────────────────────────────────────────────

/**
 * Nœud DAWG. Le mot n'est PAS stocké dans le nœud (il est reconstruit par le chemin) :
 * c'est ce qui permet le partage de suffixes. `id` est une identité de nœud canonique
 * utilisée uniquement pour construire la clé structurelle (coût O(degré), pas O(sous-arbre)).
 */
class DAWGNode {
  children: Map<string, DAWGNode> = new Map();
  isTerminal = false;
  constructor(readonly id: number) {}
}

export class DAWG {
  readonly root: DAWGNode;
  private nextId = 0;
  private minimized: Map<string, DAWGNode> = new Map();
  private lastChars: string[] = [];
  private hasWord = false;
  private unchecked: Array<[DAWGNode, string, DAWGNode]> = [];

  constructor() {
    this.root = this.newNode();
  }

  private newNode(): DAWGNode {
    return new DAWGNode(this.nextId++);
  }

  private structuralKey(node: DAWGNode): string {
    const parts = [...node.children.entries()]
      .sort(([a], [b]) => compareCodePoints(a, b))
      .map(([c, n]) => `${c}\u0001${n.id}`);
    return `${node.isTerminal ? 1 : 0}\u0002${parts.join("\u0003")}`;
  }

  private minimize(downTo: number): void {
    for (let i = this.unchecked.length - 1; i >= downTo; i--) {
      const [parent, char, child] = this.unchecked[i]!;
      const key = this.structuralKey(child);
      const existing = this.minimized.get(key);
      if (existing) {
        parent.children.set(char, existing);
      } else {
        this.minimized.set(key, child);
      }
      this.unchecked.pop();
    }
  }

  /** Les mots doivent être insérés par ordre strictement croissant (points de code). */
  insert(word: string): void {
    const chars = Array.from(word.toLowerCase());
    const w = chars.join("");
    if (this.hasWord && compareCodePoints(w, this.lastChars.join("")) <= 0) {
      throw new Error(`DAWG: insertion hors ordre — '${w}' après '${this.lastChars.join("")}'.`);
    }
    let common = 0;
    const limit = Math.min(chars.length, this.lastChars.length);
    while (common < limit && chars[common] === this.lastChars[common]) common++;
    this.minimize(common);
    let node = this.unchecked.length === 0 ? this.root : this.unchecked[this.unchecked.length - 1]![2];
    for (const char of chars.slice(common)) {
      const newNode = this.newNode();
      node.children.set(char, newNode);
      this.unchecked.push([node, char, newNode]);
      node = newNode;
    }
    node.isTerminal = true;
    this.lastChars = chars;
    this.hasWord = true;
  }

  finish(): void { this.minimize(0); }

  static build(tags: Iterable<string>): DAWG {
    const dawg = new DAWG();
    const sorted = [...new Set([...tags].map(t => t.toLowerCase()))].sort(compareCodePoints);
    for (const tag of sorted) dawg.insert(tag);
    dawg.finish();
    return dawg;
  }

  contains(word: string): boolean {
    let node: DAWGNode | undefined = this.root;
    for (const char of Array.from(word.toLowerCase())) {
      node = node.children.get(char);
      if (!node) return false;
    }
    return node.isTerminal;
  }

  /** Tags commençant par `prefix`, triés par points de code. */
  autocomplete(prefix: string): string[] {
    const p = prefix.toLowerCase();
    let node: DAWGNode | undefined = this.root;
    for (const char of Array.from(p)) {
      node = node.children.get(char);
      if (!node) return [];
    }
    const results: string[] = [];
    this.dfs(node, p, results);
    return results.sort(compareCodePoints);
  }

  private dfs(node: DAWGNode, path: string, results: string[]): void {
    if (node.isTerminal) results.push(path);
    for (const [char, child] of node.children) this.dfs(child, path + char, results);
  }

  /** Tags à distance de Levenshtein <= maxDistance, triés par (distance, tag). */
  fuzzySearch(query: string, maxDistance = 1): string[] {
    const q = Array.from(query.toLowerCase());
    const results: Array<[number, string]> = [];
    const initRow = Array.from({ length: q.length + 1 }, (_, i) => i);
    for (const [char, child] of this.root.children) {
      this.fuzzyDfs(child, char, char, q, initRow, maxDistance, results);
    }
    results.sort((a, b) => a[0] - b[0] || compareCodePoints(a[1], b[1]));
    return results.map(([, tag]) => tag);
  }

  private fuzzyDfs(
    node: DAWGNode, char: string, path: string, query: string[],
    prevRow: number[], maxDist: number, results: Array<[number, string]>,
  ): void {
    const cur: number[] = [prevRow[0]! + 1];
    let rowMin = cur[0]!;
    for (let col = 1; col <= query.length; col++) {
      const v = Math.min(
        cur[col - 1]! + 1,
        prevRow[col]! + 1,
        prevRow[col - 1]! + (query[col - 1] === char ? 0 : 1),
      );
      cur.push(v);
      if (v < rowMin) rowMin = v;
    }
    if (rowMin > maxDist) return;
    if (cur[query.length]! <= maxDist && node.isTerminal) {
      results.push([cur[query.length]!, path]);
    }
    for (const [nextChar, child] of node.children) {
      this.fuzzyDfs(child, nextChar, path + nextChar, query, cur, maxDist, results);
    }
  }

  /** Nombre de nœuds distincts (parcours itératif). */
  nodeCount(): number {
    const seen = new Set<number>([this.root.id]);
    const stack: DAWGNode[] = [this.root];
    while (stack.length > 0) {
      for (const child of stack.pop()!.children.values()) {
        if (!seen.has(child.id)) {
          seen.add(child.id);
          stack.push(child);
        }
      }
    }
    return seen.size;
  }
}

// ── VarInt + CompressedPostingsList ──────────────────────────────────────────

/** Encodage variable-length integer (style Protocol Buffers). Entiers sûrs jusqu'à 2^53. */
export const VarInt = {
  encode(value: number, out: number[] = []): number[] {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new Error(`VarInt: valeur invalide (entier >= 0 attendu) : ${value}`);
    }
    let v = value;
    while (v >= 0x80) {
      out.push((v % 0x80) | 0x80);
      v = Math.floor(v / 0x80);
    }
    out.push(v);
    return out;
  },

  /** Retourne [valeur, nouvel offset]. */
  decode(data: Uint8Array, offset = 0): [number, number] {
    let result = 0;
    let factor = 1;
    for (;;) {
      if (offset >= data.length) throw new Error("VarInt: données tronquées (offset hors limites).");
      const byte = data[offset++]!;
      result += (byte & 0x7f) * factor;
      if ((byte & 0x80) === 0) break;
      factor *= 0x80;
    }
    return [result, offset];
  },
};

/**
 * Postings list compressée : delta-encoding + VarInt (portage de CompressedPostingsList).
 * add() est O(1) (tampon) ; flush() compresse en lot.
 */
export class CompressedPostingsList {
  private compressed: Uint8Array = new Uint8Array(0);
  private pending: number[] = [];

  private static encode(sortedIds: number[]): Uint8Array {
    const bytes: number[] = [];
    let prev = 0;
    for (const id of sortedIds) {
      VarInt.encode(id - prev, bytes);
      prev = id;
    }
    return Uint8Array.from(bytes);
  }

  add(productId: number): void {
    if (!Number.isSafeInteger(productId) || productId < 0) {
      throw new Error(`productId doit être un entier >= 0, reçu : ${productId}`);
    }
    this.pending.push(productId);
  }

  remove(productId: number): boolean {
    const ids = this.decompress();
    const at = ids.indexOf(productId);
    if (at === -1) return false;
    ids.splice(at, 1);
    this.compressed = CompressedPostingsList.encode(ids);
    this.pending = [];
    return true;
  }

  flush(): void {
    if (this.pending.length === 0) return;
    this.compressed = CompressedPostingsList.encode(this.decompress());
    this.pending = [];
  }

  decompress(): number[] {
    const ids: number[] = [];
    let offset = 0;
    let current = 0;
    while (offset < this.compressed.length) {
      const [delta, next] = VarInt.decode(this.compressed, offset);
      offset = next;
      current += delta;
      ids.push(current);
    }
    if (this.pending.length === 0) return ids;
    return [...new Set([...ids, ...this.pending])].sort((a, b) => a - b);
  }

  get size(): number { return this.decompress().length; }

  /** Octets occupés par la représentation compressée (hors tampon d'écriture). */
  memoryBytes(): number { return this.compressed.length + this.pending.length * 8; }

  /** Injection directe d'octets (tests de robustesse sur données corrompues). */
  _setCompressedForTest(bytes: Uint8Array): void { this.compressed = bytes; }
}

// ── LRU Cache ─────────────────────────────────────────────────────────────────

export class LRUCache<V> {
  private cache: Map<string, V> = new Map();

  constructor(private readonly capacity: number) {
    if (capacity <= 0) throw new Error(`LRUCache capacity doit être > 0`);
  }

  get(key: string): V | undefined {
    if (!this.cache.has(key)) return undefined;
    const val = this.cache.get(key)!;
    this.cache.delete(key);
    this.cache.set(key, val);
    return val;
  }

  put(key: string, value: V): void {
    if (this.cache.has(key)) this.cache.delete(key);
    this.cache.set(key, value);
    if (this.cache.size > this.capacity) {
      this.cache.delete(this.cache.keys().next().value!);
    }
  }

  invalidate(): void { this.cache.clear(); }
}
