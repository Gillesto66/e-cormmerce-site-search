"""Catalogue synthétique déterministe, partagé par les benchmarks et le générateur de référence."""
from __future__ import annotations
import random

_SYLL = ["ba", "be", "bi", "bo", "ca", "co", "cu", "da", "de", "di", "do", "fa", "fi", "ga", "go",
         "la", "le", "li", "lo", "ma", "me", "mi", "mo", "na", "ne", "ni", "no", "pa", "pe", "pi",
         "po", "ra", "re", "ri", "ro", "sa", "se", "si", "so", "ta", "te", "ti", "to", "va", "ve"]
_SUFFIX = ["", "", "", "ier", "ique", "eur", "age", "tion", "ement", "able", "iste", "erie"]
_NICHES = ["gaming", "cuisine", "audio", "beauté", "sport", "maison", "jardin", "mode"]
_LOCATIONS = ["France", "Belgique", "Suisse", "Canada", None, None]


def make_vocab(n_words: int, rng: random.Random) -> list[str]:
    words: set[str] = set()
    while len(words) < n_words:
        stem = "".join(rng.choice(_SYLL) for _ in range(rng.randint(1, 3)))
        words.add(stem + rng.choice(_SUFFIX))
    return sorted(words)


def make_catalog(n_products: int, vocab_size: int = 1500, tags_per_product: int = 5, seed: int = 7) -> dict:
    rng = random.Random(seed)
    vocab = make_vocab(vocab_size, rng)
    products = []
    for pid in range(1, n_products + 1):
        tags = rng.sample(vocab, tags_per_product)
        products.append({
            "id": pid, "name": f"Produit {pid}",
            "type": rng.choice(["PHYSICAL", "DIGITAL"]),
            "niche": rng.choice(_NICHES),
            "price": round(rng.uniform(5, 500), 2),
            "location": rng.choice(_LOCATIONS),
            "avg_rating": round(rng.uniform(1.0, 5.0), 1),
            "review_count": rng.randint(0, 800),
            "tags": tags,
        })
    return {"products": products, "vocab": vocab}


if __name__ == "__main__":
    # python benchmarks/synth.py OUT_DIR 100 200 400 ... : écrit catalog_<n>.json pour les benchmarks JS/PHP
    import json, sys
    from pathlib import Path
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for n in map(int, sys.argv[2:]):
        cat = make_catalog(n)
        (out / f"catalog_{n}.json").write_text(json.dumps(cat, ensure_ascii=False), encoding="utf-8")
