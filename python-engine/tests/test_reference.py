"""
Rejeu du jeu de référence croisé (shared-assets/reference.json).
Le fichier est généré par ce même moteur : ce test détecte toute dérive involontaire
du scoring, du départage des ex æquo, des statuts de cache ou des erreurs.
"""
import json
from pathlib import Path

import pytest

from tagsearch import SearchEngine, SearchPreferences
from tagsearch.models import ProductType

REFERENCE = Path(__file__).parent.parent.parent / "shared-assets" / "reference.json"
DATA = json.loads(REFERENCE.read_text(encoding="utf-8"))


def _prefs(d: dict) -> SearchPreferences:
    kw = dict(d)
    if "preferred_type" in kw:
        kw["preferred_type"] = ProductType.from_str(kw["preferred_type"])
    return SearchPreferences(**kw)


def test_reference_size():
    assert len(DATA["products"]) >= 200
    assert len(DATA["cases"]) >= 100


def test_replay_reference_in_order():
    engine = SearchEngine(cache_size=200)
    engine.load_catalog(REFERENCE)
    tol = DATA["tolerance"]

    for case in DATA["cases"]:
        kwargs = dict(fuzzy=case.get("fuzzy", True), max_dist=case.get("max_dist", 1),
                      top_k=case.get("top_k", 10))
        expect = case["expect"]
        if "error" in expect:
            with pytest.raises(ValueError):
                engine.search(case["query"], _prefs(case.get("prefs", {})), **kwargs)
            continue

        results, status = engine.search(case["query"], _prefs(case.get("prefs", {})), **kwargs)
        where = f"{case['id']} {case['query']!r}"
        assert status == expect["status"], where
        assert [r["id"] for r in results] == [r["id"] for r in expect["results"]], where
        for got, ref in zip(results, expect["results"]):
            assert abs(got["score"] - ref["score"]) <= tol, where
            for field in ("name", "type", "niche", "price", "rating", "reviews"):
                assert got[field] == ref[field], f"{where} champ {field}"
