"""Mesure le nombre de nœuds d'un Trie et d'un DAWG sur le même vocabulaire (constat C10)."""
from __future__ import annotations
import random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "python-engine"))
sys.path.insert(0, str(ROOT))
from synth import make_vocab                 # noqa: E402
from tagsearch.structures import DAWG, Trie  # noqa: E402


def compare(words: list[str]) -> dict:
    trie = Trie()
    for w in words:
        trie.insert(w)
    dawg = DAWG.build(words)
    t, d = trie.node_count(), dawg.node_count()
    return dict(mots=len(words), noeuds_trie=t, noeuds_dawg=d, gain_pct=round(100 * (1 - d / t), 1))


if __name__ == "__main__":
    rng = random.Random(7)
    print("Vocabulaire synthétique à suffixes répétés (-ier, -ique, -tion, ...) :")
    for n in (500, 1500, 5000):
        print(" ", compare(make_vocab(n, rng)))
    print("Mots aléatoires sans structure (pire cas pour le partage) :")
    alpha = "abcdefghijklmnopqrstuvwxyz"
    rnd = sorted({"".join(rng.choice(alpha) for _ in range(rng.randint(4, 9))) for _ in range(1500)})
    print(" ", compare(rnd))
