/**
 * tagsearch/engine.ts
 * Réalisée par Gillesto66 & Kiro
 * SearchEngine — portage fidèle de engine.py
 * Optimisé pour environnements Serverless (Vercel) : pas d'I/O bloquant,
 * état entièrement in-memory, reconstruction DAWG en batch.
 */

import { createProductMeta, defaultPrefs, ProductMeta, SearchPreferences } from "./models.js";
import { BM25Index, calculateFinalScore } from "./scoring.js";
import { DAWG, LRUCache } from "./structures.js";

export interface SearchResult {
  id      : number;
  name    : string;
  type    : string;
  niche   : string;
  price   : number;
  rating  : number;
  reviews : number;
  score   : number;
}

export type SearchStatus = "CACHÉ" | "CALCULÉ" | "MISS";

export class SearchEngine {
  private allTags:       string[]                              = [];
  private dawg:          DAWG                                  = new DAWG();
  private invertedIndex: Map<string, Set<number>>              = new Map();
  private catalog:       Map<number, ProductMeta>              = new Map();
  private bm25:          BM25Index                             = new BM25Index();
  private cache:         LRUCache<SearchResult[]>              = new LRUCache(200);

  loadCatalog(data: { products: unknown[] }): void {
    if (!Array.isArray(data.products) || data.products.length === 0) {
      console.warn("[tagsearch] Catalogue vide.");
      return;
    }
    for (const raw of data.products) {
      const r = raw as Record<string, unknown>;
      const meta = createProductMeta({
        name: r["name"] as string, type: r["type"] as string,
        niche: r["niche"] as string, price: r["price"] as number,
        location: (r["location"] as string | null) ?? null,
        avg_rating: r["avg_rating"] as number,
        review_count: r["review_count"] as number,
        tags: r["tags"] as string[],
      });
      this.addProduct(r["id"] as number, meta);
    }
  }

  addProduct(productId: number, meta: ProductMeta): void {
    if (productId < 0) throw new Error(`productId doit être >= 0, reçu : ${productId}`);
    this.catalog.set(productId, meta);
    for (const tag of meta.tags) {
      const t = tag.toLowerCase();
      if (!this.invertedIndex.has(t)) {
        this.invertedIndex.set(t, new Set());
        this.allTags.push(t);
      }
      this.invertedIndex.get(t)!.add(productId);
    }
    this.bm25.index(productId, meta.tags);
    this.dawg = DAWG.build(this.allTags);
    this.cache.invalidate();
  }

  search(
    query    : string,
    prefs   ?: Partial<SearchPreferences>,
    fuzzy    = true,
    maxDist  = 1,
    topK     = 10,
  ): [SearchResult[], SearchStatus] {
    if (!query || !query.trim()) throw new Error("La requête ne peut pas être vide.");
    if (maxDist < 0) throw new Error(`maxDist doit être >= 0, reçu : ${maxDist}`);
    if (this.catalog.size === 0) return [[], "MISS"];

    const fullPrefs: SearchPreferences = { ...defaultPrefs(), ...prefs };
    const cacheKey = `${query.trim().toLowerCase()}|${JSON.stringify(fullPrefs)}`;
    const cached   = this.cache.get(cacheKey);
    if (cached) return [cached, "CACHÉ"];

    const qLower = query.trim().toLowerCase();
    const matchedTags = fuzzy
      ? this.dawg.fuzzySearch(qLower, maxDist)
      : this.dawg.autocomplete(qLower);

    if (matchedTags.length === 0) return [[], "MISS"];

    const candidateIds = new Set<number>();
    for (const tag of matchedTags) {
      this.invertedIndex.get(tag)?.forEach(id => candidateIds.add(id));
    }

    const results: SearchResult[] = [];
    for (const pid of candidateIds) {
      const meta = this.catalog.get(pid);
      if (!meta) continue;
      const bm25Raw    = this.bm25.score(pid, matchedTags);
      const finalScore = calculateFinalScore(pid, meta, bm25Raw, fullPrefs);
      if (finalScore === null) continue;
      results.push({
        id: pid, name: meta.name, type: meta.productType === 0 ? "PHYSICAL" : "DIGITAL",
        niche: meta.niche, price: meta.price, rating: meta.avgRating,
        reviews: meta.reviewCount, score: finalScore,
      });
    }

    results.sort((a, b) => b.score - a.score);
    const finalList = results.slice(0, topK);
    this.cache.put(cacheKey, finalList);
    return [finalList, "CALCULÉ"];
  }
}
