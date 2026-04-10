/**
 * tagsearch/structures.ts
 * Réalisée par Gillesto66 & Kiro
 * DAWG + LRUCache — portage de structures.py
 * Note : pas de __slots__ en TS, mais les classes sont naturellement compactes.
 */

// ── DAWG ─────────────────────────────────────────────────────────────────────

class DAWGNode {
  children: Map<string, DAWGNode> = new Map();
  isTerminal = false;
  tag: string | null = null;
  frozen = false;
}

export class DAWG {
  readonly root: DAWGNode = new DAWGNode();
  private minimized: Map<string, DAWGNode> = new Map();
  private lastWord   = "";
  private unchecked: Array<[DAWGNode, string, DAWGNode]> = [];

  private structuralKey(node: DAWGNode): string {
    const children = [...node.children.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([c, n]) => `${c}:${this.nodeId(n)}`)
      .join(",");
    return `${node.isTerminal}|${node.tag ?? ""}|${children}`;
  }

  private nodeId(node: DAWGNode): string {
    // Identifiant stable basé sur la structure (simplifié pour TS)
    return this.structuralKey(node);
  }

  private minimize(downTo: number): void {
    for (let i = this.unchecked.length - 1; i >= downTo; i--) {
      const [parent, char, child] = this.unchecked[i]!;
      const key = this.structuralKey(child);
      const existing = this.minimized.get(key);
      if (existing) {
        parent.children.set(char, existing);
      } else {
        child.frozen = true;
        this.minimized.set(key, child);
      }
      this.unchecked.pop();
    }
  }

  insert(word: string): void {
    const w = word.toLowerCase();
    if (w <= this.lastWord && this.lastWord !== "") {
      throw new Error(`DAWG: insertion hors ordre — '${w}' après '${this.lastWord}'.`);
    }
    let common = 0;
    for (let i = 0; i < Math.min(w.length, this.lastWord.length); i++) {
      if (w[i] !== this.lastWord[i]) break;
      common = i + 1;
    }
    this.minimize(common);
    let node = this.unchecked.length === 0 ? this.root : this.unchecked[this.unchecked.length - 1]![2];
    for (const char of w.slice(common)) {
      const newNode = new DAWGNode();
      node.children.set(char, newNode);
      this.unchecked.push([node, char, newNode]);
      node = newNode;
    }
    node.isTerminal = true;
    node.tag = w;
    this.lastWord = w;
  }

  finish(): void { this.minimize(0); }

  static build(tags: string[]): DAWG {
    const dawg = new DAWG();
    const sorted = [...new Set(tags.map(t => t.toLowerCase()))].sort();
    for (const tag of sorted) dawg.insert(tag);
    dawg.finish();
    return dawg;
  }

  contains(word: string): boolean {
    let node: DAWGNode | undefined = this.root;
    for (const char of word.toLowerCase()) {
      node = node.children.get(char);
      if (!node) return false;
    }
    return node.isTerminal;
  }

  autocomplete(prefix: string): string[] {
    let node: DAWGNode | undefined = this.root;
    for (const char of prefix.toLowerCase()) {
      node = node.children.get(char);
      if (!node) return [];
    }
    const results: string[] = [];
    this._dfs(node, results);
    return results;
  }

  private _dfs(node: DAWGNode, results: string[]): void {
    if (node.isTerminal && node.tag) results.push(node.tag);
    for (const child of node.children.values()) this._dfs(child, results);
  }

  fuzzySearch(query: string, maxDistance = 1): string[] {
    const q = query.toLowerCase();
    const results: Array<[string, number]> = [];
    const initRow = Array.from({ length: q.length + 1 }, (_, i) => i);
    for (const [char, child] of this.root.children) {
      this._fuzzyDfs(child, char, q, initRow, maxDistance, results);
    }
    results.sort((a, b) => a[1] - b[1]);
    return results.map(([tag]) => tag);
  }

  private _fuzzyDfs(
    node: DAWGNode, char: string, query: string,
    prevRow: number[], maxDist: number, results: Array<[string, number]>
  ): void {
    const cur: number[] = [prevRow[0]! + 1];
    for (let col = 1; col <= query.length; col++) {
      cur.push(Math.min(
        cur[col - 1]! + 1,
        prevRow[col]! + 1,
        prevRow[col - 1]! + (query[col - 1] === char ? 0 : 1)
      ));
    }
    if (Math.min(...cur) > maxDist) return;
    if (cur[query.length]! <= maxDist && node.isTerminal && node.tag) {
      results.push([node.tag, cur[query.length]!]);
    }
    for (const [nextChar, child] of node.children) {
      this._fuzzyDfs(child, nextChar, query, cur, maxDist, results);
    }
  }
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
