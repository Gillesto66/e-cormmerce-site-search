"""
Copie les fichiers partagés de shared-assets/ dans php-engine/tests/fixtures/ (constat C6).

Le paquet PHP est publié depuis un dépôt distinct : ses tests ne peuvent pas lire
../../shared-assets. Les fixtures sont donc embarquées dans le paquet ; ce script garantit
qu'elles ne dérivent pas de la source unique.

    python scripts/sync_fixtures.py          # copie
    python scripts/sync_fixtures.py --check  # code retour 1 si une copie diffère
"""
from __future__ import annotations
import argparse, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "shared-assets"
DST = ROOT / "php-engine" / "tests" / "fixtures"
FILES = ["catalog.json", "reference.json"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    check = ap.parse_args().check
    DST.mkdir(parents=True, exist_ok=True)
    stale = []
    for name in FILES:
        src, dst = SRC / name, DST / name
        same = dst.exists() and dst.read_bytes() == src.read_bytes()
        if not same:
            stale.append(name)
            if not check:
                shutil.copyfile(src, dst)
    if check and stale:
        print("fixtures PHP périmées :", ", ".join(stale), "— lancer scripts/sync_fixtures.py")
        return 1
    print("fixtures PHP à jour" if not stale else f"fixtures copiées : {', '.join(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
