<?php
// Benchmark du moteur PHP (constats C3/C4).
//   php benchmarks/run.php <dossier_catalogues> 100 200 400 ...
declare(strict_types=1);
require __DIR__ . '/../php-engine/vendor/autoload.php';

use TagSearch\{SearchEngine, CompressedPostingsList};

$dir = $argv[1];
$sizes = array_map('intval', array_slice($argv, 2));

function lat(SearchEngine $eng, array $vocab, bool $fuzzy, int $n = 300): array {
    mt_srand(11); $xs = [];
    for ($i = 0; $i < $n; $i++) {
        $w = $vocab[mt_rand(0, count($vocab) - 1)];
        $q = mb_substr($w, 0, mt_rand(2, 5));
        $eng->clearCache();
        $t0 = hrtime(true); $eng->search($q, null, $fuzzy, 1); $xs[] = (hrtime(true) - $t0) / 1e6;
    }
    sort($xs);
    return [$xs[intdiv(count($xs), 2)], $xs[max(0, (int) floor(count($xs) * 0.99) - 1)]];
}

printf("Machine: %s | PHP %s\n", PHP_OS, PHP_VERSION);
echo "| Produits | Indexation (ms) | Rapport | Recherche p50/p99 (ms) | Floue p50/p99 (ms) |\n|---:|---:|---:|---:|---:|\n";
$prev = null;
foreach ($sizes as $n) {
    $cat = json_decode(file_get_contents("$dir/catalog_$n.json"), true, 512, JSON_THROW_ON_ERROR);
    $file = tempnam(sys_get_temp_dir(), 'tsb'); file_put_contents($file, json_encode(['products' => $cat['products']]));
    $eng = new SearchEngine(1);
    $t0 = hrtime(true); $eng->loadCatalog($file); $t = (hrtime(true) - $t0) / 1e6; unlink($file);
    [$s50, $s99] = lat($eng, $cat['vocab'], false); [$f50, $f99] = lat($eng, $cat['vocab'], true);
    printf("| %d | %.1f | %s | %.3f / %.3f | %.3f / %.3f |\n", $n, $t, $prev ? sprintf('%.2f', $t / $prev) : '—', $s50, $s99, $f50, $f99);
    $prev = $t;
}

mt_srand(3); $ids = [];
while (count($ids) < 500) { $ids[mt_rand(1, 100000)] = true; }
$ids = array_keys($ids);
$a = memory_get_usage(); $arrays = []; for ($k = 0; $k < 200; $k++) { $arrays[] = array_map(static fn(int $x): int => $x + $k, $ids); }   // copies réelles (pas de copy-on-write)
$arrBytes = (memory_get_usage() - $a) / 200;
$pl = new CompressedPostingsList(); foreach ($ids as $i) { $pl->add($i); } $pl->flush();
printf("\nPostings (500 ids) : tableau PHP ≈ %d octets, delta+VarInt = %d octets (-%.1f %%)\n",
    $arrBytes, $pl->memoryBytes(), 100 * (1 - $pl->memoryBytes() / $arrBytes));
