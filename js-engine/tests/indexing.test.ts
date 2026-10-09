/** Indexation en lot, cohérence de l'index, structures (audit C1, C3, C8, C10). */
import { describe, it, expect } from "vitest";
import { SearchEngine } from "../src/engine.js";
import { createProductMeta, ProductMeta } from "../src/models.js";
import { BM25Index, round4 } from "../src/scoring.js";
import { CompressedPostingsList, DAWG, VarInt, compareCodePoints } from "../src/structures.js";

function meta(tags: string[], over: Partial<Parameters<typeof createProductMeta>[0]> = {}): ProductMeta {
  return createProductMeta({
    name: "P", type: "PHYSICAL", niche: "n", price: 10, location: null,
    avg_rating: 4, review_count: 10, tags, ...over,
  });
}

// Générateur pseudo-aléatoire déterministe (mulberry32)
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const SYL = ["ba", "be", "bi", "bo", "ca", "co", "da", "de", "fa", "ga", "la", "le", "ma", "mi", "na", "pa", "ra", "re", "sa", "ta", "va"];
const SUF = ["", "", "ier", "ique", "eur", "age", "tion", "able"];
function vocab(n: number, r: () => number): string[] {
  const s = new Set<string>();
  while (s.size < n) {
    let w = "";
    for (let i = 0, k = 1 + Math.floor(r() * 3); i < k; i++) w += SYL[Math.floor(r() * SYL.length)];
    s.add(w + SUF[Math.floor(r() * SUF.length)]);
  }
  return [...s].sort(compareCodePoints);
}
function items(n: number, r: () => number, words: string[]): Array<[number, ProductMeta]> {
  return Array.from({ length: n }, (_, i) =>
    [i + 1, meta(Array.from({ length: 5 }, () => words[Math.floor(r() * words.length)]!))] as [number, ProductMeta]);
}

describe("C1 — indexation en lot", () => {
  it("construit le DAWG une seule fois pour un lot, puis paresseusement", () => {
    const r = rng(1);
    let builds = 0;
    const orig = DAWG.build;
    DAWG.build = ((t: Iterable<string>) => { builds++; return orig(t); }) as typeof DAWG.build;
    try {
      new SearchEngine().addProducts(items(300, r, vocab(300, r)));
      expect(builds).toBe(1);

      const lazy = new SearchEngine();
      builds = 0;
      for (const [id, m] of items(100, r, vocab(100, r))) lazy.addProduct(id, m);
      expect(builds).toBe(0);
      expect(lazy.dirty).toBe(true);
      lazy.search("a", {}, false);
      lazy.search("b", {}, false);
      expect(builds).toBe(1);
      expect(lazy.dirty).toBe(false);
    } finally { DAWG.build = orig; }
  });

  it("l'indexation n'est pas quadratique (2N produits < 3x le temps de N)", () => {
    // Le garde-fou DÉTERMINISTE est le test précédent (une seule reconstruction du DAWG). Ce test
    // chronométré est un filet : échauffement du JIT, tailles assez grandes pour que le bruit d'un
    // runner partagé soit négligeable, meilleur de 5 essais.
    const run = (n: number) => {
      const r = rng(9);
      const it = items(n, r, vocab(400, r));
      const t0 = performance.now();
      new SearchEngine().addProducts(it);
      return performance.now() - t0;
    };
    run(2000); run(2000);                       // échauffement
    const best = (n: number) => Math.min(...Array.from({ length: 5 }, () => run(n)));
    expect(best(8000) / best(4000)).toBeLessThan(3);
  });

  it("loadCatalog est atomique", () => {
    const eng = new SearchEngine();
    const good = { id: 1, name: "a", type: "PHYSICAL", niche: "x", price: 1, avg_rating: 4, review_count: 1, tags: ["a"] };
    expect(() => eng.loadCatalog({ products: [good, { ...good, id: 2, avg_rating: 9 }] })).toThrow(/id=2/);
    expect(eng.search("a", {}, false)[1]).toBe("MISS");
  });
});

