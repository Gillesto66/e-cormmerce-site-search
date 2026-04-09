<?php
declare(strict_types=1);
namespace TagSearch;

enum ProductType: int {
    case PHYSICAL = 0;
    case DIGITAL  = 1;

    public static function fromString(string $value): self {
        return match (strtoupper($value)) {
            'PHYSICAL' => self::PHYSICAL,
            'DIGITAL'  => self::DIGITAL,
            default    => throw new \ValueError("ProductType invalide : '{$value}'"),
        };
    }
}

final readonly class ProductMeta {
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

final class SearchPreferences {
    public function __construct(
        public ?ProductType $preferredType  = null,
        public ?string      $preferredNiche = null,
        public ?float       $maxPrice       = null,
        public ?float       $minPrice       = null,
        public ?string      $userLocation   = null,
        public float        $minRating      = 0.0,
    ) {}
}
