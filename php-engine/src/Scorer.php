<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * Scorer — re-ranking multidimensionnel Phase 2.
 * Formule : bm25_norm × quality_mult × type_factor × niche_boost × proximity × price_factor
 */
final class Scorer
{
    public static function calculateFinalScore(
        int               $productId,
        ProductMeta       $meta,
        float             $bm25Raw,
        SearchPreferences $prefs,
    ): ?float {
        // ── Filtres durs ──────────────────────────────────────────────────────
        if ($prefs->maxPrice !== null && $meta->price > $prefs->maxPrice) return null;
        if ($prefs->minPrice !== null && $meta->price < $prefs->minPrice) return null;
        if ($meta->avgRating < $prefs->minRating) return null;

        // ── Dim 1 : BM25 normalisé ────────────────────────────────────────────
        $bm25Norm = max(min($bm25Raw / BM25_CAP, 1.0), BM25_FLOOR);

        // ── Dim 2 : Qualité Bayesian ──────────────────────────────────────────
        $bayesian    = ($meta->reviewCount * $meta->avgRating + PRIOR_MEAN * PRIOR_WEIGHT)
                     / ($meta->reviewCount + PRIOR_WEIGHT);
        $qualityMult = ($bayesian / 5.0) ** QUALITY_EXPONENT;

        // ── Dim 3 : Type + Niche ──────────────────────────────────────────────
        $typeFactor  = ($prefs->preferredType !== null && $meta->productType !== $prefs->preferredType)
                     ? TYPE_MISMATCH : 1.0;
        $nicheFactor = ($prefs->preferredNiche !== null
                     && $meta->niche === Unicode::lower($prefs->preferredNiche))
                     ? NICHE_BOOST : 1.0;

        // ── Dim 4 : Proximité ─────────────────────────────────────────────────
        $proximity = 1.0;
        if ($meta->location !== null && $prefs->userLocation !== null
            && Unicode::lower($meta->location) === Unicode::lower($prefs->userLocation)) {
            $proximity = PROXIMITY_BONUS;
        }

        // ── Dim 5 : Prix (filtre doux) ────────────────────────────────────────
        $priceFactor = 1.0;
        if ($prefs->maxPrice !== null && $prefs->maxPrice > 0
            && $meta->price / $prefs->maxPrice <= 0.5) {
            $priceFactor = PRICE_BUDGET_BOOST;
        }

        $final = $bm25Norm * $qualityMult * $typeFactor * $nicheFactor * $proximity * $priceFactor;
        return Unicode::round4($final);
    }
}
