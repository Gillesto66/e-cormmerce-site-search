<?php
// Réalisée par Gillesto66 & Kiro
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
 *
 * Indexation paresseuse : addProduct()/addProducts() n'enregistrent que les données ;
 * le DAWG est reconstruit UNE fois (premier search() suivant, ou commit()).
 * Nécessite l'extension mbstring (minuscules et découpage Unicode).
 */
final class SearchEngine {
    /** @var array<string, CompressedPostingsList> */
    private array $invertedIndex = [];
    /** @var array<int, ProductMeta> */
    private array $catalog = [];
    private BM25Index $bm25;
    private DAWG $dawg;
    /** @var array<string, bool> postings à compresser au prochain commit */
    private array $dirtyTags = [];
    private bool  $vocabChanged = false;
    /** @var array<string, array<int, array<string, mixed>>> */
    private array $lruCache = [];
    private int   $cacheCapacity;

    public function __construct(int $cacheSize = 200) {
        if ($cacheSize <= 0)
            throw new \InvalidArgumentException("cacheSize doit être > 0, reçu : {$cacheSize}");
        $this->bm25          = new BM25Index();
        $this->dawg          = new DAWG();
        $this->cacheCapacity = $cacheSize;
    }

    /** Charge un catalogue JSON (format shared-assets/catalog.json). Atomique : tout ou rien. */
    public function loadCatalog(string $path): void {
        if (!file_exists($path))
            throw new \RuntimeException("Catalogue introuvable : {$path}");
        $json = file_get_contents($path);
        if ($json === false)
            throw new \RuntimeException("Impossible de lire : {$path}");
        try {
            $data = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
        } catch (\JsonException $e) {
            throw new \InvalidArgumentException("JSON malformé dans {$path} : {$e->getMessage()}", 0, $e);
        }
        $products = is_array($data) ? ($data['products'] ?? []) : [];
        if (!is_array($products) || $products === [])
            return;

        $parsed = [];
        foreach ($products as $raw) {
            $id = is_array($raw) ? ($raw['id'] ?? '?') : '?';
            try {
                $parsed[] = [self::intField($raw, 'id'), self::metaFromArray($raw)];
            } catch (\Throwable $e) {
                throw new \InvalidArgumentException("Produit invalide (id={$id}) : {$e->getMessage()}", 0, $e);
            }
        }
        $this->addProducts($parsed);
    }

    /** @param mixed $raw */
    private static function metaFromArray(mixed $raw): ProductMeta {
        if (!is_array($raw))
            throw new \InvalidArgumentException('produit : objet attendu');
        foreach (['name', 'type', 'niche', 'price', 'avg_rating', 'review_count', 'tags'] as $k) {
            if (!array_key_exists($k, $raw))
                throw new \InvalidArgumentException("champ manquant : {$k}");
        }
        foreach (['price', 'avg_rating'] as $k) {
            if (!is_int($raw[$k]) && !is_float($raw[$k]))
                throw new \InvalidArgumentException("{$k} doit être un nombre");
        }
        if (!is_array($raw['tags']))
            throw new \InvalidArgumentException('tags doit être un tableau');
        return new ProductMeta(
            name        : (string) $raw['name'],
            productType : ProductType::fromString((string) $raw['type']),
            niche       : (string) $raw['niche'],
            price       : (float) $raw['price'],
            location    : isset($raw['location']) ? (string) $raw['location'] : null,
            avgRating   : (float) $raw['avg_rating'],
            reviewCount : self::intField($raw, 'review_count'),
            tags        : $raw['tags'],
        );
    }

    /** @param mixed $raw */
    private static function intField(mixed $raw, string $key): int {
        if (!is_array($raw) || !array_key_exists($key, $raw) || !is_int($raw[$key]))
            throw new \InvalidArgumentException("{$key} doit être un entier");
        return $raw[$key];
    }

    /**
     * Enregistre un produit ; l'index est mis à jour au prochain search() ou commit().
     * Un identifiant déjà présent est REMPLACÉ proprement (postings et BM25 mis à jour).
     */
    public function addProduct(int $productId, ProductMeta $meta): void {
        $this->add($productId, $meta);
        $this->lruCache = [];
    }

    /**
     * Ajoute un lot puis reconstruit l'index une seule fois.
     * @param iterable<array{0: int, 1: ProductMeta}> $items
     */
    public function addProducts(iterable $items): int {
        $count = 0;
        foreach ($items as [$id, $meta]) {
            $this->add($id, $meta);
            $count++;
        }
        $this->lruCache = [];
        $this->commit();
        return $count;
    }

