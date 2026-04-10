// tagsearch/index.ts — Réalisée par Gillesto66 & Kiro
export { SearchEngine } from "./engine.js";
export type { SearchResult, SearchStatus } from "./engine.js";
export { ProductType, createProductMeta, defaultPrefs } from "./models.js";
export type { ProductMeta, SearchPreferences } from "./models.js";
export { BM25Index, calculateFinalScore } from "./scoring.js";
