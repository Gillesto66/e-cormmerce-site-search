/**
 * tagsearch/scoring.ts
 * Réalisée par Gillesto66 & Kiro
 * BM25Index + calculateFinalScore — portage fidèle de scoring.py
 *
 * Précision flottante :
 *   Constantes identiques à scoring.py. Math.log() en V8 peut diverger
 *   au 15e chiffre vs Python. Tolérance cross-langage : 1e-9.
 *   L'arrondi à 4 décimales est EXACT (round4) : `Math.round(x * 1e4) / 1e4` donne un
 *   résultat différent de Python quand x * 1e4 tombe sur .5 par erreur d'arrondi.
 */

import { ProductMeta, SearchPreferences } from "./models.js";

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

/**
 * Arrondi à 4 décimales identique à `round(x, 4)` de Python (valeur exacte du double,
 * égalité parfaite arrondie au pair). `toFixed` travaille sur la valeur exacte ; seuls
 * les x = m/32 (m impair) sont des égalités exactes, traitées explicitement.
 */
export function round4(x: number): number {
  const m = x * 32;                       // exact : multiplication par une puissance de 2
  if (Number.isInteger(m) && Math.abs(m) % 2 === 1) {
    const t = (m * 625) / 2;              // x * 1e4, exact ici
    const lo = Math.floor(t);
    return (lo % 2 === 0 ? lo : lo + 1) / 1e4;
  }
  return Number(x.toFixed(4));
}

export class BM25Index {
  private tf:    Map<string, Map<number, number>> = new Map();
  private df:    Map<string, number>              = new Map();
  private dl:    Map<number, number>              = new Map();
  private N      = 0;
  private avgdl  = 0;
  private dlSum  = 0;      // somme courante : avgdl en O(1) (et non O(N) par ajout)

  get docCount(): number { return this.N; }
  docFreq(tag: string): number { return this.df.get(tag.toLowerCase()) ?? 0; }

  index(productId: number, tags: readonly string[]): void {
    if (this.dl.has(productId)) {
      throw new Error(`BM25: produit ${productId} déjà indexé — appeler remove() d'abord.`);
    }
    const lower = tags.map(t => t.toLowerCase());
    this.dl.set(productId, lower.length);
    this.dlSum += lower.length;
    this.N++;
    this.avgdl = this.dlSum / this.N;
    for (const tag of lower) {
      let postings = this.tf.get(tag);
      if (!postings) { postings = new Map(); this.tf.set(tag, postings); }
      const prev = postings.get(productId) ?? 0;
      postings.set(productId, prev + 1);
      if (prev === 0) this.df.set(tag, (this.df.get(tag) ?? 0) + 1);
    }
  }

  /** Désindexe un produit. `tags` : les tags passés à index(). */
  remove(productId: number, tags: readonly string[]): void {
    const len = this.dl.get(productId);
    if (len === undefined) return;
    this.dl.delete(productId);
    this.dlSum -= len;
    this.N--;
    this.avgdl = this.N > 0 ? this.dlSum / this.N : 0;
    for (const tag of new Set(tags.map(t => t.toLowerCase()))) {
      const postings = this.tf.get(tag);
      if (postings && postings.delete(productId)) {
        this.df.set(tag, (this.df.get(tag) ?? 1) - 1);
        if (postings.size === 0) { this.tf.delete(tag); this.df.delete(tag); }
      }
    }
  }

  score(productId: number, queryTags: readonly string[]): number {
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
  return round4(final);
}
