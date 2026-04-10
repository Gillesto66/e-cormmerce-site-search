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
  const upper = value.toUpperCase();
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

export function createProductMeta(raw: {
  name: string; type: string; niche: string; price: number;
  location: string | null; avg_rating: number; review_count: number;
  tags: string[];
}): ProductMeta {
  if (raw.avg_rating < 0 || raw.avg_rating > 5)
    throw new Error(`avgRating doit être dans [0, 5], reçu : ${raw.avg_rating}`);
  if (raw.review_count < 0)
    throw new Error(`reviewCount doit être >= 0, reçu : ${raw.review_count}`);
  if (raw.price < 0)
    throw new Error(`price doit être >= 0, reçu : ${raw.price}`);
  return {
    name        : raw.name,
    productType : productTypeFromString(raw.type),
    niche       : raw.niche.toLowerCase(),
    price       : raw.price,
    location    : raw.location,
    avgRating   : raw.avg_rating,
    reviewCount : raw.review_count,
    tags        : raw.tags,
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
