<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

final class SearchPreferences
{
    public function __construct(
        public ?ProductType $preferredType  = null,
        public ?string      $preferredNiche = null,
        public ?float       $maxPrice       = null,
        public ?float       $minPrice       = null,
        public ?string      $userLocation   = null,
        public float        $minRating      = 0.0,
    ) {}
}
