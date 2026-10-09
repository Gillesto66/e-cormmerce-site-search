<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * DAWG (Directed Acyclic Word Graph) — algorithme de Daciuk et al., portage de structures.py.
 * Immuable après finish() : reconstruire (DAWG::build) quand le vocabulaire change.
 */
final class DAWG
{
    public readonly DAWGNode $root;
    private int $nextId = 0;
    /** @var array<string, DAWGNode> */
    private array $minimized = [];
    /** @var string[] */
    private array $lastChars = [];
    private bool $hasWord = false;
    /** @var array<int, array{0: DAWGNode, 1: string, 2: DAWGNode}> */
    private array $unchecked = [];

    public function __construct()
    {
        $this->root = $this->newNode();
    }

    private function newNode(): DAWGNode
    {
        return new DAWGNode($this->nextId++);
    }

    private function structuralKey(DAWGNode $node): string
    {
        $chars = array_map('strval', array_keys($node->children));
        usort($chars, [Unicode::class, 'compare']);
        $parts = [];
        foreach ($chars as $c) {
            $parts[] = $c . "\x01" . $node->children[$c]->id;
        }
        return ($node->isTerminal ? '1' : '0') . "\x02" . implode("\x03", $parts);
    }

    private function minimize(int $downTo): void
    {
        for ($i = count($this->unchecked) - 1; $i >= $downTo; $i--) {
            [$parent, $char, $child] = $this->unchecked[$i];
            $key = $this->structuralKey($child);
            if (isset($this->minimized[$key])) {
                $parent->children[$char] = $this->minimized[$key];
            } else {
                $this->minimized[$key] = $child;
            }
            array_pop($this->unchecked);
        }
    }

    /** Les mots doivent être insérés par ordre strictement croissant (points de code). */
    public function insert(string $word): void
    {
        $word  = Unicode::lower($word);
        $chars = Unicode::chars($word);
        $last  = implode('', $this->lastChars);
        if ($this->hasWord && Unicode::compare($word, $last) <= 0) {
            throw new \InvalidArgumentException("DAWG: insertion hors ordre — '{$word}' après '{$last}'.");
        }
        $common = 0;
        $limit  = min(count($chars), count($this->lastChars));
        while ($common < $limit && $chars[$common] === $this->lastChars[$common]) {
            $common++;
        }
        $this->minimize($common);
        $node = $this->unchecked === [] ? $this->root : $this->unchecked[count($this->unchecked) - 1][2];
        foreach (array_slice($chars, $common) as $char) {
            $new = $this->newNode();
            $node->children[$char] = $new;
            $this->unchecked[] = [$node, $char, $new];
            $node = $new;
        }
        $node->isTerminal = true;
        $this->lastChars  = $chars;
        $this->hasWord    = true;
    }

    public function finish(): void
    {
        $this->minimize(0);
    }

    /** @param iterable<string|int> $tags */
    public static function build(iterable $tags): self
    {
        $set = [];
        foreach ($tags as $t) {
            $set[Unicode::lower((string) $t)] = true;       // dédoublonnage
        }
        $words = array_map('strval', array_keys($set));     // "2024" devient une clé entière : on re-caste
        usort($words, [Unicode::class, 'compare']);
        $dawg = new self();
        foreach ($words as $w) {
            $dawg->insert($w);
        }
        $dawg->finish();
        return $dawg;
    }

    public function contains(string $word): bool
    {
        $node = $this->root;
        foreach (Unicode::chars(Unicode::lower($word)) as $c) {
            if (!isset($node->children[$c])) {
                return false;
            }
            $node = $node->children[$c];
        }
        return $node->isTerminal;
    }

    /** @return string[] tags commençant par $prefix, triés par points de code */
    public function autocomplete(string $prefix): array
    {
        $prefix = Unicode::lower($prefix);
        $node = $this->root;
        foreach (Unicode::chars($prefix) as $c) {
            if (!isset($node->children[$c])) {
                return [];
            }
            $node = $node->children[$c];
        }
        $results = [];
        $this->dfs($node, $prefix, $results);
        usort($results, [Unicode::class, 'compare']);
        return $results;
    }

    /** @param string[] $results */
    private function dfs(DAWGNode $node, string $path, array &$results): void
    {
        if ($node->isTerminal) {
            $results[] = $path;
        }
        foreach ($node->children as $char => $child) {
            $this->dfs($child, $path . $char, $results);
        }
    }

    /** @return string[] tags à distance de Levenshtein <= $maxDistance, triés par (distance, tag) */
    public function fuzzySearch(string $query, int $maxDistance = 1): array
    {
        $q   = Unicode::chars(Unicode::lower($query));
        $res = [];
        $init = range(0, count($q));
        foreach ($this->root->children as $char => $child) {
            $this->fuzzyDfs($child, (string) $char, (string) $char, $q, $init, $maxDistance, $res);
        }
        usort($res, static fn(array $a, array $b): int => $a[0] <=> $b[0] ?: Unicode::compare($a[1], $b[1]));
        return array_column($res, 1);
    }

    /**
     * @param string[] $query
     * @param int[]    $prevRow
     * @param array<int, array{0: int, 1: string}> $results
     */
    private function fuzzyDfs(DAWGNode $node, string $char, string $path, array $query,
                              array $prevRow, int $maxDist, array &$results): void
    {
        $n   = count($query);
        $cur = [$prevRow[0] + 1];
        $min = $cur[0];
        for ($col = 1; $col <= $n; $col++) {
            $v = min($cur[$col - 1] + 1, $prevRow[$col] + 1, $prevRow[$col - 1] + ($query[$col - 1] === $char ? 0 : 1));
            $cur[] = $v;
            if ($v < $min) {
                $min = $v;
            }
        }
        if ($min > $maxDist) {
            return;
        }
        if ($cur[$n] <= $maxDist && $node->isTerminal) {
            $results[] = [$cur[$n], $path];
        }
        foreach ($node->children as $next => $child) {
            $this->fuzzyDfs($child, (string) $next, $path . $next, $query, $cur, $maxDist, $results);
        }
    }

    /** Nombre de nœuds distincts (parcours itératif). */
    public function nodeCount(): int
    {
        $seen  = [$this->root->id => true];
        $stack = [$this->root];
        while ($stack !== []) {
            $node = array_pop($stack);
            foreach ($node->children as $child) {
                if (!isset($seen[$child->id])) {
                    $seen[$child->id] = true;
                    $stack[] = $child;
                }
            }
        }
        return count($seen);
    }
}
