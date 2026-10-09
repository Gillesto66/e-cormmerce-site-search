<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * Utilitaires Unicode — parité avec Python/JS.
 *
 * Pourquoi : strtolower() et levenshtein() de PHP travaillent sur des OCTETS.
 * « É » n'est pas abaissé par strtolower() (ASCII seulement depuis PHP 8.2) et
 * « pâtisserie » est à distance 2 de « patisserie » (« â » = 2 octets) au lieu de 1.
 * Tout le moteur passe donc par ces fonctions (points de code Unicode, UTF-8).
 */
final class Unicode
{
    public static function lower(string $s): string
    {
        return mb_strtolower($s, 'UTF-8');
    }

    /** @return string[] points de code, un élément par caractère */
    public static function chars(string $s): array
    {
        return $s === '' ? [] : mb_str_split($s, 1, 'UTF-8');
    }

    /** Ordre des points de code Unicode (== ordre des octets en UTF-8). */
    public static function compare(string $a, string $b): int
    {
        return strcmp($a, $b) <=> 0;
    }

    /**
     * Arrondi à 4 décimales identique à round(x, 4) de Python : valeur exacte du double,
     * égalité parfaite arrondie au pair. round() de PHP 8.2 applique un « pré-arrondi »
     * à 15 chiffres qui diverge sur les quasi-égalités ; sprintf('%.4f') travaille sur la
     * valeur exacte. Seuls les x = m/32 (m impair) sont des égalités exactes.
     */
    public static function round4(float $x): float
    {
        $m = $x * 32.0;                              // exact : puissance de 2
        if ($m === floor($m) && fmod(abs($m), 2.0) === 1.0) {
            $t  = ($m * 625.0) / 2.0;                // x * 1e4, exact ici
            $lo = floor($t);
            return (fmod($lo, 2.0) === 0.0 ? $lo : $lo + 1.0) / 1e4;
        }
        return (float) sprintf('%.4F', $x);
    }
}