describe("cohérence de l'index", () => {
  it("remplace un produit proprement (postings + BM25)", () => {
    const eng = new SearchEngine();
    eng.addProduct(1, meta(["alpha", "beta"]));
    eng.addProduct(2, meta(["beta"]));
    eng.addProduct(1, meta(["gamma"]));
    expect(eng.search("alpha", {}, false)[0]).toEqual([]);
    expect(eng.search("gamma", {}, false)[0].map(r => r.id)).toEqual([1]);
    expect(eng.search("beta", {}, false)[0].map(r => r.id)).toEqual([2]);
  });

  it("retire un produit et nettoie le vocabulaire", () => {
    const eng = new SearchEngine();
    eng.addProduct(1, meta(["unique", "commun"]));
    eng.addProduct(2, meta(["commun"]));
    expect(eng.removeProduct(1)).toBe(true);
    expect(eng.removeProduct(1)).toBe(false);
    expect(eng.search("unique", {}, false)[0]).toEqual([]);
  });

  it("BM25 refuse la double indexation et maintient avgdl", () => {
    const idx = new BM25Index();
    idx.index(1, ["a", "b"]);
    expect(() => idx.index(1, ["a"])).toThrow(/déjà indexé/);
    idx.index(2, ["a"]);
    idx.remove(1, ["a", "b"]);
    expect(idx.docCount).toBe(1);
    expect(idx.docFreq("b")).toBe(0);
  });

  it("la clé de cache contient fuzzy, maxDist et topK", () => {
    const eng = new SearchEngine();
    eng.addProducts([[1, meta(["gaming"])], [2, meta(["gamin"])], [3, meta(["gaminx"])]]);
    expect(eng.search("gaming", {}, false)[0]).toHaveLength(1);
    expect(eng.search("gaming", {}, true, 1)[0]).toHaveLength(3);
    expect(eng.search("gaming", {}, true, 1)[1]).toBe("CACHÉ");
    expect(eng.search("gaming", {}, true, 1, 1)[0]).toHaveLength(1);
  });

  it("les résultats en cache sont des copies", () => {
    const eng = new SearchEngine();
    eng.addProduct(1, meta(["gaming"]));
    eng.search("gaming", {}, false)[0][0]!.score = -1;
    const [r, s] = eng.search("gaming", {}, false);
    expect(s).toBe("CACHÉ");
    expect(r[0]!.score).not.toBe(-1);
  });

  it("départage les ex æquo par id croissant et valide topK", () => {
    const eng = new SearchEngine();
    for (const id of [9, 3, 7, 1]) eng.addProduct(id, meta(["twin"]));
    expect(eng.search("twin", {}, false)[0].map(r => r.id)).toEqual([1, 3, 7, 9]);
    expect(() => eng.search("twin", {}, false, 1, 0)).toThrow(/topK/);
  });
});

describe("structures", () => {
  it("DAWG : partage réel des suffixes (moins de la moitié des nœuds d'un trie)", () => {
    const words = vocab(1500, rng(7));
    let trie = 1;
    const seen = new Set<string>();
    for (const w of words) {
      const cps = Array.from(w);
      for (let i = 1; i <= cps.length; i++) {
        const p = cps.slice(0, i).join("");
        if (!seen.has(p)) { seen.add(p); trie++; }
      }
    }
    expect(DAWG.build(words).nodeCount()).toBeLessThan(trie * 0.5);
  });

  it("DAWG : fuzzy == Levenshtein exhaustif, points de code Unicode compris", () => {
    const lev = (a: string[], b: string[]) => {
      let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
      for (let i = 1; i <= a.length; i++) {
        const cur = [i];
        for (let j = 1; j <= b.length; j++) {
          cur.push(Math.min(cur[j - 1]! + 1, prev[j]! + 1, prev[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 1)));
        }
        prev = cur;
      }
      return prev[b.length]!;
    };
    const words = [...vocab(200, rng(5)), "café", "cafe", "🍣", "sushi🍣", "寿司"].sort(compareCodePoints);
    const dawg = DAWG.build(words);
    for (const q of ["caf", "cafe", "sushi", "🍣", "寿", "ba", "bat"]) {
      for (const d of [0, 1, 2]) {
        const exp = words
          .map(w => [lev(Array.from(q), Array.from(w)), w] as [number, string])
          .filter(([x]) => x <= d)
          .sort((a, b) => a[0] - b[0] || compareCodePoints(a[1], b[1]))
          .map(x => x[1]);
        expect(dawg.fuzzySearch(q, d)).toEqual(exp);
      }
    }
  });

  it("VarInt aller-retour jusqu'à 2^53-1 ; refuse négatifs et non entiers", () => {
    for (const v of [0, 1, 127, 128, 16383, 16384, 2 ** 31, 2 ** 40 + 5, Number.MAX_SAFE_INTEGER]) {
      expect(VarInt.decode(Uint8Array.from(VarInt.encode(v)))[0]).toBe(v);
    }
    expect(() => VarInt.encode(-1)).toThrow();
    expect(() => VarInt.encode(1.5)).toThrow();
    expect(() => VarInt.decode(Uint8Array.from([0x80]))).toThrow(/tronquées/);
  });

  it("postings : compression delta+VarInt, ajout, retrait", () => {
    const pl = new CompressedPostingsList();
    const r = rng(3);
    const ids = new Set<number>();
    while (ids.size < 500) ids.add(1 + Math.floor(r() * 100000));
    for (const i of ids) pl.add(i);
    pl.flush();
    expect(pl.decompress()).toEqual([...ids].sort((a, b) => a - b));
    expect(pl.memoryBytes()).toBeLessThan(500 * 3);
    expect(pl.remove([...ids][0]!)).toBe(true);
    expect(pl.size).toBe(499);
  });

  it("round4 == round(x, 4) de Python, y compris sur les égalités exactes", () => {
    expect(round4(0.03125)).toBe(0.0312);   // égalité exacte -> pair (Python : 0.0312)
    expect(round4(0.09375)).toBe(0.0938);
    expect(round4(0.12345)).toBe(0.1235);   // 0.12345 est stocké juste au-dessus
    expect(round4(1.00005)).toBe(1.0001);
  });
});
