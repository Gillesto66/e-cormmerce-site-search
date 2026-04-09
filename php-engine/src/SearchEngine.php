<?php
declare(strict_types=1);
namespace TagSearch;

/**
 * SearchEngine PHP — portage fidèle de engine.py
 * Compatible Laravel via Service Provider (bind dans AppServiceProvider).
 *
 * Usage Laravel :
 *   $this->app->singleton(SearchEngine::class, fn() => new SearchEngine());
 *   $engine = app(SearchEngine::class);
 *   $engine->loadCatalog(storage_path('catalog.json'));
 */
final class SearchEngine {
    /** @var array<string, int[]> */
    private array $invertedIndex = [];
    /** @var string[] */
    private array $allTags = [];
    /** @var array<int, ProductMeta> */
    private array $catalog = [];
    private BM25Index $bm25;
    /** @var array<string, array<int, array<string, mixed>>> */
    private array $lruCache = [];
    private int   $cacheCapacity;

    public function __construct(int $cacheSize = 200) {
        $this->bm25          = new BM25Index();
        $this->cacheCapacity = $cacheSize;
    }

    public function loadCatalog(string $path): void {
        if (!file_exists($path))
            throw new \RuntimeException("Catalogue introuvable : {$path}");
        $json = file_get_contents($path);
        if ($json === false)
            throw new \RuntimeException("Impossible de lire : {$path}");
        $data = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
        foreach ($data['products'] as $raw) {
            $meta = new ProductMeta(
                name        : $raw['name'],
                productType : ProductType::fromString($raw['type']),
                niche       : strtolower($raw['niche']),
                price       : (float) $raw['price'],
                location    : $raw['location'] ?? null,
                avgRating   : (float) $raw['avg_rating'],
                reviewCount : (int)   $raw['review_count'],
                tags        : $raw['tags'],
            );
            $this->addProduct((int) $raw['id'], $meta);
        }
    }

    public function addProduct(int $productId, ProductMeta $meta): void {
        if ($productId < 0)
            throw new \InvalidArgumentException("productId doit être >= 0, reçu : {$productId}");
        $this->catalog[$productId] = $meta;
        foreach ($meta->tags as $tag) {
            $t = strtolower($tag);
            if (!isset($this->invertedIndex[$t])) {
                $this->invertedIndex[$t] = [];
                $this->allTags[]         = $t;
            }
            if (!in_array($productId, $this->invertedIndex[$t], true))
                $this->invertedIndex[$t][] = $productId;
        }
        $this->bm25->index($productId, $meta->tags);
        $this->lruCache = []; // invalidation simple
    }

    /**
     * Recherche multidimensionnelle.
     *
     * @return array{results: array<int, array<string, mixed>>, status: string}
     */
    public function search(
        string            $query,
        ?SearchPreferences $prefs    = null,
        bool              $fuzzy    = true,
        int               $maxDist  = 1,
        int               $topK     = 10,
    ): array {
        if (trim($query) === '')
            throw new \InvalidArgumentException("La requête ne peut pas être vide.");
        if ($maxDist < 0)
            throw new \InvalidArgumentException("maxDist doit être >= 0, reçu : {$maxDist}");
        if (empty($this->catalog))
            return ['results' => [], 'status' => 'MISS'];

        $prefs    ??= new SearchPreferences();
        $cacheKey   = strtolower(trim($query)) . '|' . serialize($prefs);

        if (isset($this->lruCache[$cacheKey])) {
            // Move to end (LRU)
            $val = $this->lruCache[$cacheKey];
            unset($this->lruCache[$cacheKey]);
            $this->lruCache[$cacheKey] = $val;
            return ['results' => $val, 'status' => 'CACHÉ'];
        }

        $qLower      = strtolower(trim($query));
        $matchedTags = $fuzzy
            ? $this->fuzzySearch($qLower, $maxDist)
            : $this->autocomplete($qLower);

        if (empty($matchedTags))
            return ['results' => [], 'status' => 'MISS'];

        $candidateIds = [];
        foreach ($matchedTags as $tag) {
            foreach ($this->invertedIndex[$tag] ?? [] as $pid)
                $candidateIds[$pid] = true;
        }

        $results = [];
        foreach (array_keys($candidateIds) as $pid) {
            $meta      = $this->catalog[$pid] ?? null;
            if ($meta === null) continue;
            $bm25Raw   = $this->bm25->score($pid, $matchedTags);
            $score     = Scorer::calculateFinalScore($pid, $meta, $bm25Raw, $prefs);
            if ($score === null) continue;
            $results[] = [
                'id'      => $pid,
                'name'    => $meta->name,
                'type'    => $meta->productType->name,
                'niche'   => $meta->niche,
                'price'   => $meta->price,
                'rating'  => $meta->avgRating,
                'reviews' => $meta->reviewCount,
                'score'   => $score,
            ];
        }

        usort($results, fn($a, $b) => $b['score'] <=> $a['score']);
        $finalList = array_slice($results, 0, $topK);

        // LRU put
        $this->lruCache[$cacheKey] = $finalList;
        if (count($this->lruCache) > $this->cacheCapacity)
            array_shift($this->lruCache);

        return ['results' => $finalList, 'status' => 'CALCULÉ'];
    }

    // ── Trie/DAWG simplifié (PHP) ────────────────────────────────────────────
    // PHP n'a pas de DAWG natif. On utilise un Trie en tableau associatif.
    // Pour la production, utiliser une extension C ou un service dédié.

    /** @return string[] */
    private function autocomplete(string $prefix): array {
        $results = [];
        foreach (array_keys($this->invertedIndex) as $tag) {
            if (str_starts_with($tag, $prefix)) $results[] = $tag;
        }
        return $results;
    }

    /** @return string[] */
    private function fuzzySearch(string $query, int $maxDist): array {
        $results = [];
        foreach (array_keys($this->invertedIndex) as $tag) {
            $dist = levenshtein($query, $tag);
            if ($dist <= $maxDist) $results[] = [$tag, $dist];
        }
        usort($results, fn($a, $b) => $a[1] <=> $b[1]);
        return array_column($results, 0);
    }
}
