/**
 * tagsearch/models.ts
 * Réalisée par Gillesto66 & Kiro
 * Structures de données métier — portage fidèle de models.py
 */

export enum ProductType {
  PHYSICAL = 0,
  DIGITAL  = 1,
}

export function productTypeFromString(value: string): ProductType {
  const upper = String(value).toUpperCase();
  if (upper === "PHYSICAL") return ProductType.PHYSICAL;
  if (upper === "DIGITAL")  return ProductType.DIGITAL;
  throw new Error(`ProductType invalide : '${value}'. Attendu : PHYSICAL | DIGITAL`);
}

export interface ProductMeta {
  readonly name        : string;
  readonly productType : ProductType;
  readonly niche       : string;       // normalisé en lowercase à la construction
  readonly price       : number;
  readonly location    : string | null;
  readonly avgRating   : number;       // 0.0 – 5.0
  readonly reviewCount : number;
  readonly tags        : readonly string[];
}

function requireFinite(name: string, value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} doit être un nombre fini, reçu : ${String(value)}`);
  }
  return value;
}

export function createProductMeta(raw: {
  name: string; type: string; niche: string; price: number;
  location: string | null; avg_rating: number; review_count: number;
  tags: string[];
}): ProductMeta {
  if (typeof raw.name !== "string") throw new Error(`name doit être une chaîne, reçu : ${String(raw.name)}`);
  if (typeof raw.niche !== "string") throw new Error(`niche doit être une chaîne, reçu : ${String(raw.niche)}`);
  if (!Array.isArray(raw.tags)) throw new Error("tags doit être un tableau de chaînes");
  const price       = requireFinite("price", raw.price);
  const avgRating   = requireFinite("avg_rating", raw.avg_rating);
  const reviewCount = requireFinite("review_count", raw.review_count);
  if (avgRating < 0 || avgRating > 5)
    throw new Error(`avg_rating doit être dans [0.0, 5.0], reçu : ${avgRating}`);
  if (reviewCount < 0 || !Number.isInteger(reviewCount))
    throw new Error(`review_count doit être un entier >= 0, reçu : ${reviewCount}`);
  if (price < 0)
    throw new Error(`price doit être >= 0, reçu : ${price}`);
  return {
    name        : raw.name,
    productType : productTypeFromString(raw.type),
    niche       : raw.niche.toLowerCase(),
    price,
    location    : raw.location ?? null,
    avgRating,
    reviewCount,
    tags        : raw.tags.map(t => String(t)),
  };
}

export interface SearchPreferences {
  preferredType  ?: ProductType;
  preferredNiche ?: string;
  maxPrice       ?: number;
  minPrice       ?: number;
  userLocation   ?: string;
  minRating       : number;   // défaut : 0
}

export function defaultPrefs(): SearchPreferences {
  return { minRating: 0 };
}
