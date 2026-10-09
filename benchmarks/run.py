"""
Benchmark reproductible du moteur Python (constats C1 et C4 de l'audit).

    python benchmarks/run.py --sizes 100 200 400 800 --check-ratio 3.0

Mesure : temps d'indexation (load_catalog), latence de recherche et de recherche floue
(p50/p99 sur requêtes préfixées de 2 à 5 lettres, hors cache), mémoire de l'index.
Code retour 1 si le temps pour 2N produits dépasse `--check-ratio` fois celui de N
(garde-fou de complexité utilisable en CI).
"""
from __future__ import annotations
import argparse, json, platform, random, statistics, sys, time, tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "python-engine"))
sys.path.insert(0, str(ROOT))

from synth import make_catalog          # noqa: E402
from tagsearch import SearchEngine       # noqa: E402


def build(catalog: dict) -> tuple[SearchEngine, float]:
    path = ROOT / "_bench_catalog.json"
    path.write_text(json.dumps({"products": catalog["products"]}), encoding="utf-8")
    eng = SearchEngine(cache_size=1)
    t0 = time.perf_counter()
    eng.load_catalog(path)
    if hasattr(eng, "commit"):
        eng.commit()
    elapsed = time.perf_counter() - t0
    path.unlink(missing_ok=True)
    return eng, elapsed


def latencies(eng: SearchEngine, vocab: list[str], n: int, fuzzy: bool, seed: int = 11) -> tuple[float, float]:
    rng = random.Random(seed)
    queries = [rng.choice(vocab)[: rng.randint(2, 5)] for _ in range(n)]
    samples = []
    for q in queries:
        eng.cache.invalidate()                        # mesure hors cache
        t0 = time.perf_counter()
        eng.search(q, fuzzy=fuzzy, max_dist=1)
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return statistics.median(samples), samples[int(len(samples) * 0.99) - 1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[100, 200, 400, 800])
    ap.add_argument("--queries", type=int, default=300)
    ap.add_argument("--vocab", type=int, default=1500)
    ap.add_argument("--check-ratio", type=float, default=None)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    rows, prev = [], None
    for n in a.sizes:
        cat = make_catalog(n, vocab_size=a.vocab)
        tracemalloc.start()
        eng, t_index = build(cat)
        _, peak = tracemalloc.get_traced_memory()
        cur, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        s50, s99 = latencies(eng, cat["vocab"], a.queries, fuzzy=False)
        f50, f99 = latencies(eng, cat["vocab"], a.queries, fuzzy=True)
        row = dict(produits=n, index_s=round(t_index, 3), ratio=None if prev is None else round(t_index / prev, 2),
                   search_p50_ms=round(s50, 3), search_p99_ms=round(s99, 3),
                   fuzzy_p50_ms=round(f50, 3), fuzzy_p99_ms=round(f99, 3), memoire_mo=round(cur / 1e6, 2))
        rows.append(row); prev = t_index
        print(row, flush=True)

    print(f"\nMachine : {platform.platform()} | Python {platform.python_version()}")
    print("| Produits | Indexation (s) | Rapport | Recherche p50/p99 (ms) | Floue p50/p99 (ms) | Mémoire (Mo) |")
    print("|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['produits']} | {r['index_s']} | {r['ratio'] or '—'} | {r['search_p50_ms']} / {r['search_p99_ms']} "
              f"| {r['fuzzy_p50_ms']} / {r['fuzzy_p99_ms']} | {r['memoire_mo']} |")
    if a.json:
        a.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if a.check_ratio is not None:
        worst = max((r["ratio"] for r in rows if r["ratio"]), default=0)
        sizes_double = all(b == 2 * a_ for a_, b in zip(a.sizes, a.sizes[1:]))
        if sizes_double and worst > a.check_ratio:
            print(f"ÉCHEC : rapport {worst} > {a.check_ratio} (indexation super-linéaire)")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