    public function removeProduct(int $productId): bool {
        if (!isset($this->catalog[$productId]))
            return false;
        $this->remove($productId);
        $this->lruCache = [];
        return true;
    }

    /** Compresse les postings modifiés et reconstruit le DAWG si le vocabulaire a changé. */
    public function commit(): void {
        foreach (array_keys($this->dirtyTags) as $tag) {
            ($this->invertedIndex[$tag] ?? null)?->flush();
        }
        $this->dirtyTags = [];
        if ($this->vocabChanged) {
            $this->dawg         = DAWG::build(array_keys($this->invertedIndex));
            $this->vocabChanged = false;
        }
    }

    /** Vide le cache des résultats (mesures hors cache, tests). */
    public function clearCache(): void {
        $this->lruCache = [];
    }

    public function isDirty(): bool {
        return $this->dirtyTags !== [] || $this->vocabChanged;
    }

    private function add(int $productId, ProductMeta $meta): void {
        if ($productId < 0)
            throw new \InvalidArgumentException("productId doit être >= 0, reçu : {$productId}");
        if (isset($this->catalog[$productId]))
            $this->remove($productId);

        $this->catalog[$productId] = $meta;
        foreach (array_unique(array_map([Unicode::class, 'lower'], $meta->tags)) as $t) {
            if (!isset($this->invertedIndex[$t])) {
                $this->invertedIndex[$t] = new CompressedPostingsList();
                $this->vocabChanged      = true;
            }
            $this->invertedIndex[$t]->add($productId);
            $this->dirtyTags[$t] = true;
        }
        $this->bm25->index($productId, $meta->tags);
    }

    private function remove(int $productId): void {
        $meta = $this->catalog[$productId];
        unset($this->catalog[$productId]);
        foreach (array_unique(array_map([Unicode::class, 'lower'], $meta->tags)) as $t) {
            $postings = $this->invertedIndex[$t];
            $postings->remove($productId);
            if ($postings->size() === 0) {
                unset($this->invertedIndex[$t], $this->dirtyTags[$t]);
                $this->vocabChanged = true;
            } else {
                $this->dirtyTags[$t] = true;
            }
        }
        $this->bm25->remove($productId, $meta->tags);
    }

    /**
     * Recherche multidimensionnelle. Ordre déterministe : score décroissant puis id croissant ;
     * tags appariés ordonnés (distance, tag). Lève \InvalidArgumentException si la requête est
     * vide, $maxDist < 0 ou $topK < 1 ; toute autre exception remonte telle quelle.
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
        if ($topK < 1)
            throw new \InvalidArgumentException("topK doit être >= 1, reçu : {$topK}");
        if ($this->catalog === [])
            return ['results' => [], 'status' => 'MISS'];

        $prefs ??= new SearchPreferences();
        if ($this->isDirty())
            $this->commit();

        $qLower   = Unicode::lower(trim($query));
        $cacheKey = implode('|', [
            $qLower, $prefs->preferredType?->name ?? '', $prefs->preferredNiche ?? '',
            serialize($prefs->maxPrice), serialize($prefs->minPrice), $prefs->userLocation ?? '',
            serialize($prefs->minRating), $fuzzy ? '1' : '0', $maxDist, $topK,
        ]);

        if (isset($this->lruCache[$cacheKey])) {
            $val = $this->lruCache[$cacheKey];          // LRU : déplace en fin
            unset($this->lruCache[$cacheKey]);
            $this->lruCache[$cacheKey] = $val;
            return ['results' => $val, 'status' => 'CACHÉ'];
        }

        $matchedTags = $fuzzy
            ? $this->dawg->fuzzySearch($qLower, $maxDist)
            : $this->dawg->autocomplete($qLower);

        if ($matchedTags === [])
            return ['results' => [], 'status' => 'MISS'];

        $candidateIds = [];
        foreach ($matchedTags as $tag) {
            foreach ($this->invertedIndex[$tag]->decompress() as $pid)
                $candidateIds[$pid] = true;
        }

        $results = [];
        foreach (array_keys($candidateIds) as $pid) {
            $meta    = $this->catalog[$pid];
            $bm25Raw = $this->bm25->score($pid, $matchedTags);
            $score   = Scorer::calculateFinalScore($pid, $meta, $bm25Raw, $prefs);
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

        usort($results, static fn(array $a, array $b): int => $b['score'] <=> $a['score'] ?: $a['id'] <=> $b['id']);
        $finalList = array_slice($results, 0, $topK);

        $this->lruCache[$cacheKey] = $finalList;
        if (count($this->lruCache) > $this->cacheCapacity)
            array_shift($this->lruCache);

        return ['results' => $finalList, 'status' => 'CALCULÉ'];
    }
}
