"""
Synchronise php-engine/ vers le dépôt Packagist (constat C6) : UNE source de vérité.

Le paquet `tagsearch/php-engine` est servi par un dépôt distinct (php-e-cormmerce-search).
Ce script en fait un miroir exact de php-engine/ (src, tests + fixtures, composer.json,
composer.lock, phpunit.xml, README, LICENSE). Ne jamais éditer le code PHP dans le dépôt miroir.

    python scripts/sync_php_repo.py ../php-e-cormmerce-search           # copie
    python scripts/sync_php_repo.py ../php-e-cormmerce-search --check   # code 1 si dérive
"""
from __future__ import annotations
import argparse, filecmp, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "php-engine"
DIRS = ["src", "tests"]
FILES = ["composer.json", "composer.lock", "phpunit.xml", "README.md", "LICENSE"]
IGNORE = shutil.ignore_patterns(".phpunit.result.cache", ".phpunit.cache", "__pycache__")


def files_under(base: Path) -> set[Path]:
    return {p.relative_to(base) for p in base.rglob("*") if p.is_file() and ".phpunit" not in p.name}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    dst_root = a.target.resolve()
    if not (dst_root / ".git").exists():
        print(f"{dst_root} n'est pas un dépôt git")
        return 2

    drift: list[str] = []
    for d in DIRS:
        s, t = SRC / d, dst_root / d
        want = files_under(s)
        have = files_under(t) if t.exists() else set()
        drift += [f"{d}/{p.as_posix()} (obsolète)" for p in sorted(have - want)]
        drift += [f"{d}/{p.as_posix()}" for p in sorted(want) if p not in have or not filecmp.cmp(s / p, t / p, shallow=False)]
        if not a.check:
            if t.exists():
                shutil.rmtree(t)
            shutil.copytree(s, t, ignore=IGNORE)
    for f in FILES:
        s, t = SRC / f, dst_root / f
        if not t.exists() or not filecmp.cmp(s, t, shallow=False):
            drift.append(f)
            if not a.check:
                shutil.copyfile(s, t)

    if a.check:
        if drift:
            print("dépôt PHP en dérive :", *drift, sep="\n  ")
            return 1
        print("dépôt PHP identique à php-engine/")
        return 0
    print(f"{len(drift)} fichier(s) synchronisé(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
