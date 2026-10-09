/**
 * Rejeu du jeu de référence croisé (shared-assets/reference.json), généré par le moteur Python.
 * Vérifie, sur 250+ requêtes : mêmes statuts, mêmes ids dans le même ordre, mêmes scores
 * (tolérance du fichier), mêmes champs, mêmes erreurs.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";
import { SearchEngine } from "../src/engine.js";
import { ProductType, SearchPreferences, round4 } from "../src/index.js";

const ref = JSON.parse(readFileSync(resolve(__dirname, "../../shared-assets/reference.json"), "utf-8"));

function toPrefs(p: Record<string, unknown> | undefined): Partial<SearchPreferences> {
  const out: Record<string, unknown> = {};
  if (!p) return out as Partial<SearchPreferences>;
  if (p["preferred_type"] !== undefined) {
    out["preferredType"] = String(p["preferred_type"]).toUpperCase() === "DIGITAL" ? ProductType.DIGITAL : ProductType.PHYSICAL;
  }
  if (p["preferred_niche"] !== undefined) out["preferredNiche"] = p["preferred_niche"];
  if (p["max_price"] !== undefined) out["maxPrice"] = p["max_price"];
  if (p["min_price"] !== undefined) out["minPrice"] = p["min_price"];
  if (p["user_location"] !== undefined) out["userLocation"] = p["user_location"];
  if (p["min_rating"] !== undefined) out["minRating"] = p["min_rating"];
  return out as Partial<SearchPreferences>;
}

describe("jeu de référence croisé (source de vérité : Python)", () => {
  it("contient au moins 200 produits et 100 requêtes", () => {
    expect(ref.products.length).toBeGreaterThanOrEqual(200);
    expect(ref.cases.length).toBeGreaterThanOrEqual(100);
  });

  it("round4 égale round(x, 4) de Python sur 7 000 valeurs (quasi-égalités et égalités exactes)", () => {
    const bad = (ref.rounding as number[][]).filter(([x, expected]) => round4(x!) !== expected);
    expect(bad).toEqual([]);
  });

  it("rejoue toutes les requêtes dans l'ordre avec les mêmes résultats", () => {
    const engine = new SearchEngine(200);
    engine.loadCatalog({ products: ref.products });
    const failures: string[] = [];

    for (const c of ref.cases) {
      const fuzzy = c.fuzzy ?? true, maxDist = c.max_dist ?? 1, topK = c.top_k ?? 10;
      const where = `${c.id} ${JSON.stringify(c.query)}`;
      if (c.expect.error) {
        try {
          engine.search(c.query, toPrefs(c.prefs), fuzzy, maxDist, topK);
          failures.push(`${where}: erreur attendue`);
        } catch { /* attendu */ }
        continue;
      }
      const [results, status] = engine.search(c.query, toPrefs(c.prefs), fuzzy, maxDist, topK);
      if (status !== c.expect.status) failures.push(`${where}: statut ${status} != ${c.expect.status}`);
      const gotIds = results.map(r => r.id).join(",");
      const refIds = c.expect.results.map((r: { id: number }) => r.id).join(",");
      if (gotIds !== refIds) { failures.push(`${where}: ids [${gotIds}] != [${refIds}]`); continue; }
      results.forEach((r, i) => {
        const e = c.expect.results[i];
        if (Math.abs(r.score - e.score) > ref.tolerance) failures.push(`${where}: score ${r.score} != ${e.score} (id ${r.id})`);
        for (const f of ["name", "type", "niche", "price", "rating", "reviews"] as const) {
          if (r[f] !== e[f]) failures.push(`${where}: champ ${f} ${r[f]} != ${e[f]}`);
        }
      });
    }
    expect(failures).toEqual([]);
  });
});
