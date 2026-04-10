<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

final readonly class ProductMeta
{
    /** @param string[] $tags */
    public function __construct(
        public string      $name,
        public ProductType $productType,
        public string      $niche,
        public float       $price,
        public ?string     $location,
        public float       $avgRating,
        public int         $reviewCount,
        public array       $tags,
    ) {
        if ($avgRating < 0.0 || $avgRating > 5.0)
            throw new \InvalidArgumentException("avgRating doit être dans [0.0, 5.0], reçu : {$avgRating}");
        if ($reviewCount < 0)
            throw new \InvalidArgumentException("reviewCount doit être >= 0, reçu : {$reviewCount}");
        if ($price < 0)
            throw new \InvalidArgumentException("price doit être >= 0, reçu : {$price}");
    }
}
