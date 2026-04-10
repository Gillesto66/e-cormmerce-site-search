/**
 * tagsearch/engine.ts
 * Réalisée par Gillesto66 & Kiro
 * SearchEngine — portage fidèle de engine.py
 * Optimisé pour environnements Serverless (Vercel) : pas d'I/O bloquant,
 * état entièrement in-memory, reconstruction DAWG en batch.
 */
import { createProductMeta, defaultPrefs } from "./models.js";
import { BM25Index, calculateFinalScore } from "./scoring.js";
import { DAWG, LRUCache } from "./structures.js";
export class SearchEngine {
    allTags = [];
    dawg = new DAWG();
    invertedIndex = new Map();
    catalog = new Map();
    bm25 = new BM25Index();
    cache = new LRUCache(200);
    loadCatalog(data) {
        if (!Array.isArray(data.products) || data.products.length === 0) {
            console.warn("[tagsearch] Catalogue vide.");
            return;
        }
        for (const raw of data.products) {
            const r = raw;
            const meta = createProductMeta({
                name: r["name"], type: r["type"],
                niche: r["niche"], price: r["price"],
                location: r["location"] ?? null,
                avg_rating: r["avg_rating"],
                review_count: r["review_count"],
                tags: r["tags"],
            });
            this.addProduct(r["id"], meta);
        }
    }
    addProduct(productId, meta) {
        if (productId < 0)
            throw new Error(`productId doit être >= 0, reçu : ${productId}`);
        this.catalog.set(productId, meta);
        for (const tag of meta.tags) {
            const t = tag.toLowerCase();
            if (!this.invertedIndex.has(t)) {
                this.invertedIndex.set(t, new Set());
                this.allTags.push(t);
            }
            this.invertedIndex.get(t).add(productId);
        }
        this.bm25.index(productId, meta.tags);
        this.dawg = DAWG.build(this.allTags);
        this.cache.invalidate();
    }
    search(query, prefs, fuzzy = true, maxDist = 1, topK = 10) {
        if (!query || !query.trim())
            throw new Error("La requête ne peut pas être vide.");
        if (maxDist < 0)
            throw new Error(`maxDist doit être >= 0, reçu : ${maxDist}`);
        if (this.catalog.size === 0)
            return [[], "MISS"];
        const fullPrefs = { ...defaultPrefs(), ...prefs };
        const cacheKey = `${query.trim().toLowerCase()}|${JSON.stringify(fullPrefs)}`;
        const cached = this.cache.get(cacheKey);
        if (cached)
            return [cached, "CACHÉ"];
        const qLower = query.trim().toLowerCase();
        const matchedTags = fuzzy
            ? this.dawg.fuzzySearch(qLower, maxDist)
            : this.dawg.autocomplete(qLower);
        if (matchedTags.length === 0)
            return [[], "MISS"];
        const candidateIds = new Set();
        for (const tag of matchedTags) {
            this.invertedIndex.get(tag)?.forEach(id => candidateIds.add(id));
        }
        const results = [];
        for (const pid of candidateIds) {
            const meta = this.catalog.get(pid);
            if (!meta)
                continue;
            const bm25Raw = this.bm25.score(pid, matchedTags);
            const finalScore = calculateFinalScore(pid, meta, bm25Raw, fullPrefs);
            if (finalScore === null)
                continue;
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
//# sourceMappingURL=engine.js.map