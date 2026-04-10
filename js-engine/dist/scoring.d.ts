/**
 * tagsearch/scoring.ts
 * Réalisée par Gillesto66 & Kiro
 * BM25Index + calculateFinalScore — portage fidèle de scoring.py
 *
 * Précision flottante :
 *   Constantes identiques à scoring.py. Math.log() en V8 peut diverger
 *   au 15e chiffre vs Python. Tolérance cross-langage : 1e-9.
 */
import { ProductMeta, SearchPreferences } from "./models.js";
export declare const BM25_K1 = 1.5;
export declare const BM25_B = 0.75;
export declare const BM25_CAP = 10;
export declare const BM25_FLOOR = 0.05;
export declare const QUALITY_EXPONENT = 1.5;
export declare const PRIOR_MEAN = 3.5;
export declare const PRIOR_WEIGHT = 10;
export declare const TYPE_MISMATCH = 0.1;
export declare const NICHE_BOOST = 1.2;
export declare const PROXIMITY_BONUS = 1.15;
export declare const PRICE_BUDGET_BOOST = 1.1;
export declare class BM25Index {
    private tf;
    private df;
    private dl;
    private N;
    private avgdl;
    index(productId: number, tags: readonly string[]): void;
    score(productId: number, queryTags: string[]): number;
}
export declare function calculateFinalScore(_productId: number, meta: ProductMeta, bm25Raw: number, prefs: SearchPreferences): number | null;
//# sourceMappingURL=scoring.d.ts.map