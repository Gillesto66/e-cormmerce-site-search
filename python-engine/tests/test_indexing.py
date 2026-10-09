"""Indexation en lot, cohérence de l'index et non-régression de complexité (audit C1, C8, C10)."""
import random
import sys
import time
from pathlib import Path

import pytest

from tagsearch import ProductMeta, ProductType, SearchEngine, SearchPreferences
from tagsearch.scoring import BM25Index
from tagsearch.structures import DAWG, CompressedPostingsList, Trie

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "benchmarks"))
from synth import make_catalog, make_vocab  # noqa: E402


def _meta(tags, **kw) -> ProductMeta:
    base = dict(name="P", product_type=ProductType.PHYSICAL, niche="n", price=10.0, location=None,
                avg_rating=4.0, review_count=10, tags=tags)
    base.update(kw)
    return ProductMeta(**base)


def _items(n: int, vocab_size: int = 300):
    out = []
    for p in make_catalog(n, vocab_size=vocab_size)["products"]:
        out.append((p["id"], _meta(p["tags"], name=p["name"])))
    return out


# ── C1 : l'indexation ne reconstruit plus le DAWG à chaque produit ───────────

class TestBatchIndexing:
    def test_dawg_built_once_for_a_whole_batch(self, monkeypatch):
        builds = []
        original = DAWG.build.__func__
        monkeypatch.setattr(DAWG, "build", classmethod(lambda cls, tags: (builds.append(1), original(cls, tags))[1]))
        eng = SearchEngine()
        eng.add_products(_items(300))
        assert len(builds) == 1, "add_products doit reconstruire le DAWG une seule fois"

    def test_add_product_is_lazy_then_search_commits_once(self, monkeypatch):
        builds = []
        original = DAWG.build.__func__
        monkeypatch.setattr(DAWG, "build", classmethod(lambda cls, tags: (builds.append(1), original(cls, tags))[1]))
        eng = SearchEngine()
        for pid, meta in _items(100):
            eng.add_product(pid, meta)
        assert builds == [] and eng.dirty
        eng.search("a", fuzzy=False)
        eng.search("b", fuzzy=False)
        assert len(builds) == 1 and not eng.dirty

    def test_indexing_time_is_not_quadratic(self):
        def best(n):
            times = []
            for _ in range(3):
                items = _items(n)
                t0 = time.perf_counter()
                SearchEngine().add_products(items)
                times.append(time.perf_counter() - t0)
            return min(times)

        t_n, t_2n = best(500), best(1000)
        assert t_2n / t_n < 3.0, f"indexation super-linéaire : x{t_2n / t_n:.2f} pour 2N produits"

    def test_load_catalog_is_atomic(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"products":[{"id":1,"name":"a","type":"PHYSICAL","niche":"x","price":1,'
                       '"avg_rating":4,"review_count":1,"tags":["a"]},'
                       '{"id":2,"name":"b","type":"PHYSICAL","niche":"x","price":1,'
                       '"avg_rating":9,"review_count":1,"tags":["b"]}]}', encoding="utf-8")
        eng = SearchEngine()
        with pytest.raises(ValueError, match="id=2"):
            eng.load_catalog(bad)
        assert eng.catalog == {}


# ── Cohérence de l'index : remplacement et retrait ───────────────────────────

class TestIndexConsistency:
    def test_replace_product_updates_postings_and_bm25(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["alpha", "beta"]))
        eng.add_product(2, _meta(["beta"]))
        eng.add_product(1, _meta(["gamma"]))            # remplacement
        assert eng.bm25.N == 2
        assert eng.search("alpha", fuzzy=False)[0] == []
        assert [r["id"] for r in eng.search("gamma", fuzzy=False)[0]] == [1]
        assert [r["id"] for r in eng.search("beta", fuzzy=False)[0]] == [2]
        assert eng.bm25.df.get("beta") == 1 and "alpha" not in eng.bm25.df

    def test_remove_product_cleans_vocabulary(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["unique", "commun"]))
        eng.add_product(2, _meta(["commun"]))
        assert eng.remove_product(1) is True and eng.remove_product(1) is False
        assert "unique" not in eng.inverted_index
        assert eng.search("unique", fuzzy=False)[0] == []
        assert eng.bm25.N == 1

    def test_bm25_rejects_double_index(self):
        idx = BM25Index()
        idx.index(1, ["a"])
        with pytest.raises(ValueError, match="déjà indexé"):
            idx.index(1, ["a"])

    def test_bm25_avgdl_is_maintained_incrementally(self):
        idx = BM25Index()
        idx.index(1, ["a", "b"]); idx.index(2, ["a"])
        assert idx.avgdl == 1.5
        idx.remove(1, ["a", "b"])
        assert idx.avgdl == 1.0 and idx.N == 1

    def test_postings_remove_roundtrip(self):
        pl = CompressedPostingsList()
        for i in (5, 300, 70_000):
            pl.add(i)
        pl.flush()
        assert pl.remove(300) and not pl.remove(300)
        assert pl.decompress() == [5, 70_000]


