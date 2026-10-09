<?php
declare(strict_types=1);
namespace TagSearch\Tests;

use PHPUnit\Framework\TestCase;
use TagSearch\{BM25Index, CompressedPostingsList, DAWG, ProductMeta, ProductType, SearchEngine, Unicode, VarInt};

/** Indexation en lot, cohérence de l'index, structures (audit C1, C3, C8, C10). */
final class IndexingTest extends TestCase
{
    /** @param string[] $tags */
    private static function meta(array $tags, string $name = 'P'): ProductMeta
    {
        return new ProductMeta($name, ProductType::PHYSICAL, 'n', 10.0, null, 4.0, 10, $tags);
    }

    /** @return string[] */
    private static function vocab(int $n, int $seed): array
    {
        mt_srand($seed);
        $syl = ['ba','be','bi','bo','ca','co','da','de','fa','ga','la','le','ma','mi','na','pa','ra','re','sa','ta','va'];
        $suf = ['', '', 'ier', 'ique', 'eur', 'age', 'tion', 'able'];
        $set = [];
        while (count($set) < $n) {
            $w = '';
            for ($i = 0, $k = mt_rand(1, 3); $i < $k; $i++) { $w .= $syl[mt_rand(0, 20)]; }
            $set[$w . $suf[mt_rand(0, 7)]] = true;
        }
        return array_map('strval', array_keys($set));
    }

    /** @return array<int, array{0:int, 1:ProductMeta}> */
    private static function items(int $n, array $words): array
    {
        $out = [];
        for ($i = 1; $i <= $n; $i++) {
            $tags = [];
            for ($k = 0; $k < 5; $k++) { $tags[] = $words[mt_rand(0, count($words) - 1)]; }
            $out[] = [$i, self::meta($tags)];
        }
        return $out;
    }

    // ── C1 ────────────────────────────────────────────────────────────────────

    public function testIndexingIsLazyAndCommitsOnce(): void
    {
        $words = self::vocab(100, 1);
        $eng = new SearchEngine();
        foreach (self::items(100, $words) as [$id, $m]) { $eng->addProduct($id, $m); }
        $this->assertTrue($eng->isDirty());
        $eng->search('a', null, false);
        $this->assertFalse($eng->isDirty());
    }

    public function testIndexingTimeIsNotQuadratic(): void
    {
        $best = static function (int $n): float {
            $b = INF;
            for ($k = 0; $k < 3; $k++) {
                $words = self::vocab(400, 9);
                $it = self::items($n, $words);
                $t0 = hrtime(true);
                (new SearchEngine())->addProducts($it);
                $b = min($b, (hrtime(true) - $t0) / 1e6);
            }
            return $b;
        };
        $this->assertLessThan(3.0, $best(2000) / $best(1000), 'indexation super-linéaire');
    }

    public function testLoadCatalogIsAtomic(): void
    {
        $file = tempnam(sys_get_temp_dir(), 'ts');
        $good = ['id' => 1, 'name' => 'a', 'type' => 'PHYSICAL', 'niche' => 'x', 'price' => 1,
                 'avg_rating' => 4, 'review_count' => 1, 'tags' => ['a']];
        file_put_contents($file, json_encode(['products' => [$good, [...$good, 'id' => 2, 'avg_rating' => 9]]]));
        $eng = new SearchEngine();
        try {
            $eng->loadCatalog($file);
            $this->fail('exception attendue');
        } catch (\InvalidArgumentException $e) {
            $this->assertStringContainsString('id=2', $e->getMessage());
        } finally { unlink($file); }
        $this->assertSame('MISS', $eng->search('a', null, false)['status']);
    }

    public function testLoadCatalogReportsMissingFieldInsteadOfWarning(): void
    {
        $file = tempnam(sys_get_temp_dir(), 'ts');
        file_put_contents($file, json_encode(['products' => [['id' => 5, 'name' => 'a']]]));
        $this->expectException(\InvalidArgumentException::class);
        $this->expectExceptionMessage('champ manquant');
        try { (new SearchEngine())->loadCatalog($file); } finally { unlink($file); }
    }

    // ── Cohérence de l'index ──────────────────────────────────────────────────

    public function testReplaceProductUpdatesPostingsAndBm25(): void
    {
        $eng = new SearchEngine();
        $eng->addProduct(1, self::meta(['alpha', 'beta']));
        $eng->addProduct(2, self::meta(['beta']));
        $eng->addProduct(1, self::meta(['gamma']));
        $this->assertSame([], $eng->search('alpha', null, false)['results']);
        $this->assertSame([1], array_column($eng->search('gamma', null, false)['results'], 'id'));
        $this->assertSame([2], array_column($eng->search('beta', null, false)['results'], 'id'));
    }

    public function testRemoveProductCleansVocabulary(): void
    {
        $eng = new SearchEngine();
        $eng->addProduct(1, self::meta(['unique', 'commun']));
        $eng->addProduct(2, self::meta(['commun']));
        $this->assertTrue($eng->removeProduct(1));
        $this->assertFalse($eng->removeProduct(1));
        $this->assertSame([], $eng->search('unique', null, false)['results']);
    }

    public function testBm25RejectsDoubleIndexAndTracksAvgdl(): void
    {
        $idx = new BM25Index();
        $idx->index(1, ['a', 'b']);
        $this->expectException(\LogicException::class);
        try { $idx->index(1, ['a']); } finally {
            $idx->index(2, ['a']);
            $idx->remove(1, ['a', 'b']);
            $this->assertSame(1, $idx->docCount());
            $this->assertSame(0, $idx->docFreq('b'));
        }
    }

