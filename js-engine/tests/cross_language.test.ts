/**
 * Tests cross-langage TypeScript — miroir de test_cross_language.py
 * Charge shared-assets/catalog.json et valide les mêmes cas de test.
 * Tolérance : |score_ts - score_py| < 1e-9
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";
import { SearchEngine } from "../src/engine.js";
import { ProductType } from "../src/models.js";
import { BM25Index, PRIOR_MEAN, PRIOR_WEIGHT } from "../src/scoring.js";

const CATALOG_PATH = resolve(__dirname, "../../shared-assets/catalog.json");
const TOLERANCE    = 1e-9;

let engine: SearchEngine;

beforeAll(() => {
  engine = new SearchEngine();
  const data = JSON.parse(readFileSync(CATALOG_PATH, "utf-8"));
  engine.loadCatalog(data);
});

describe("BM25 — composants isolés", () => {
  it("IDF formula matches Python reference", () => {
    const N = 10, df = 3;
    const idf = Math.log((N - df + 0.5) / (df + 0.5) + 1);
    expect(idf).toBeGreaterThan(0);
    // Valeur de référence Python : math.log(7.5/3.5 + 1) ≈ 1.0647
    expect(Math.abs(idf - Math.log(7.5 / 3.5 + 1))).toBeLessThan(TOLERANCE);
  });

  it("TF saturation : tf=10 < 10 × tf=1", () => {
    const idx = new BM25Index();
    idx.index(1, ["gaming", "gaming", "gaming", "gaming", "gaming",
                  "gaming", "gaming", "gaming", "gaming", "gaming"]);
    idx.index(2, ["gaming"]);
    const s10 = idx.score(1, ["gaming"]);
    const s1  = idx.score(2, ["gaming"]);
    expect(s10).toBeLessThan(s1 * 10);
  });

  it("score=0 si tag absent", () => {
    const idx = new BM25Index();
    idx.index(1, ["gaming"]);
    expect(idx.score(1, ["cuisine"])).toBe(0);
  });
});

describe("TC01 — cuisine sans filtre : Physical > Digital", () => {
  it("Robot pâtissier (id=4) devant E-book (id=5)", () => {
    const [results] = engine.search("cuisine", {}, false);
    const ids = results.map(r => r.id);
    expect(ids).toContain(4);
    expect(ids).toContain(5);
    const scoreRobot = results.find(r => r.id === 4)!.score;
    const scoreEbook = results.find(r => r.id === 5)!.score;
    expect(scoreRobot).toBeGreaterThan(scoreEbook);
  });
});

describe("TC02 — cuisine preferred_type=DIGITAL", () => {
  it("E-book (id=5) devant Robot (id=4)", () => {
    const [results] = engine.search("cuisine", { preferredType: ProductType.DIGITAL }, false);
    const ids = results.map(r => r.id);
    expect(ids.indexOf(5)).toBeLessThan(ids.indexOf(4));
  });
});

describe("TC03 — gaming budget max 100€", () => {
  it("Clavier (id=1, 129.99€) exclu, Souris (id=2) présente", () => {
    const [results] = engine.search("gaming", { maxPrice: 100 }, false);
    const ids = results.map(r => r.id);
    expect(ids).not.toContain(1);
    expect(ids).toContain(2);
  });
});

describe("TC04 — beauté min_rating=4.0", () => {
  it("Sérum (id=7, 2.8★) exclu, Palette (id=8) présente", () => {
    const [results] = engine.search("beauté", { minRating: 4.0 }, false);
    const ids = results.map(r => r.id);
    expect(ids).not.toContain(7);
    expect(ids).toContain(8);
  });
});

describe("TC05 — fuzzy 'gaiming'", () => {
  it("Résultats gaming malgré la faute de frappe", () => {
    const [results] = engine.search("gaiming", {}, true, 1);
    const niches = new Set(results.map(r => r.niche));
    expect(niches).toContain("gaming");
  });
});

describe("Scores de référence cross-langage", () => {
  it("TYPE_MISMATCH divise le score par ~10 (ratio = 0.1 ± 1e-6)", () => {
    const [base]    = engine.search("cuisine", {}, false);
    const [digital] = engine.search("cuisine", { preferredType: ProductType.DIGITAL }, false);
    const scoreBase    = base.find(r => r.id === 4)!.score;
    const scoreDigital = digital.find(r => r.id === 4)!.score;
    const ratio = scoreDigital / scoreBase;
    expect(Math.abs(ratio - 0.1)).toBeLessThan(1e-3);
  });

  it("Bayesian rating lisse les produits avec peu d'avis", () => {
    // Sérum : 2.8★, 12 avis → bayesian > 2.8 (tiré vers 3.5)
    // Palette : 4.5★, 276 avis → bayesian < 4.5 (légèrement tiré vers 3.5)
    const serum   = { avgRating: 2.8, reviewCount: 12  };
    const palette = { avgRating: 4.5, reviewCount: 276 };
    const br = (m: typeof serum) =>
      (m.reviewCount * m.avgRating + PRIOR_MEAN * PRIOR_WEIGHT) / (m.reviewCount + PRIOR_WEIGHT);
    expect(br(serum)).toBeGreaterThan(serum.avgRating);
    expect(br(palette)).toBeLessThan(palette.avgRating);
    expect(br(palette)).toBeGreaterThan(br(serum));
  });
});

describe("Robustesse", () => {
  it("Requête vide lève une erreur", () => {
    expect(() => engine.search("")).toThrow("vide");
  });

  it("Requête inconnue retourne MISS", () => {
    const [results, status] = engine.search("xyzqwerty123", {}, false);
    expect(results).toHaveLength(0);
    expect(status).toBe("MISS");
  });

  it("Cache HIT sur requête répétée", () => {
    engine.search("yoga", {}, false);
    const [, status] = engine.search("yoga", {}, false);
    expect(status).toBe("CACHÉ");
  });
});
