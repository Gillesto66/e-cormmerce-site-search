"""
Génère shared-assets/reference.json : jeu de référence croisé (constat C7).

Le moteur Python est la SOURCE DE VÉRITÉ : ce script joue les requêtes sur un catalogue
synthétique déterministe et fige les résultats attendus (ids, ordre, scores, statuts).
Les suites JS (Vitest) et PHP (PHPUnit) rejouent le fichier dans l'ordre sur un moteur
neuf (l'ordre compte : il détermine les statuts CACHÉ / CALCULÉ).

    python shared-assets/generate_reference.py            # régénère le fichier
    python shared-assets/generate_reference.py --check    # échoue si le fichier est périmé

Règles de départage définies ici (identiques dans les trois langages) :
  - résultats triés par score décroissant, puis `id` croissant ;
  - tags appariés ordonnés par (distance de Levenshtein, tag) en recherche floue,
    par ordre lexicographique (points de code Unicode) en autocomplétion ;
  - distance de Levenshtein calculée sur les points de code Unicode, pas sur les octets.
"""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python-engine"))
sys.path.insert(0, str(HERE.parent / "benchmarks"))

from synth import make_vocab                                     # noqa: E402
from tagsearch import SearchEngine, SearchPreferences            # noqa: E402
from tagsearch.models import ProductType                         # noqa: E402

OUT = HERE / "reference.json"
TOLERANCE = 1e-9

ACCENTED = ["pâtisserie", "café", "été", "crème", "brûlé", "œuf", "mécanique", "électroménager",
            "beauté", "naïf", "déjà", "forêt", "garçon", "noël", "Éclair", "ÉTÉ", "Crème", "ÇA",
            "sans-fil", "e-book", "usb-c", "4k", "2024", "007", "123", "寿司", "sushi🍣", "🍣"]
BASE = ["gaming", "cuisine", "audio", "yoga", "tech", "rgb", "clavier", "souris", "casque", "robot",
        "bluetooth", "sport", "maison", "jardin", "mode", "lecture", "voyage", "photo", "musique", "cinéma"]
NICHES = ["Gaming", "cuisine", "AUDIO", "beauté", "sport", "maison", "jardin", "mode"]
LOCATIONS = ["France", "france", "Belgique", "Suisse", "Canada", None, None, None]


def build_catalog(rng: random.Random) -> list[dict]:
    vocab = ACCENTED + BASE + make_vocab(260, rng)
    products: list[dict] = []

    def one(pid: int, **over) -> dict:
        tags = [rng.choice(vocab) for _ in range(rng.randint(2, 7))]
        if rng.random() < 0.25:                       # casse variable : doit être normalisée
            tags = [t.upper() if rng.random() < 0.3 else t for t in tags]
        if rng.random() < 0.1:                        # tag répété dans un même produit (tf = 2)
            tags.append(tags[0])
        digital = rng.random() < 0.35
        p = {
            "id": pid, "name": f"Produit {pid}",
            "type": "DIGITAL" if digital else "PHYSICAL",
            "niche": rng.choice(NICHES),
            "price": round(rng.choice([rng.uniform(1, 40), rng.uniform(40, 200), rng.uniform(200, 900)]), 2),
            "location": None if digital else rng.choice(LOCATIONS),
            "avg_rating": round(rng.uniform(1.0, 5.0), 1),
            "review_count": rng.choice([0, 1, 3, 12, 45, 120, 350, 900]),
            "tags": tags,
        }
        p.update(over)
        return p

    for pid in range(1, 221):
        products.append(one(pid))
    # Jumeaux parfaits : mêmes tags/notes/prix → scores identiques, départage par id.
    twin = dict(type="PHYSICAL", niche="gaming", price=59.9, location="France", avg_rating=4.4,
                review_count=77, tags=["jumeau", "gaming", "twin-tag"])
    for pid in (301, 302, 303, 304, 305):
        products.append({"id": pid, "name": f"Jumeau {pid}", **twin})
    # Identifiants limites : 0 et un grand identifiant (VarInt sur plusieurs octets).
    products.append(one(0, name="Produit zéro", tags=["zero-id", "gaming"]))
    products.append(one(1_000_000, name="Produit géant", tags=["zero-id", "grand-id", "café"]))
    # Prix 0, note 0 et 5, aucun avis.
    products.append(one(400, name="Gratuit", price=0.0, avg_rating=0.0, review_count=0, tags=["gratuit", "gaming"]))
    products.append(one(401, name="Parfait", avg_rating=5.0, review_count=900, tags=["parfait", "gaming"]))
    return products


