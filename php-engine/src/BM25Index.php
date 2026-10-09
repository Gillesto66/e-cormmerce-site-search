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
    private int   $dlSum = 0;   // somme courante : avgdl en O(1) (et non array_sum O(N) par ajout)

    public function docCount(): int
    {
        return $this->N;
    }

    public function docFreq(string $tag): int
    {
        return $this->df[Unicode::lower($tag)] ?? 0;
    }

    /** @param string[] $tags */
    public function index(int $productId, array $tags): void
    {
        if (isset($this->dl[$productId])) {
            throw new \LogicException("BM25: produit {$productId} déjà indexé — appeler remove() d'abord.");
        }
        $lower = array_map([Unicode::class, 'lower'], $tags);
        $this->dl[$productId] = count($lower);
        $this->dlSum += count($lower);
        $this->N++;
        $this->avgdl = $this->dlSum / $this->N;

        foreach ($lower as $tag) {
            $prev = $this->tf[$tag][$productId] ?? 0;
            $this->tf[$tag][$productId] = $prev + 1;
            if ($prev === 0) {
                $this->df[$tag] = ($this->df[$tag] ?? 0) + 1;
            }
        }
    }

    /**
     * Désindexe un produit.
     * @param string[] $tags les tags passés à index()
     */
    public function remove(int $productId, array $tags): void
    {
        if (!isset($this->dl[$productId])) {
            return;
        }
        $this->dlSum -= $this->dl[$productId];
        unset($this->dl[$productId]);
        $this->N--;
        $this->avgdl = $this->N > 0 ? $this->dlSum / $this->N : 0.0;

        foreach (array_unique(array_map([Unicode::class, 'lower'], $tags)) as $tag) {
            if (isset($this->tf[$tag][$productId])) {
                unset($this->tf[$tag][$productId]);
                $this->df[$tag]--;
                if ($this->tf[$tag] === []) {
                    unset($this->tf[$tag], $this->df[$tag]);
                }
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
            $tag   = Unicode::lower((string) $raw);
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
