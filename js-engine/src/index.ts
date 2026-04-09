export { SearchEngine } from "./engine.js";
export { ProductType, createProductMeta, defaultPrefs } from "./models.js";
export type { ProductMeta, SearchPreferences, SearchResult, SearchStatus } from "./engine.js";
export { BM25Index, calculateFinalScore } from "./scoring.js";
