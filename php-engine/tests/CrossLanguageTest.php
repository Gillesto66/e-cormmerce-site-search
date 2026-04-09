<?php
declare(strict_types=1);
namespace TagSearch\Tests;

use PHPUnit\Framework\TestCase;
use TagSearch\{SearchEngine, SearchPreferences, ProductType};

/**
 * Tests cross-langage PHP — miroir de test_cross_language.py et cross_language.test.ts
 * Tolérance : abs(score_php - score_py) < 1e-9
 */
final class CrossLanguageTest extends TestCase {
    private static SearchEngine $engine;
    private const CATALOG = __DIR__ . '/../../shared-assets/catalog.json';
    private const TOLERANCE = 1e-9;

    public static function setUpBeforeClass(): void {
        self::$engine = new SearchEngine(cacheSize: 50);
        self::$engine->loadCatalog(self::CATALOG);
    }

    // ── TC01 ─────────────────────────────────────────────────────────────────

    public function testCuisinePhysicalBeatsDigital(): void {
        $r = self::$engine->search('cuisine', fuzzy: false);
        $ids = array_column($r['results'], 'id');
        $this->assertContains(4, $ids);
        $this->assertContains(5, $ids);
        $scoreRobot = $this->scoreById($r['results'], 4);
        $scoreEbook = $this->scoreById($r['results'], 5);
        $this->assertGreaterThan($scoreEbook, $scoreRobot);
    }

    // ── TC02 ─────────────────────────────────────────────────────────────────

    public function testDigitalFilterInvertsOrder(): void {
        $prefs = new SearchPreferences(preferredType: ProductType::DIGITAL);
        $r     = self::$engine->search('cuisine', prefs: $prefs, fuzzy: false);
        $ids   = array_column($r['results'], 'id');
        $this->assertLessThan(array_search(4, $ids), array_search(5, $ids));
    }

    // ── TC03 ─────────────────────────────────────────────────────────────────

    public function testPriceFilterExcludesClavier(): void {
        $prefs = new SearchPreferences(maxPrice: 100.0);
        $r     = self::$engine->search('gaming', prefs: $prefs, fuzzy: false);
        $ids   = array_column($r['results'], 'id');
        $this->assertNotContains(1, $ids);
        $this->assertContains(2, $ids);
    }

    // ── TC04 ─────────────────────────────────────────────────────────────────

    public function testMinRatingExcludesSerum(): void {
        $prefs = new SearchPreferences(minRating: 4.0);
        $r     = self::$engine->search('beauté', prefs: $prefs, fuzzy: false);
        $ids   = array_column($r['results'], 'id');
        $this->assertNotContains(7, $ids);
        $this->assertContains(8, $ids);
    }

    // ── TC05 ─────────────────────────────────────────────────────────────────

    public function testFuzzyGaimingReturnsGaming(): void {
        $r      = self::$engine->search('gaiming', fuzzy: true, maxDist: 1);
        $niches = array_unique(array_column($r['results'], 'niche'));
        $this->assertContains('gaming', $niches);
    }

    // ── TYPE_MISMATCH ratio ───────────────────────────────────────────────────

    public function testTypeMismatchFactorIsPointOne(): void {
        $base    = self::$engine->search('cuisine', fuzzy: false);
        $prefs   = new SearchPreferences(preferredType: ProductType::DIGITAL);
        $digital = self::$engine->search('cuisine', prefs: $prefs, fuzzy: false);
        $scoreBase    = $this->scoreById($base['results'], 4);
        $scoreDigital = $this->scoreById($digital['results'], 4);
        $ratio = $scoreDigital / $scoreBase;
        $this->assertEqualsWithDelta(0.1, $ratio, 1e-3);
    }

    // ── Robustesse ────────────────────────────────────────────────────────────

    public function testEmptyQueryThrows(): void {
        $this->expectException(\InvalidArgumentException::class);
        self::$engine->search('');
    }

    public function testUnknownQueryReturnsMiss(): void {
        $r = self::$engine->search('xyzqwerty123', fuzzy: false);
        $this->assertEmpty($r['results']);
        $this->assertSame('MISS', $r['status']);
    }

    public function testCacheHitOnRepeat(): void {
        self::$engine->search('yoga', fuzzy: false);
        $r = self::$engine->search('yoga', fuzzy: false);
        $this->assertSame('CACHÉ', $r['status']);
    }

    public function testLoadNonexistentFileThrows(): void {
        $this->expectException(\RuntimeException::class);
        (new SearchEngine())->loadCatalog('/nonexistent/catalog.json');
    }

    // ── Helper ────────────────────────────────────────────────────────────────

    private function scoreById(array $results, int $id): float {
        foreach ($results as $r) {
            if ($r['id'] === $id) return (float) $r['score'];
        }
        $this->fail("Produit id={$id} absent des résultats.");
    }
}
