<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * BM25 (Okapi BM25) in-memory sur les tags produits.
 * Constantes dans ScoringConstants.php.
 */
final class BM25Index
{
    /** @var array<string, array<int, int>> */
    private array $tf = [];
    /** @var array<string, int> */
    private array $df = [];
    /** @var array<int, int> */
    private array $dl = [];
    private int   $N     = 0;
    private float $avgdl = 0.0;

    /** @param string[] $tags */
    public function index(int $productId, array $tags): void
    {
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
    public function score(int $productId, array $queryTags): float
    {
        if ($this->N === 0 || $this->avgdl === 0.0) return 0.0;
        $total = 0.0;
        $dlD   = $this->dl[$productId] ?? 0;

        foreach ($queryTags as $raw) {
            $tag   = strtolower($raw);
            $tfVal = $this->tf[$tag][$productId] ?? 0;
            if ($tfVal === 0) continue;
            $dfVal = $this->df[$tag] ?? 0;
            $idf   = log(($this->N - $dfVal + 0.5) / ($dfVal + 0.5) + 1);
            $norm  = $tfVal * (BM25_K1 + 1)
                   / ($tfVal + BM25_K1 * (1 - BM25_B + BM25_B * $dlD / $this->avgdl));
            $total += $idf * $norm;
        }
        return $total;
    }
}