# ── Cache : la clé contient tous les paramètres qui changent le résultat ─────

class TestCacheKey:
    def test_fuzzy_max_dist_top_k_are_part_of_the_key(self):
        eng = SearchEngine()
        eng.add_products([(1, _meta(["gaming"])), (2, _meta(["gamin"])), (3, _meta(["gaminx"]))])
        exact, s1 = eng.search("gaming", fuzzy=False)
        fuzzy, s2 = eng.search("gaming", fuzzy=True, max_dist=1)
        wide, s3 = eng.search("gaming", fuzzy=True, max_dist=2)
        assert (s1, s2, s3) == ("CALCULÉ", "CALCULÉ", "CALCULÉ")
        assert len(exact) == 1 and len(fuzzy) == 3 == len(wide)
        assert eng.search("gaming", fuzzy=True, max_dist=1)[1] == "CACHÉ"
        assert len(eng.search("gaming", fuzzy=True, max_dist=1, top_k=1)[0]) == 1

    def test_cached_results_are_copies(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["gaming"]))
        first, _ = eng.search("gaming", fuzzy=False)
        first[0]["score"] = -1
        second, status = eng.search("gaming", fuzzy=False)
        assert status == "CACHÉ" and second[0]["score"] != -1


# ── C8 : les vraies erreurs ne sont plus transformées en « aucun résultat » ──

class TestErrorsAreNotSwallowed:
    def test_scoring_bug_propagates(self, monkeypatch):
        import tagsearch.engine as engine_module

        def boom(*a, **k):
            raise RuntimeError("bug de scoring")

        eng = SearchEngine()
        eng.add_product(1, _meta(["gaming"]))
        monkeypatch.setattr(engine_module, "calculate_final_score", boom)
        with pytest.raises(RuntimeError, match="bug de scoring"):
            eng.search("gaming", fuzzy=False)

    def test_corrupted_postings_propagate(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["gaming"]))
        eng.commit()
        eng.inverted_index["gaming"]._compressed = b"\x80"      # VarInt tronqué
        with pytest.raises(ValueError, match="tronquées"):
            eng.search("gaming", fuzzy=False)

    def test_top_k_validation(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["gaming"]))
        with pytest.raises(ValueError, match="top_k"):
            eng.search("gaming", top_k=0)

    def test_search_prefs_type_checked(self):
        eng = SearchEngine()
        eng.add_product(1, _meta(["gaming"]))
        with pytest.raises(TypeError):
            eng.search("gaming", prefs={"max_price": 1})        # type: ignore[arg-type]


# ── Déterminisme et structures ───────────────────────────────────────────────

class TestDeterminism:
    def test_ties_are_broken_by_id(self):
        eng = SearchEngine()
        for pid in (9, 3, 7, 1):
            eng.add_product(pid, _meta(["twin"]))
        assert [r["id"] for r in eng.search("twin", fuzzy=False)[0]] == [1, 3, 7, 9]

    def test_matched_tags_order_is_distance_then_tag(self):
        d = DAWG.build(["cafe", "cafes", "cave", "care"])
        assert d.fuzzy_search("cafe", 1) == ["cafe", "cafes", "care", "cave"]


class TestDawg:
    def test_dawg_really_shares_suffixes(self):
        words = make_vocab(1500, random.Random(7))
        trie = Trie()
        for w in words:
            trie.insert(w)
        dawg = DAWG.build(words)
        assert dawg.node_count() < 0.5 * trie.node_count(), (dawg.node_count(), trie.node_count())

    def test_dawg_language_is_exactly_the_input(self):
        words = make_vocab(400, random.Random(3))
        dawg = DAWG.build(words)
        assert all(dawg.contains(w) for w in words)
        assert not dawg.contains("zzzzzz") and not dawg.contains(words[0] + "x")
        assert sorted(dawg.autocomplete("")) == sorted(set(words))

    def test_fuzzy_matches_brute_force_levenshtein(self):
        def lev(a, b):
            prev = list(range(len(b) + 1))
            for i, ca in enumerate(a, 1):
                cur = [i]
                for j, cb in enumerate(b, 1):
                    cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
                prev = cur
            return prev[-1]

        rng = random.Random(5)
        words = make_vocab(300, rng)
        dawg = DAWG.build(words)
        for _ in range(60):
            q = rng.choice(words)[: rng.randint(2, 6)]
            for dist in (0, 1, 2):
                expected = sorted((lev(q, w), w) for w in words if lev(q, w) <= dist)
                assert dawg.fuzzy_search(q, dist) == [w for _, w in expected]
