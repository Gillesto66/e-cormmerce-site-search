/**
 * tagsearch/scoring.ts
 * Réalisée par Gillesto66 & Kiro
 * BM25Index + calculateFinalScore — portage fidèle de scoring.py
 *
 * Précision flottante :
 *   Constantes identiques à scoring.py. Math.log() en V8 peut diverger
 *   au 15e chiffre vs Python. Tolérance cross-langage : 1e-9.
 */

import { ProductMeta, ProductType, SearchPreferences } from "./models.js";

export const BM25_K1            = 1.5;
export const BM25_B             = 0.75;
export const BM25_CAP           = 10.0;
export const BM25_FLOOR         = 0.05;
export const QUALITY_EXPONENT   = 1.5;
export const PRIOR_MEAN         = 3.5;
export const PRIOR_WEIGHT       = 10.0;
export const TYPE_MISMATCH      = 0.1;
export const NICHE_BOOST        = 1.2;
export const PROXIMITY_BONUS    = 1.15;
export const PRICE_BUDGET_BOOST = 1.1;


export class BM25Index {
  private tf:    Map<string, Map<number, number>> = new Map();
  private df:    Map<string, number>              = new Map();
  private dl:    Map<number, number>              = new Map();
  private N      = 0;
  private avgdl  = 0;

  index(productId: number, tags: readonly string[]): void {
    const lower = tags.map(t => t.toLowerCase());
    this.dl.set(productId, lower.length);
    this.N++;
    let sum = 0; this.dl.forEach(v => (sum += v));
    this.avgdl = sum / this.N;
    for (const tag of lower) {
      if (!this.tf.has(tag)) this.tf.set(tag, new Map());
      const m    = this.tf.get(tag)!;
      const prev = m.get(productId) ?? 0;
      m.set(productId, prev + 1);
      if (prev === 0) this.df.set(tag, (this.df.get(tag) ?? 0) + 1);
    }
  }

  score(productId: number, queryTags: string[]): number {
    if (this.N === 0 || this.avgdl === 0) return 0;
    let total = 0;
    const dlD = this.dl.get(productId) ?? 0;
    for (const raw of queryTags) {
      const tag   = raw.toLowerCase();
      const tfVal = this.tf.get(tag)?.get(productId) ?? 0;
      if (tfVal === 0) continue;
      const dfVal = this.df.get(tag) ?? 0;
      const idf   = Math.log((this.N - dfVal + 0.5) / (dfVal + 0.5) + 1);
      const norm  = tfVal * (BM25_K1 + 1) / (tfVal + BM25_K1 * (1 - BM25_B + BM25_B * dlD / this.avgdl));
      total += idf * norm;
    }
    return total;
  }
}


export function calculateFinalScore(
  _productId : number,
  meta       : ProductMeta,
  bm25Raw    : number,
  prefs      : SearchPreferences,
): number | null {
  if (prefs.maxPrice !== undefined && meta.price > prefs.maxPrice) return null;
  if (prefs.minPrice !== undefined && meta.price < prefs.minPrice) return null;
  if (meta.avgRating < prefs.minRating) return null;

  const bm25Norm    = Math.max(Math.min(bm25Raw / BM25_CAP, 1.0), BM25_FLOOR);
  const bayesian    = (meta.reviewCount * meta.avgRating + PRIOR_MEAN * PRIOR_WEIGHT)
                    / (meta.reviewCount + PRIOR_WEIGHT);
  const qualityMult = Math.pow(bayesian / 5.0, QUALITY_EXPONENT);
  const typeFactor  = (prefs.preferredType !== undefined && meta.productType !== prefs.preferredType)
                    ? TYPE_MISMATCH : 1.0;
  const nicheFactor = (prefs.preferredNiche !== undefined
                    && meta.niche === prefs.preferredNiche.toLowerCase())
                    ? NICHE_BOOST : 1.0;
  const proximity   = (meta.location !== null && prefs.userLocation !== undefined
                    && meta.location.toLowerCase() === prefs.userLocation.toLowerCase())
                    ? PROXIMITY_BONUS : 1.0;
  const priceFactor = (prefs.maxPrice !== undefined && prefs.maxPrice > 0
                    && meta.price / prefs.maxPrice <= 0.5)
                    ? PRICE_BUDGET_BOOST : 1.0;

  const final = bm25Norm * qualityMult * typeFactor * nicheFactor * proximity * priceFactor;
  return Math.round(final * 10000) / 10000;
}