def build_cases(rng: random.Random, products: list[dict]) -> list[dict]:
    all_tags = sorted({t.lower() for p in products for t in p["tags"]})
    cases: list[dict] = []

    def add(query, prefs=None, fuzzy=None, max_dist=None, top_k=None):
        c: dict = {"query": query}
        if prefs: c["prefs"] = prefs
        if fuzzy is not None: c["fuzzy"] = fuzzy
        if max_dist is not None: c["max_dist"] = max_dist
        if top_k is not None: c["top_k"] = top_k
        cases.append(c)

    def typo(w: str) -> str:
        if len(w) < 3: return w
        i = rng.randrange(len(w)); kind = rng.choice("sdi")
        if kind == "s": return w[:i] + rng.choice("abcdefghij") + w[i + 1:]
        if kind == "d": return w[:i] + w[i + 1:]
        return w[:i] + rng.choice("abcdefghij") + w[i:]

    # 1. Mots exacts (autocomplétion et floue)
    for w in rng.sample(all_tags, 24):
        add(w, fuzzy=False)
        add(w)
    # 2. Préfixes
    for w in rng.sample(all_tags, 14):
        add(w[: max(2, len(w) // 2)], fuzzy=False)
    # 3. Fautes de frappe, max_dist 1 / 2 / 3 / 0
    for w in rng.sample(all_tags, 16):
        add(typo(w), max_dist=1)
    for w in rng.sample(all_tags, 6):
        add(typo(typo(w)), max_dist=2)
    for w in rng.sample(all_tags, 3):
        add(typo(w), max_dist=3)
        add(w, max_dist=0)
    # 4. Accents, casse, espaces, Unicode
    for q in ["2024", "2025", "007", "12", "patisserie", "pâtisserie", "PÂTISSERIE", "cafe", "café", "CAFÉ", "ete", "été", "ÉTÉ",
              "oeuf", "œuf", "creme", "crème", "naif", "foret", "garcon", "noel", "ca", "éclair", "eclair",
              "寿司", "sushi", "sushi🍣", "🍣", "  gaming  ", "GAMING", "Gaming"]:
        add(q); add(q, fuzzy=False)
    # 5. Aucun résultat
    for q in ["xyzqwerty123", "zzzzzzzz", "ééééééé"]:
        add(q); add(q, fuzzy=False)
    # 6. Préférences : un cas par dimension, puis combinaisons
    base = ["gaming", "cuisine", "tech", "sport", "audio", "café", "jumeau", "gratuit"]
    for q in base:
        add(q, {"preferred_type": "DIGITAL"}, fuzzy=False)
        add(q, {"preferred_type": "PHYSICAL"}, fuzzy=False)
        add(q, {"preferred_niche": "gaming"}, fuzzy=False)
        add(q, {"preferred_niche": "GAMING"}, fuzzy=False)
        add(q, {"max_price": 100.0, "user_location": "france"}, fuzzy=False)
        add(q, {"min_price": 50.0}, fuzzy=False)
        add(q, {"min_rating": 4.0}, fuzzy=False)
        add(q, {"max_price": 0.0}, fuzzy=False)
        add(q, {"preferred_type": "DIGITAL", "preferred_niche": "audio", "max_price": 300.0,
                "min_price": 5.0, "user_location": "Belgique", "min_rating": 3.0})
    add("gaming", {"min_rating": 5.0}, fuzzy=False)
    add("gaming", {"min_rating": 5.1}, fuzzy=False)            # filtre qui exclut tout
    add("gaming", {"max_price": 1.0, "min_price": 500.0}, fuzzy=False)   # fourchette impossible
    # 7. top_k
    for k in (1, 2, 3, 50, 1000):
        add("gaming", top_k=k, fuzzy=False)
        add("tech", top_k=k)
    # 8. Départage des ex æquo
    add("jumeau", fuzzy=False); add("twin-tag", fuzzy=False); add("jumeau", top_k=2, fuzzy=False)
    add("zero-id", fuzzy=False); add("grand-id", fuzzy=False)
    # 9. Cache : mêmes requêtes rejouées (statut CACHÉ), puis variantes de paramètres
    #    qui NE doivent PAS réutiliser l'entrée (fuzzy / max_dist / top_k font partie de la clé).
    add("gaming", fuzzy=False); add("gaming", fuzzy=False)
    add("gaming", fuzzy=True); add("gaming", fuzzy=True, max_dist=2); add("gaming", fuzzy=True, max_dist=2)
    add("gaming", top_k=3, fuzzy=False); add("gaming", top_k=3, fuzzy=False)
    add("  GAMING ", fuzzy=False)
    # 10. Erreurs attendues
    add(""); add("   "); add("gaming", max_dist=-1); add("gaming", top_k=0); add("gaming", top_k=-3)
    return cases


def to_prefs(d: dict) -> SearchPreferences:
    kw = dict(d)
    if "preferred_type" in kw:
        kw["preferred_type"] = ProductType.from_str(kw["preferred_type"])
    return SearchPreferences(**kw)


def rounding_cases(rng: random.Random) -> list[list[float]]:
    """Valeurs [x, round(x, 4)] : cas courants, quasi-égalités et égalités exactes (k/32)."""
    import math
    xs: list[float] = [k / 32 for k in range(1, 64)]                         # égalités exactes
    for _ in range(1200):
        base = rng.randint(0, 20000) / 10000 + 0.00005                        # proche d'une égalité décimale
        for step in (-2, -1, 0, 1, 2):
            v = base
            for _ in range(abs(step)):
                v = math.nextafter(v, math.inf if step > 0 else -math.inf)
            xs.append(v)
    xs += [rng.random() * rng.choice([0.01, 1, 1.3]) for _ in range(1000)]
    return [[x, round(x, 4)] for x in xs]


def generate() -> dict:
    rng = random.Random(20261009)
    products = build_catalog(rng)
    cases = build_cases(rng, products)

    tmp = HERE / "_ref_catalog.json"
    tmp.write_text(json.dumps({"products": products}, ensure_ascii=False), encoding="utf-8")
    eng = SearchEngine(cache_size=200)
    eng.load_catalog(tmp)
    tmp.unlink()

    out_cases = []
    for i, c in enumerate(cases, 1):
        case = {"id": f"R{i:03d}", **c}
        try:
            results, status = eng.search(
                c["query"], to_prefs(c.get("prefs", {})),
                fuzzy=c.get("fuzzy", True), max_dist=c.get("max_dist", 1), top_k=c.get("top_k", 10))
            case["expect"] = {"status": status, "results": results}
        except ValueError:
            case["expect"] = {"error": "invalid_argument"}
        out_cases.append(case)

    return {
        "version": 1,
        "description": "Jeu de référence croisé généré par le moteur Python (source de vérité). "
                       "À rejouer dans l'ordre sur un moteur neuf. Ne pas éditer à la main.",
        "tolerance": TOLERANCE,
        "rounding": rounding_cases(random.Random(4)),
        "products": products,
        "cases": out_cases,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = json.dumps(generate(), ensure_ascii=False, indent=1) + "\n"
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("reference.json périmé : relancer generate_reference.py")
            return 1
        print("reference.json à jour")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    n = json.loads(text)
    st: dict[str, int] = {}
    for c in n["cases"]:
        k = c["expect"].get("status", "ERREUR"); st[k] = st.get(k, 0) + 1
    print(f"{len(n['products'])} produits, {len(n['cases'])} requêtes -> {st}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
