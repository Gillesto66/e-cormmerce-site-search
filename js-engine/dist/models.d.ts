/**
 * tagsearch/models.ts
 * Réalisée par Gillesto66 & Kiro
 * Structures de données métier — portage fidèle de models.py
 */
export declare enum ProductType {
    PHYSICAL = 0,
    DIGITAL = 1
}
export declare function productTypeFromString(value: string): ProductType;
export interface ProductMeta {
    readonly name: string;
    readonly productType: ProductType;
    readonly niche: string;
    readonly price: number;
    readonly location: string | null;
    readonly avgRating: number;
    readonly reviewCount: number;
    readonly tags: readonly string[];
}
export declare function createProductMeta(raw: {
    name: string;
    type: string;
    niche: string;
    price: number;
    location: string | null;
    avg_rating: number;
    review_count: number;
    tags: string[];
}): ProductMeta;
export interface SearchPreferences {
    preferredType?: ProductType;
    preferredNiche?: string;
    maxPrice?: number;
    minPrice?: number;
    userLocation?: string;
    minRating: number;
}
export declare function defaultPrefs(): SearchPreferences;
//# sourceMappingURL=models.d.ts.map