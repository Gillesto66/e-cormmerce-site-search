<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

enum ProductType: int
{
    case PHYSICAL = 0;
    case DIGITAL  = 1;

    public static function fromString(string $value): self
    {
        return match (strtoupper($value)) {
            'PHYSICAL' => self::PHYSICAL,
            'DIGITAL'  => self::DIGITAL,
            default    => throw new \ValueError("ProductType invalide : '{$value}'"),
        };
    }
}
