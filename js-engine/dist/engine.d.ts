/**
 * tagsearch/engine.ts
 * Réalisée par Gillesto66 & Kiro
 * SearchEngine — portage fidèle de engine.py
 * Optimisé pour environnements Serverless (Vercel) : pas d'I/O bloquant,
 * état entièrement in-memory, reconstruction DAWG en batch.
 */
import { ProductMeta, SearchPreferences } from "./models.js";
export interface SearchResult {
    id: number;
    name: string;
    type: string;
    niche: string;
    price: number;
    rating: number;
    reviews: number;
    score: number;
}
export type SearchStatus = "CACHÉ" | "CALCULÉ" | "MISS";
export declare class SearchEngine {
    private allTags;
    private dawg;
    private invertedIndex;
    private catalog;
    private bm25;
    private cache;
    loadCatalog(data: {
        products: unknown[];
    }): void;
    addProduct(productId: number, meta: ProductMeta): void;
    search(query: string, prefs?: Partial<SearchPreferences>, fuzzy?: boolean, maxDist?: number, topK?: number): [SearchResult[], SearchStatus];
}
//# sourceMappingURL=engine.d.ts.map