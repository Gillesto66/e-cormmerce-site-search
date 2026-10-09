/**
 * tagsearch/engine.ts
 * Réalisée par Gillesto66 & Kiro
 * SearchEngine — portage fidèle de engine.py
 * Optimisé pour environnements Serverless (Vercel) : pas d'I/O bloquant, état
 * entièrement in-memory.
 *
 * Indexation paresseuse : addProduct()/addProducts() n'enregistrent que les données ;
 * le DAWG est reconstruit UNE fois (premier search() suivant, ou commit()).
 */

import { createProductMeta, defaultPrefs, ProductMeta, SearchPreferences } from "./models.js";
import { BM25Index, calculateFinalScore } from "./scoring.js";
import { CompressedPostingsList, DAWG, LRUCache } from "./structures.js";

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
  private dawg:          DAWG                                    = new DAWG();
  private invertedIndex: Map<string, CompressedPostingsList>     = new Map();
  private catalog:       Map<number, ProductMeta>                = new Map();
  private bm25:          BM25Index                               = new BM25Index();
  private cache:         LRUCache<SearchResult[]>;
  private dirtyTags:     Set<string>                             = new Set();
  private vocabChanged                                           = false;

  constructor(cacheSize = 200) {
    this.cache = new LRUCache(cacheSize);
  }

  /** Charge un catalogue déjà parsé ({ products: [...] }). Atomique : tout ou rien. */
  loadCatalog(data: { products: unknown[] }): void {
    if (!Array.isArray(data.products) || data.products.length === 0) {
      console.warn("[tagsearch] Catalogue vide.");
      return;
    }
    const parsed: Array<[number, ProductMeta]> = [];
    for (const raw of data.products) {
      const r = raw as Record<string, unknown>;
      try {
        const id = r["id"];
        if (typeof id !== "number" || !Number.isInteger(id)) throw new Error(`id invalide : ${String(id)}`);
        parsed.push([id, createProductMeta({
          name: r["name"] as string, type: r["type"] as string,
          niche: r["niche"] as string, price: r["price"] as number,
          location: (r["location"] as string | null) ?? null,
          avg_rating: r["avg_rating"] as number,
          review_count: r["review_count"] as number,
          tags: r["tags"] as string[],
        })]);
      } catch (e) {
        throw new Error(`Produit invalide (id=${String(r["id"] ?? "?")}) : ${(e as Error).message}`);
      }
    }
    this.addProducts(parsed);
  }

  /**
   * Enregistre un produit. L'index est mis à jour au prochain search() ou commit().
   * Un identifiant déjà présent est REMPLACÉ proprement (postings et BM25 mis à jour).
   */
  addProduct(productId: number, meta: ProductMeta): void {
    this.add(productId, meta);
    this.cache.invalidate();
  }

  /** Ajoute un lot puis reconstruit l'index une seule fois. Retourne le nombre traité. */
  addProducts(items: Iterable<[number, ProductMeta]>): number {
    let count = 0;
    for (const [id, meta] of items) { this.add(id, meta); count++; }
    this.cache.invalidate();
    this.commit();
    return count;
  }

  removeProduct(productId: number): boolean {
    if (!this.catalog.has(productId)) return false;
    this.remove(productId);
    this.cache.invalidate();
    return true;
  }

  /** Compresse les postings modifiés et reconstruit le DAWG si le vocabulaire a changé. */
  commit(): void {
    for (const tag of this.dirtyTags) this.invertedIndex.get(tag)?.flush();
    this.dirtyTags.clear();
    if (this.vocabChanged) {
      this.dawg = DAWG.build(this.invertedIndex.keys());
      this.vocabChanged = false;
    }
  }

  /** Vide le cache des résultats (mesures hors cache, tests). */
  clearCache(): void { this.cache.invalidate(); }

  get dirty(): boolean { return this.dirtyTags.size > 0 || this.vocabChanged; }

  private add(productId: number, meta: ProductMeta): void {
    if (!Number.isInteger(productId) || productId < 0) {
      throw new Error(`productId doit être un entier >= 0, reçu : ${productId}`);
    }
    if (this.catalog.has(productId)) this.remove(productId);
    this.catalog.set(productId, meta);
    for (const tag of new Set(meta.tags.map(t => t.toLowerCase()))) {
      let postings = this.invertedIndex.get(tag);
      if (!postings) {
        postings = new CompressedPostingsList();
        this.invertedIndex.set(tag, postings);
        this.vocabChanged = true;
      }
      postings.add(productId);
      this.dirtyTags.add(tag);
    }
    this.bm25.index(productId, meta.tags);
  }

  private remove(productId: number): void {
    const meta = this.catalog.get(productId)!;
    this.catalog.delete(productId);
    for (const tag of new Set(meta.tags.map(t => t.toLowerCase()))) {
      const postings = this.invertedIndex.get(tag)!;
      postings.remove(productId);
      if (postings.size === 0) {
        this.invertedIndex.delete(tag);
        this.dirtyTags.delete(tag);
        this.vocabChanged = true;
      } else {
        this.dirtyTags.add(tag);
      }
    }
    this.bm25.remove(productId, meta.tags);
  }

  /**
   * Recherche multidimensionnelle. Ordre déterministe : score décroissant puis `id`
   * croissant ; tags appariés ordonnés (distance, tag). Lève une Error si la requête
   * est vide, maxDist < 0 ou topK < 1 ; toute autre exception remonte telle quelle.
   */
  search(
    query    : string,
    prefs   ?: Partial<SearchPreferences>,
    fuzzy    = true,
    maxDist  = 1,
    topK     = 10,
  ): [SearchResult[], SearchStatus] {
    if (!query || !query.trim()) throw new Error("La requête ne peut pas être vide.");
    if (maxDist < 0) throw new Error(`maxDist doit être >= 0, reçu : ${maxDist}`);
    if (topK < 1) throw new Error(`topK doit être >= 1, reçu : ${topK}`);
    if (this.catalog.size === 0) return [[], "MISS"];

    const fullPrefs: SearchPreferences = { ...defaultPrefs(), ...prefs };
    if (this.dirty) this.commit();

    const qLower   = query.trim().toLowerCase();
    const cacheKey = [qLower, fullPrefs.preferredType, fullPrefs.preferredNiche, fullPrefs.maxPrice,
      fullPrefs.minPrice, fullPrefs.userLocation, fullPrefs.minRating, fuzzy, maxDist, topK]
      .map(v => String(v)).join("|");
    const cached = this.cache.get(cacheKey);
    if (cached) return [cached.map(r => ({ ...r })), "CACHÉ"];

    const matchedTags = fuzzy
      ? this.dawg.fuzzySearch(qLower, maxDist)
      : this.dawg.autocomplete(qLower);
    if (matchedTags.length === 0) return [[], "MISS"];

    const candidateIds = new Set<number>();
    for (const tag of matchedTags) {
      for (const id of this.invertedIndex.get(tag)!.decompress()) candidateIds.add(id);
    }

    const results: SearchResult[] = [];
    for (const pid of candidateIds) {
      const meta       = this.catalog.get(pid)!;
      const bm25Raw    = this.bm25.score(pid, matchedTags);
      const finalScore = calculateFinalScore(pid, meta, bm25Raw, fullPrefs);
      if (finalScore === null) continue;
      results.push({
        id: pid, name: meta.name, type: meta.productType === 0 ? "PHYSICAL" : "DIGITAL",
        niche: meta.niche, price: meta.price, rating: meta.avgRating,
        reviews: meta.reviewCount, score: finalScore,
      });
    }

    results.sort((a, b) => b.score - a.score || a.id - b.id);
    const finalList = results.slice(0, topK);
    this.cache.put(cacheKey, finalList);
    return [finalList.map(r => ({ ...r })), "CALCULÉ"];
  }
}
