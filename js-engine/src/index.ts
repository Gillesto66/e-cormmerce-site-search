// tagsearch/index.ts — Réalisée par Gillesto66 & Kiro
export { SearchEngine } from "./engine.js";
export type { SearchResult, SearchStatus } from "./engine.js";
export { ProductType, createProductMeta, defaultPrefs, productTypeFromString } from "./models.js";
export type { ProductMeta, SearchPreferences } from "./models.js";
export { BM25Index, calculateFinalScore, round4 } from "./scoring.js";
export { DAWG, CompressedPostingsList, VarInt, LRUCache, compareCodePoints } from "./structures.js";
