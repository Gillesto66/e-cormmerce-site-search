<?php
declare(strict_types=1);
namespace TagSearch\Tests;

use PHPUnit\Framework\TestCase;
use TagSearch\{ProductType, SearchEngine, SearchPreferences, Unicode};

/**
 * Rejeu du jeu de référence croisé (tests/fixtures/reference.json), généré par le moteur Python.
 * Mêmes statuts, mêmes ids dans le même ordre, mêmes scores, mêmes champs, mêmes erreurs
 * que Python — y compris accents, emoji/CJK, tags numériques, ex æquo et cache.
 */
final class ReferenceTest extends TestCase
{
    private const FIXTURE = __DIR__ . '/fixtures/reference.json';

    /** @return array<string, mixed> */
    private static function ref(): array
    {
        return json_decode((string) file_get_contents(self::FIXTURE), true, 512, JSON_THROW_ON_ERROR);
    }

    /** @param array<string, mixed> $p */
    private static function prefs(array $p): SearchPreferences
    {
        return new SearchPreferences(
            preferredType : isset($p['preferred_type']) ? ProductType::fromString($p['preferred_type']) : null,
            preferredNiche: $p['preferred_niche'] ?? null,
            maxPrice      : isset($p['max_price']) ? (float) $p['max_price'] : null,
            minPrice      : isset($p['min_price']) ? (float) $p['min_price'] : null,
            userLocation  : $p['user_location'] ?? null,
            minRating     : (float) ($p['min_rating'] ?? 0.0),
        );
    }

    public function testFixtureIsLargeEnough(): void
    {
        $ref = self::ref();
        $this->assertGreaterThanOrEqual(200, count($ref['products']));
        $this->assertGreaterThanOrEqual(100, count($ref['cases']));
    }

    public function testRound4MatchesPythonOnSevenThousandValues(): void
    {
        $bad = [];
        foreach (self::ref()['rounding'] as [$x, $expected]) {
            if (Unicode::round4((float) $x) !== (float) $expected) {
                $bad[] = sprintf('%.17g -> %s (attendu %s)', $x, Unicode::round4((float) $x), $expected);
            }
        }
        $this->assertSame([], array_slice($bad, 0, 10), count($bad) . ' arrondis divergents');
    }

    public function testReplaysEveryCaseInOrderLikePython(): void
    {
        $ref    = self::ref();
        $engine = new SearchEngine(cacheSize: 200);
        $engine->loadCatalog(self::FIXTURE);
        $failures = [];

        foreach ($ref['cases'] as $c) {
            $where = $c['id'] . ' ' . json_encode($c['query'], JSON_UNESCAPED_UNICODE);
            $args  = [
                self::prefs($c['prefs'] ?? []),
                $c['fuzzy'] ?? true,
                $c['max_dist'] ?? 1,
                $c['top_k'] ?? 10,
            ];
            if (isset($c['expect']['error'])) {
                try {
                    $engine->search($c['query'], ...$args);
                    $failures[] = "{$where}: erreur attendue";
                } catch (\InvalidArgumentException) {
                    // attendu
                }
                continue;
            }
            $out = $engine->search($c['query'], ...$args);
            if ($out['status'] !== $c['expect']['status']) {
                $failures[] = "{$where}: statut {$out['status']} != {$c['expect']['status']}";
            }
            $got = implode(',', array_column($out['results'], 'id'));
            $exp = implode(',', array_column($c['expect']['results'], 'id'));
            if ($got !== $exp) {
                $failures[] = "{$where}: ids [{$got}] != [{$exp}]";
                continue;
            }
            foreach ($out['results'] as $i => $r) {
                $e = $c['expect']['results'][$i];
                if (abs($r['score'] - $e['score']) > $ref['tolerance']) {
                    $failures[] = "{$where}: score {$r['score']} != {$e['score']} (id {$r['id']})";
                }
                foreach (['name', 'type', 'niche', 'rating', 'reviews'] as $f) {
                    if ($r[$f] != $e[$f]) {
                        $failures[] = "{$where}: champ {$f} {$r[$f]} != {$e[$f]}";
                    }
                }
                if (abs($r['price'] - $e['price']) > 1e-12) {
                    $failures[] = "{$where}: prix {$r['price']} != {$e['price']}";
                }
            }
        }
        $this->assertSame([], array_slice($failures, 0, 15), count($failures) . ' divergences');
    }
}
