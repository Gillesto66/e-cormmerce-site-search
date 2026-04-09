<?php
declare(strict_types=1);
namespace TagSearch;

/**
 * BM25Index + calculateFinalScore — portage fidèle de scoring.py
 *
 * Précision flottante PHP :
 *   PHP utilise IEEE 754 double (64 bits), identique à Python et JS.
 *   log() en PHP peut diverger au 15e chiffre vs Python.
 *   Tolérance cross-langage : 1e-9.
 */

// Constantes synchronisées avec shared-assets/catalog.json
const BM25_K1            = 1.5;
const BM25_B             = 0.75;
const BM25_CAP           = 10.0;
const BM25_FLOOR         = 0.05;
const QUALITY_EXPONENT   = 1.5;
const PRIOR_MEAN         = 3.5;
const PRIOR_WEIGHT       = 10.0;
const TYPE_MISMATCH      = 0.1;
const NICHE_BOOST        = 1.2;
const PROXIMITY_BONUS    = 1.15;
const PRICE_BUDGET_BOOST = 1.1;


final class BM25Index {
    /** @var array<string, array<int, int>> */
    private array $tf = [];
    /** @var array<string, int> */
    private array $df = [];
    /** @var array<int, int> */
    private array $dl = [];
    private int   $N      = 0;
    private float $avgdl  = 0.0;

    /** @param string[] $tags */
    public function index(int $productId, array $tags): void {
        $lower = array_map('strtolower', $tags);
        $this->dl[$productId] = count($lower);
        $this->N++;
        $this->avgdl = array_sum($this->dl) / $this->N;

        foreach ($lower as $tag) {
            $this->tf[$tag][$productId] = ($this->tf[$tag][$productId] ?? 0) + 1;
            if ($this->tf[$tag][$productId] === 1) {
                $this->df[$tag] = ($this->df[$tag] ?? 0) + 1;
            }
        }
    }

    /** @param string[] $queryTags */
    public function score(int $productId, array $queryTags): float {
        if ($this->N === 0 || $this->avgdl === 0.0) return 0.0;
        $total = 0.0;
        $dlD   = $this->dl[$productId] ?? 0;

        foreach ($queryTags as $raw) {
            $tag   = strtolower($raw);
            $tfVal = $this->tf[$tag][$productId] ?? 0;
            if ($tfVal === 0) continue;
            $dfVal = $this->df[$tag] ?? 0;
            $idf   = log(($this->N - $dfVal + 0.5) / ($dfVal + 0.5) + 1);
            $norm  = $tfVal * (BM25_K1 + 1) / ($tfVal + BM25_K1 * (1 - BM25_B + BM25_B * $dlD / $this->avgdl));
            $total += $idf * $norm;
        }
        return $total;
    }
}


final class Scorer {
    /** @param string[] $matchedTags */
    public static function calculateFinalScore(
        int               $productId,
        ProductMeta       $meta,
        float             $bm25Raw,
        SearchPreferences $prefs,
    ): ?float {
        // Filtres durs
        if ($prefs->maxPrice !== null && $meta->price > $prefs->maxPrice) return null;
        if ($prefs->minPrice !== null && $meta->price < $prefs->minPrice) return null;
        if ($meta->avgRating < $prefs->minRating) return null;

        // Dim 1 : BM25 normalisé
        $bm25Norm = max(min($bm25Raw / BM25_CAP, 1.0), BM25_FLOOR);

        // Dim 2 : Qualité Bayesian
        $bayesian    = ($meta->reviewCount * $meta->avgRating + PRIOR_MEAN * PRIOR_WEIGHT)
                     / ($meta->reviewCount + PRIOR_WEIGHT);
        $qualityMult = ($bayesian / 5.0) ** QUALITY_EXPONENT;

        // Dim 3 : Type + Niche
        $typeFactor  = ($prefs->preferredType !== null && $meta->productType !== $prefs->preferredType)
                     ? TYPE_MISMATCH : 1.0;
        $nicheFactor = ($prefs->preferredNiche !== null
                     && $meta->niche === strtolower($prefs->preferredNiche))
                     ? NICHE_BOOST : 1.0;

        // Dim 4 : Proximité
        $proximity = 1.0;
        if ($meta->location !== null && $prefs->userLocation !== null
            && strtolower($meta->location) === strtolower($prefs->userLocation)) {
            $proximity = PROXIMITY_BONUS;
        }

        // Dim 5 : Prix (filtre doux)
        $priceFactor = 1.0;
        if ($prefs->maxPrice !== null && $prefs->maxPrice > 0
            && $meta->price / $prefs->maxPrice <= 0.5) {
            $priceFactor = PRICE_BUDGET_BOOST;
        }

        $final = $bm25Norm * $qualityMult * $typeFactor * $nicheFactor * $proximity * $priceFactor;
        return round($final, 4);
    }
}
