/**
 * tagsearch/models.ts
 * Réalisée par Gillesto66 & Kiro
 * Structures de données métier — portage fidèle de models.py
 */
export var ProductType;
(function (ProductType) {
    ProductType[ProductType["PHYSICAL"] = 0] = "PHYSICAL";
    ProductType[ProductType["DIGITAL"] = 1] = "DIGITAL";
})(ProductType || (ProductType = {}));
export function productTypeFromString(value) {
    const upper = value.toUpperCase();
    if (upper === "PHYSICAL")
        return ProductType.PHYSICAL;
    if (upper === "DIGITAL")
        return ProductType.DIGITAL;
    throw new Error(`ProductType invalide : '${value}'. Attendu : PHYSICAL | DIGITAL`);
}
export function createProductMeta(raw) {
    if (raw.avg_rating < 0 || raw.avg_rating > 5)
        throw new Error(`avgRating doit être dans [0, 5], reçu : ${raw.avg_rating}`);
    if (raw.review_count < 0)
        throw new Error(`reviewCount doit être >= 0, reçu : ${raw.review_count}`);
    if (raw.price < 0)
        throw new Error(`price doit être >= 0, reçu : ${raw.price}`);
    return {
        name: raw.name,
        productType: productTypeFromString(raw.type),
        niche: raw.niche.toLowerCase(),
        price: raw.price,
        location: raw.location,
        avgRating: raw.avg_rating,
        reviewCount: raw.review_count,
        tags: raw.tags,
    };
}
export function defaultPrefs() {
    return { minRating: 0 };
}
//# sourceMappingURL=models.js.map