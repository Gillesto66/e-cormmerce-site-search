<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

final class ProductMeta
{
    /** Niche normalisée en minuscules (comme models.py). */
    public readonly string $niche;
    /** @var string[] */
    public readonly array $tags;

    /** @param string[] $tags */
    public function __construct(
        public readonly string      $name,
        public readonly ProductType $productType,
        string                      $niche,
        public readonly float       $price,
        public readonly ?string     $location,
        public readonly float       $avgRating,
        public readonly int         $reviewCount,
        array                       $tags,
    ) {
        if (!is_finite($avgRating) || $avgRating < 0.0 || $avgRating > 5.0)
            throw new \InvalidArgumentException("avgRating doit être dans [0.0, 5.0], reçu : {$avgRating}");
        if ($reviewCount < 0)
            throw new \InvalidArgumentException("reviewCount doit être >= 0, reçu : {$reviewCount}");
        if (!is_finite($price) || $price < 0)
            throw new \InvalidArgumentException("price doit être >= 0, reçu : {$price}");
        $this->niche = Unicode::lower($niche);
        $this->tags  = array_map('strval', array_values($tags));
    }
}