    public function testCacheKeyContainsFuzzyMaxDistTopK(): void
    {
        $eng = new SearchEngine();
        $eng->addProducts([[1, self::meta(['gaming'])], [2, self::meta(['gamin'])], [3, self::meta(['gaminx'])]]);
        $this->assertCount(1, $eng->search('gaming', null, false)['results']);
        $this->assertCount(3, $eng->search('gaming', null, true, 1)['results']);
        $this->assertSame('CACHÉ', $eng->search('gaming', null, true, 1)['status']);
        $this->assertCount(1, $eng->search('gaming', null, true, 1, 1)['results']);
    }

    public function testTiesBrokenByIdAndTopKValidated(): void
    {
        $eng = new SearchEngine();
        foreach ([9, 3, 7, 1] as $id) { $eng->addProduct($id, self::meta(['twin'])); }
        $this->assertSame([1, 3, 7, 9], array_column($eng->search('twin', null, false)['results'], 'id'));
        $this->expectException(\InvalidArgumentException::class);
        $eng->search('twin', null, false, 1, 0);
    }

    public function testNumericTagsSurviveArrayKeyCasting(): void
    {
        $eng = new SearchEngine();
        $eng->addProducts([[1, self::meta(['2024', '007'])], [2, self::meta(['2025'])]]);
        $this->assertSame([1], array_column($eng->search('2024', null, false)['results'], 'id'));
        $ids = array_column($eng->search('202', null, false)['results'], 'id');
        sort($ids);
        $this->assertSame([1, 2], $ids);
        $this->assertSame([1], array_column($eng->search('007', null, false)['results'], 'id'));
    }

    // ── Unicode (parité avec Python) ──────────────────────────────────────────

    public function testLowercaseAndLevenshteinUseCodePoints(): void
    {
        $this->assertSame('éclair', Unicode::lower('ÉCLAIR'));
        $dawg = DAWG::build(['pâtisserie', 'patisserie', 'sushi🍣', '寿司', '🍣']);
        // « patisserie » est à distance 1 de « pâtisserie » (et non 2 comme levenshtein() sur octets)
        $this->assertSame(['patisserie', 'pâtisserie'], $dawg->fuzzySearch('patisserie', 1));
        $this->assertSame(['🍣'], $dawg->fuzzySearch('🍣', 0));
        $this->assertSame(['sushi🍣'], $dawg->autocomplete('sushi'));
    }

    // ── Structures ────────────────────────────────────────────────────────────

    public function testDawgReallySharesSuffixes(): void
    {
        $words = self::vocab(1500, 7);
        $trie = [''=>true];
        foreach ($words as $w) {
            $cps = Unicode::chars($w);
            for ($i = 1; $i <= count($cps); $i++) { $trie[implode('', array_slice($cps, 0, $i))] = true; }
        }
        $this->assertLessThan(0.5 * count($trie), DAWG::build($words)->nodeCount());
    }

    public function testFuzzyEqualsBruteForceLevenshtein(): void
    {
        $lev = static function (array $a, array $b): int {
            $prev = range(0, count($b));
            for ($i = 1; $i <= count($a); $i++) {
                $cur = [$i];
                for ($j = 1; $j <= count($b); $j++) {
                    $cur[] = min($cur[$j-1] + 1, $prev[$j] + 1, $prev[$j-1] + ($a[$i-1] === $b[$j-1] ? 0 : 1));
                }
                $prev = $cur;
            }
            return $prev[count($b)];
        };
        $words = self::vocab(200, 5);
        $dawg  = DAWG::build($words);
        foreach (['ba', 'bat', 'cola', 'ma'] as $q) {
            foreach ([0, 1, 2] as $d) {
                $exp = [];
                foreach ($words as $w) {
                    $dist = $lev(Unicode::chars($q), Unicode::chars($w));
                    if ($dist <= $d) { $exp[] = [$dist, $w]; }
                }
                usort($exp, fn($a, $b) => $a[0] <=> $b[0] ?: Unicode::compare($a[1], $b[1]));
                $this->assertSame(array_column($exp, 1), $dawg->fuzzySearch($q, $d), "q={$q} d={$d}");
            }
        }
    }

    public function testVarIntRoundTripAndErrors(): void
    {
        foreach ([0, 1, 127, 128, 16383, 16384, 2 ** 31, 2 ** 40 + 5, PHP_INT_MAX >> 8] as $v) {
            $this->assertSame($v, VarInt::decode(VarInt::encode($v))[0]);
        }
        $this->expectException(\UnexpectedValueException::class);
        VarInt::decode("\x80");
    }

    public function testPostingsAreCompressedAndRemovable(): void
    {
        mt_srand(3);
        $ids = [];
        while (count($ids) < 500) { $ids[mt_rand(1, 100000)] = true; }
        $ids = array_keys($ids);
        $pl = new CompressedPostingsList();
        foreach ($ids as $i) { $pl->add($i); }
        $pl->flush();
        sort($ids);
        $this->assertSame($ids, $pl->decompress());
        $this->assertLessThan(500 * 3, $pl->memoryBytes());
        $this->assertTrue($pl->remove($ids[0]));
        $this->assertSame(499, $pl->size());
    }

    public function testCorruptedPostingsPropagate(): void
    {
        $eng = new SearchEngine();
        $eng->addProduct(1, self::meta(['gaming']));
        $eng->commit();
        $ref = new \ReflectionProperty($eng, 'invertedIndex');
        $ref->getValue($eng)['gaming']->setCompressedForTest("\x80");
        $this->expectException(\UnexpectedValueException::class);
        $eng->search('gaming', null, false);
    }
}
