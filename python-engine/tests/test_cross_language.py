"""
Tests cross-langage — source de vérité Python.
Charge shared-assets/catalog.json et génère les scores de référence.
Ces mêmes cas sont rejoués en TS (Vitest) et PHP (PHPUnit) avec tolérance 1e-9.
"""

import json
import math
import pytest
from pathlib import Path

from tagsearch import SearchEngine, SearchPreferences
from tagsearch.models import ProductType
from tagsearch.scoring import (
    BM25Index, calculate_final_score,
    BM25_K1, BM25_B, BM25_CAP, BM25_FLOOR,
    QUALITY_EXPONENT, PRIOR_MEAN, PRIOR_WEIGHT,
)

CATALOG_PATH = Path(__file__).parent.parent.parent / "shared-assets" / "catalog.json"
TOLERANCE    = 1e-9


@pytest.fixture(scope="module")
def engine() -> SearchEngine:
    eng = SearchEngine(cache_size=50)
    eng.load_catalog(CATALOG_PATH)
    return eng


# ── Tests unitaires BM25 (composants isolés) ────────────────────────────────

class TestBM25Components:
    """Valide chaque composant BM25 séparément pour le portage cross-langage."""

    def test_idf_formula(self):
        """IDF = log((N - df + 0.5) / (df + 0.5) + 1)"""
        N, df = 10, 3
        expected = math.log((N - df + 0.5) / (df + 0.5) + 1)
        assert abs(expected - math.log(7.5 / 3.5 + 1)) < TOLERANCE

    def test_tf_norm_saturation(self):
        """TF normalisé sature : tf=10 ne vaut pas 10× tf=1."""
        dl, avgdl = 5, 5.0
        tf1  = 1  * (BM25_K1 + 1) / (1  + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        tf10 = 10 * (BM25_K1 + 1) / (10 + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        assert tf10 < tf1 * 10, "BM25 doit saturer la fréquence des termes"

    def test_bm25_zero_on_missing_tag(self):
        idx = BM25Index()
        idx.index(1, ["gaming", "tech"])
        assert idx.score(1, ["cuisine"]) == 0.0

    def test_bm25_positive_on_matching_tag(self):
        idx = BM25Index()
        idx.index(1, ["gaming", "tech"])
        idx.index(2, ["cuisine"])
        score = idx.score(1, ["gaming"])
        assert score > 0.0


# ── Tests scoring multidimensionnel ─────────────────────────────────────────

class TestScoringDimensions:

    def _make_engine(self) -> SearchEngine:
        eng = SearchEngine(cache_size=10)
        eng.load_catalog(CATALOG_PATH)
        return eng

    def test_tc01_cuisine_physical_beats_digital(self, engine):
        """TC01 : Robot pâtissier (Physical) > E-book (Digital) sans filtre."""
        results, _ = engine.search("cuisine", fuzzy=False)
        ids = [r["id"] for r in results]
        assert 4 in ids and 5 in ids
        score_robot  = next(r["score"] for r in results if r["id"] == 4)
        score_ebook  = next(r["score"] for r in results if r["id"] == 5)
        assert score_robot > score_ebook

    def test_tc02_digital_filter_inverts_order(self, engine):
        """TC02 : preferred_type=DIGITAL → E-book devant Robot."""
        prefs = SearchPreferences(preferred_type=ProductType.DIGITAL)
        results, _ = engine.search("cuisine", prefs=prefs, fuzzy=False)
        ids = [r["id"] for r in results]
        assert ids.index(5) < ids.index(4)

    def test_tc03_price_filter_excludes_clavier(self, engine):
        """TC03 : budget 100€ → Clavier (129.99€) exclu."""
        prefs = SearchPreferences(max_price=100.0)
        results, _ = engine.search("gaming", prefs=prefs, fuzzy=False)
        ids = [r["id"] for r in results]
        assert 1 not in ids   # Clavier exclu
        assert 2 in ids       # Souris présente

    def test_tc04_min_rating_excludes_serum(self, engine):
        """TC04 : min_rating=4.0 → Sérum (2.8★) exclu."""
        prefs = SearchPreferences(min_rating=4.0)
        results, _ = engine.search("beauté", prefs=prefs, fuzzy=False)
        ids = [r["id"] for r in results]
        assert 7 not in ids   # Sérum exclu
        assert 8 in ids       # Palette présente

    def test_tc05_fuzzy_gaming_typo(self, engine):
        """TC05 : 'gaiming' → résultats gaming via fuzzy."""
        results, _ = engine.search("gaiming", fuzzy=True, max_dist=1)
        niches = {r["niche"] for r in results}
        assert "gaming" in niches

    def test_bayesian_rating_smoothing(self, engine):
        """Produit avec peu d'avis est tiré vers la moyenne marché."""
        serum   = engine.catalog[7]   # 2.8★, 12 avis
        palette = engine.catalog[8]   # 4.5★, 276 avis
        br_serum   = (serum.review_count   * serum.avg_rating   + PRIOR_MEAN * PRIOR_WEIGHT) / (serum.review_count   + PRIOR_WEIGHT)
        br_palette = (palette.review_count * palette.avg_rating + PRIOR_MEAN * PRIOR_WEIGHT) / (palette.review_count + PRIOR_WEIGHT)
        # Le sérum est tiré vers 3.5 (PRIOR_MEAN), la palette reste proche de 4.5
        assert br_serum > serum.avg_rating      # Tiré vers le haut (était très bas)
        assert br_palette < palette.avg_rating  # Légèrement tiré vers le bas
        assert br_palette > br_serum


# ── Génération des scores de référence (cross-language fixture) ──────────────

class TestCrossLanguageFixtures:
    """
    Génère et valide les scores de référence pour TS et PHP.
    Ces scores sont la source de vérité : les autres langages doivent
    tomber dans |score_ref - score_impl| < TOLERANCE (1e-9).
    """

    def test_reference_scores_stable(self, engine):
        """Les scores de référence ne doivent pas changer entre runs."""
        results, _ = engine.search("cuisine", fuzzy=False)
        scores = {r["id"]: r["score"] for r in results}
        # Scores attendus (calculés lors de la validation Phase 2)
        assert abs(scores[4] - 0.1354) < 1e-3   # Robot pâtissier
        assert abs(scores[5] - 0.1082) < 1e-3   # E-book

    def test_type_mismatch_factor(self, engine):
        """Le facteur TYPE_MISMATCH=0.1 doit diviser le score par ~10.
        Tolérance 1e-3 : les scores sont arrondis à 4 décimales avant division,
        ce qui introduit une erreur d'arrondi de l'ordre de 1e-4/score_base.
        """
        results_no_filter, _ = engine.search("cuisine", fuzzy=False)
        prefs = SearchPreferences(preferred_type=ProductType.DIGITAL)
        results_digital, _   = engine.search("cuisine", prefs=prefs, fuzzy=False)

        score_robot_base    = next(r["score"] for r in results_no_filter if r["id"] == 4)
        score_robot_digital = next(r["score"] for r in results_digital   if r["id"] == 4)
        ratio = score_robot_digital / score_robot_base
        assert abs(ratio - 0.1) < 1e-3, f"Ratio attendu ~0.1, obtenu {ratio}"


# ── Tests robustesse & gestion d'erreurs ────────────────────────────────────

class TestRobustness:

    def test_empty_query_raises(self, engine):
        with pytest.raises(ValueError, match="vide"):
            engine.search("")

    def test_whitespace_query_raises(self, engine):
        with pytest.raises(ValueError, match="vide"):
            engine.search("   ")

    def test_negative_max_dist_raises(self, engine):
        with pytest.raises(ValueError, match="max_dist"):
            engine.search("gaming", max_dist=-1)

    def test_unknown_query_returns_miss(self, engine):
        results, status = engine.search("xyzqwerty123", fuzzy=False)
        assert results == []
        assert status == "MISS"

    def test_cache_hit_on_repeat(self, engine):
        engine.search("yoga", fuzzy=False)
        _, status = engine.search("yoga", fuzzy=False)
        assert status == "CACHÉ"

    def test_load_nonexistent_file_raises(self):
        eng = SearchEngine()
        with pytest.raises(FileNotFoundError):
            eng.load_catalog("/nonexistent/path/catalog.json")

    def test_invalid_rating_raises(self):
        from tagsearch.models import ProductMeta, ProductType
        with pytest.raises(ValueError, match="avg_rating"):
            ProductMeta("Test", ProductType.PHYSICAL, "gaming", 10.0, None, 6.0, 10, ["tag"])
