<?php
declare(strict_types=1);
namespace TagSearch\Tests;

use PHPUnit\Framework\TestCase;
use TagSearch\{BM25Index, ProductMeta, ProductType, Scorer, SearchEngine, SearchPreferences};

/**
 * Suite de tests PHP — miroir de test_cross_language.py et cross_language.test.ts
 *
 * Couverture :
 *   - BM25Index : IDF, saturation TF, score nul sur tag absent
 *   - ProductMeta : validation des contraintes (rating, price, reviewCount)
 *   - Scorer::calculateFinalScore : chaque dimension isolément
 *   - SearchEngine : TC01–TC05 cross-langage + robustesse + cache
 */
final class CrossLanguageTest extends TestCase
{
    private static SearchEngine $engine;
    private const CATALOG   = __DIR__ . '/../../shared-assets/catalog.json';
    private const TOLERANCE = 1e-9;

    public static function setUpBeforeClass(): void
    {
        self::$engine = new SearchEngine(cacheSize: 50);
        self::$engine->loadCatalog(self::CATALOG);
    }

    // =========================================================================
    // SECTION 1 — BM25Index (composants isolés)
    // =========================================================================

    public function testBm25IdfFormula(): void
    {
        $N = 10; $df = 3;
        $expected = log(($N - $df + 0.5) / ($df + 0.5) + 1);
        $this->assertEqualsWithDelta(log(7.5 / 3.5 + 1), $expected, self::TOLERANCE);
    }

    public function testBm25TfSaturation(): void
    {
        $idx = new BM25Index();
        $idx->index(1, array_fill(0, 10, 'gaming'));
        $idx->index(2, ['gaming']);
        $s10 = $idx->score(1, ['gaming']);
        $s1  = $idx->score(2, ['gaming']);
        $this->assertLessThan($s1 * 10, $s10, 'BM25 doit saturer la fréquence des termes');
    }

    public function testBm25ZeroOnMissingTag(): void
    {
        $idx = new BM25Index();
        $idx->index(1, ['gaming', 'tech']);
        $this->assertSame(0.0, $idx->score(1, ['cuisine']));
    }

    public function testBm25PositiveOnMatchingTag(): void
    {
        $idx = new BM25Index();
        $idx->index(1, ['gaming', 'tech']);
        $idx->index(2, ['cuisine']);
        $this->assertGreaterThan(0.0, $idx->score(1, ['gaming']));
    }

    public function testBm25ZeroOnEmptyIndex(): void
    {
        $idx = new BM25Index();
        $this->assertSame(0.0, $idx->score(99, ['gaming']));
    }

    // =========================================================================
    // SECTION 2 — ProductMeta (validation des contraintes)
    // =========================================================================

    private function makeMeta(array $overrides = []): ProductMeta
    {
        return new ProductMeta(
            name        : $overrides['name']        ?? 'Produit Test',
            productType : $overrides['productType'] ?? ProductType::PHYSICAL,
            niche       : $overrides['niche']       ?? 'gaming',
            price       : $overrides['price']       ?? 50.0,
            // array_key_exists car null est une valeur valide (produit digital)
            location    : array_key_exists('location', $overrides) ? $overrides['location'] : 'France',
            avgRating   : $overrides['avgRating']   ?? 4.5,
            reviewCount : $overrides['reviewCount'] ?? 100,
            tags        : $overrides['tags']        ?? ['gaming'],
        );
    }

    public function testProductMetaInvalidRatingThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/avgRating/');
        $this->makeMeta(['avgRating' => 6.0]);
    }

    public function testProductMetaNegativeRatingThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        $this->makeMeta(['avgRating' => -0.1]);
    }

    public function testProductMetaNegativePriceThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/price/');
        $this->makeMeta(['price' => -1.0]);
    }

    public function testProductMetaNegativeReviewCountThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessageMatches('/reviewCount/');
        $this->makeMeta(['reviewCount' => -1]);
    }

    public function testProductTypeFromStringCaseInsensitive(): void
    {
        $this->assertSame(ProductType::PHYSICAL, ProductType::fromString('physical'));
        $this->assertSame(ProductType::DIGITAL,  ProductType::fromString('DIGITAL'));
    }

    public function testProductTypeFromStringInvalidThrows(): void
    {
        $this->expectException(\ValueError::class);
        ProductType::fromString('UNKNOWN');
    }

    // =========================================================================
    // SECTION 3 — Scorer::calculateFinalScore (dimensions isolées)
    // =========================================================================

    public function testScorerExcludesOnMaxPrice(): void
    {
        $prefs = new SearchPreferences(maxPrice: 100.0);
        $this->assertNull(Scorer::calculateFinalScore(1, $this->makeMeta(['price' => 150.0]), 1.0, $prefs));
    }

    public function testScorerExcludesOnMinPrice(): void
    {
        $prefs = new SearchPreferences(minPrice: 20.0);
        $this->assertNull(Scorer::calculateFinalScore(1, $this->makeMeta(['price' => 10.0]), 1.0, $prefs));
    }

    public function testScorerExcludesOnMinRating(): void
    {
        $prefs = new SearchPreferences(minRating: 4.0);
        $this->assertNull(Scorer::calculateFinalScore(1, $this->makeMeta(['avgRating' => 2.5]), 1.0, $prefs));
    }

    public function testScorerTypeMismatchAppliesFactor(): void
    {
        $meta     = $this->makeMeta(['productType' => ProductType::PHYSICAL]);
        $scoreOk  = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(preferredType: ProductType::PHYSICAL));
        $scoreBad = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(preferredType: ProductType::DIGITAL));
        $this->assertNotNull($scoreOk);
        $this->assertNotNull($scoreBad);
        $this->assertEqualsWithDelta(0.1, $scoreBad / $scoreOk, 1e-3);
    }

    public function testScorerNicheBoostApplied(): void
    {
        $meta       = $this->makeMeta(['niche' => 'gaming']);
        $scoreBoost = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(preferredNiche: 'gaming'));
        $scoreBase  = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences());
        $this->assertNotNull($scoreBoost);
        $this->assertNotNull($scoreBase);
        $this->assertEqualsWithDelta(1.2, $scoreBoost / $scoreBase, 1e-3);
    }

    public function testScorerProximityBonusApplied(): void
    {
        $meta      = $this->makeMeta(['location' => 'France']);
        $scoreProx = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(userLocation: 'France'));
        $scoreBase = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences());
        $this->assertNotNull($scoreProx);
        $this->assertNotNull($scoreBase);
        $this->assertEqualsWithDelta(1.15, $scoreProx / $scoreBase, 1e-3);
    }

    public function testScorerDigitalIgnoresProximity(): void
    {
        // location=null (digital) → proximity toujours 1.0, même avec userLocation
        // On compare le même produit avec et sans userLocation
        $meta       = $this->makeMeta(['location' => null]);
        $scoreProx  = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(userLocation: 'France'));
        $scoreBase  = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences());
        $this->assertNotNull($scoreProx);
        $this->assertNotNull($scoreBase);
        $this->assertEqualsWithDelta($scoreBase, $scoreProx, 1e-9);
    }

    public function testScorerPriceBudgetBoostApplied(): void
    {
        // prix = 30€, budget max = 100€ → ratio 0.3 ≤ 0.5 → boost +10%
        $meta       = $this->makeMeta(['price' => 30.0]);
        $scoreBoost = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences(maxPrice: 100.0));
        $scoreBase  = Scorer::calculateFinalScore(1, $meta, 5.0, new SearchPreferences());
        $this->assertNotNull($scoreBoost);
        $this->assertNotNull($scoreBase);
        $this->assertEqualsWithDelta(1.1, $scoreBoost / $scoreBase, 1e-3);
    }

    public function testScorerBayesianRatingSmoothing(): void
    {
        // Produit avec peu d'avis → tiré vers la moyenne marché (3.5)
        $metaFew  = $this->makeMeta(['avgRating' => 2.8, 'reviewCount' => 12]);
        $metaMany = $this->makeMeta(['avgRating' => 4.5, 'reviewCount' => 276]);
        $scoreFew  = Scorer::calculateFinalScore(1, $metaFew,  5.0, new SearchPreferences());
        $scoreMany = Scorer::calculateFinalScore(1, $metaMany, 5.0, new SearchPreferences());
        $this->assertNotNull($scoreFew);
        $this->assertNotNull($scoreMany);
        $this->assertGreaterThan($scoreFew, $scoreMany);
    }

    public function testScorerBm25FloorApplied(): void
    {
        // bm25_raw=0 → plancher BM25_FLOOR=0.05, score non nul
        $score = Scorer::calculateFinalScore(1, $this->makeMeta(), 0.0, new SearchPreferences());
        $this->assertNotNull($score);
        $this->assertGreaterThan(0.0, $score);
    }

    // =========================================================================
    // SECTION 4 — SearchEngine (tests cross-langage TC01–TC05)
    // =========================================================================

    public function testTC01CuisinePhysicalBeatsDigital(): void
    {
        $r   = self::$engine->search('cuisine', fuzzy: false);
        $ids = array_column($r['results'], 'id');
        $this->assertContains(4, $ids, 'Robot pâtissier doit être présent');
        $this->assertContains(5, $ids, 'E-book doit être présent');
        $this->assertGreaterThan(
            $this->scoreById($r['results'], 5),
            $this->scoreById($r['results'], 4),
            'Robot (Physical, plus d\'avis) doit scorer plus haut que E-book'
        );
    }

    public function testTC02DigitalFilterInvertsOrder(): void
    {
        $prefs   = new SearchPreferences(preferredType: ProductType::DIGITAL);
        $r       = self::$engine->search('cuisine', prefs: $prefs, fuzzy: false);
        $results = $r['results'];
        // Trouver les positions explicitement (évite le bug de array_search avec false)
        $posEbook = null; $posRobot = null;
        foreach ($results as $i => $item) {
            if ($item['id'] === 5) $posEbook = $i;
            if ($item['id'] === 4) $posRobot = $i;
        }
        $this->assertNotNull($posEbook, 'E-book doit être dans les résultats');
        $this->assertNotNull($posRobot, 'Robot doit être dans les résultats');
        $this->assertLessThan($posRobot, $posEbook, 'E-book doit être avant Robot avec filtre DIGITAL');
    }

    public function testTC03PriceFilterExcludesClavier(): void
    {
        $prefs = new SearchPreferences(maxPrice: 100.0);
        $r     = self::$engine->search('gaming', prefs: $prefs, fuzzy: false);
        $ids   = array_column($r['results'], 'id');
        $this->assertNotContains(1, $ids, 'Clavier (129.99€) doit être exclu');
        $this->assertContains(2, $ids, 'Souris (79.99€) doit être présente');
    }

    public function testTC04MinRatingExcludesSerum(): void
    {
        $prefs = new SearchPreferences(minRating: 4.0);
        $r     = self::$engine->search('beauté', prefs: $prefs, fuzzy: false);
        $ids   = array_column($r['results'], 'id');
        $this->assertNotContains(7, $ids, 'Sérum (2.8★) doit être exclu');
        $this->assertContains(8, $ids, 'Palette (4.5★) doit être présente');
    }

    public function testTC05FuzzyGaimingReturnsGaming(): void
    {
        $r      = self::$engine->search('gaiming', fuzzy: true, maxDist: 1);
        $niches = array_unique(array_column($r['results'], 'niche'));
        $this->assertContains('gaming', $niches, 'Fuzzy doit trouver les produits gaming');
    }

    public function testTypeMismatchRatioIsPointOne(): void
    {
        $base    = self::$engine->search('cuisine', fuzzy: false);
        $prefs   = new SearchPreferences(preferredType: ProductType::DIGITAL);
        $digital = self::$engine->search('cuisine', prefs: $prefs, fuzzy: false);
        $ratio   = $this->scoreById($digital['results'], 4) / $this->scoreById($base['results'], 4);
        $this->assertEqualsWithDelta(0.1, $ratio, 1e-3);
    }

    public function testTopKLimitsResults(): void
    {
        $r = self::$engine->search('tech', fuzzy: false, topK: 1);
        $this->assertCount(1, $r['results']);
    }

    public function testMinPriceFilter(): void
    {
        // Exclut les produits < 50€ (E-book 14.99€, Tapis 29.99€, App 9.99€)
        $prefs = new SearchPreferences(minPrice: 50.0);
        $r     = self::$engine->search('digital', prefs: $prefs, fuzzy: false);
        foreach ($r['results'] as $item) {
            $this->assertGreaterThanOrEqual(50.0, $item['price']);
        }
    }

    // =========================================================================
    // SECTION 5 — Robustesse & gestion d'erreurs
    // =========================================================================

    public function testEmptyQueryThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        self::$engine->search('');
    }

    public function testWhitespaceQueryThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        self::$engine->search('   ');
    }

    public function testNegativeMaxDistThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        self::$engine->search('gaming', maxDist: -1);
    }

    public function testUnknownQueryReturnsMiss(): void
    {
        $r = self::$engine->search('xyzqwerty123', fuzzy: false);
        $this->assertEmpty($r['results']);
        $this->assertSame('MISS', $r['status']);
    }

    public function testCacheHitOnRepeat(): void
    {
        self::$engine->search('yoga', fuzzy: false);
        $r = self::$engine->search('yoga', fuzzy: false);
        $this->assertSame('CACHÉ', $r['status']);
    }

    public function testLoadNonexistentFileThrows(): void
    {
        $this->expectException(\RuntimeException::class);
        (new SearchEngine())->loadCatalog('/nonexistent/catalog.json');
    }

    public function testNegativeProductIdThrows(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        (new SearchEngine())->addProduct(-1, $this->makeMeta());
    }

    // =========================================================================
    // Helper
    // =========================================================================

    private function scoreById(array $results, int $id): float
    {
        foreach ($results as $r) {
            if ($r['id'] === $id) return (float) $r['score'];
        }
        $this->fail("Produit id={$id} absent des résultats.");
    }
}
