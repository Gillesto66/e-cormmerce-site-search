<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * Postings list compressée : delta-encoding + VarInt. add() est O(1) (tampon),
 * flush() compresse en lot. Portage de CompressedPostingsList (Python).
 */
final class CompressedPostingsList
{
    private string $compressed = '';
    /** @var int[] */
    private array $pending = [];

    /** @param int[] $sortedIds */
    private static function encode(array $sortedIds): string
    {
        $out  = '';
        $prev = 0;
        foreach ($sortedIds as $id) {
            $out .= VarInt::encode($id - $prev);
            $prev = $id;
        }
        return $out;
    }

    public function add(int $productId): void
    {
        if ($productId < 0) {
            throw new \InvalidArgumentException("productId doit être >= 0, reçu : {$productId}");
        }
        $this->pending[] = $productId;
    }

    public function remove(int $productId): bool
    {
        $ids = $this->decompress();
        $at  = array_search($productId, $ids, true);
        if ($at === false) {
            return false;
        }
        array_splice($ids, (int) $at, 1);
        $this->compressed = self::encode($ids);
        $this->pending    = [];
        return true;
    }

    public function flush(): void
    {
        if ($this->pending === []) {
            return;
        }
        $this->compressed = self::encode($this->decompress());
        $this->pending    = [];
    }

    /** @return int[] */
    public function decompress(): array
    {
        $ids = [];
        $offset = 0;
        $current = 0;
        $len = strlen($this->compressed);
        while ($offset < $len) {
            [$delta, $offset] = VarInt::decode($this->compressed, $offset);
            $current += $delta;
            $ids[] = $current;
        }
        if ($this->pending !== []) {
            $ids = array_values(array_unique(array_merge($ids, $this->pending)));
            sort($ids);
        }
        return $ids;
    }

    public function size(): int
    {
        return count($this->decompress());
    }

    /** Octets de la représentation compressée (hors tampon d'écriture). */
    public function memoryBytes(): int
    {
        return strlen($this->compressed) + count($this->pending) * 16;
    }

    /** Injection directe d'octets (tests de robustesse sur données corrompues). */
    public function setCompressedForTest(string $bytes): void
    {
        $this->compressed = $bytes;
    }
}
