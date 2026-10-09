"""
tagsearch.scoring
=================
Réalisée par Gillesto66 & Kiro
BM25Index + calculate_final_score.

Formules canoniques documentées ici — source de vérité pour le portage TS/PHP.
Toute modification doit être répercutée dans shared-assets/catalog.json
(section scoring_constants) et dans les tests cross-langage.
"""

from __future__ import annotations
import logging
import math

from .models import ProductMeta, ProductType, SearchPreferences

logger = logging.getLogger(__name__)

# ── Constantes de scoring (synchronisées avec shared-assets/catalog.json) ───
BM25_K1          = 1.5
BM25_B           = 0.75
BM25_CAP         = 10.0   # Plafond de normalisation BM25 → score dans [0,1]
BM25_FLOOR       = 0.05   # Plancher : tag très fréquent reste visible
QUALITY_EXPONENT = 1.5    # Courbe convexe : pénalise sévèrement les notes < 3/5
PRIOR_MEAN       = 3.5    # Note a priori marché e-commerce
PRIOR_WEIGHT     = 10.0   # Équivalent 10 avis fictifs (lissage Bayesian)
TYPE_MISMATCH    = 0.1    # Facteur si type ne correspond pas (filtre doux)
NICHE_BOOST      = 1.2    # +20% si niche correspond
PROXIMITY_BONUS  = 1.15   # +15% si zone de livraison correspond
PRICE_BUDGET_BOOST = 1.1  # +10% si prix ≤ 50% du budget max


class BM25Index:
    """
    BM25 (Okapi BM25) in-memory sur les tags produits.

    Formule IDF :
        IDF(q) = log( (N - df(q) + 0.5) / (df(q) + 0.5) + 1 )
        Le +1 évite les valeurs négatives pour les termes très fréquents.

    Formule TF normalisée :
        TF_norm(q, d) = tf(q,d) × (K1+1) / (tf(q,d) + K1×(1 - B + B×dl/avgdl))

    Score BM25(d, Q) = Σ IDF(qi) × TF_norm(qi, d)
    """

    def __init__(self) -> None:
        self.tf:    dict[str, dict[int, int]] = {}
        self.df:    dict[str, int]            = {}
        self.dl:    dict[int, int]            = {}
        self.N:     int                       = 0
        self.avgdl: float                     = 0.0
        self._dl_sum: int                     = 0   # somme courante : avgdl en O(1) (et non O(N) par ajout)

    def index(self, product_id: int, tags: list[str]) -> None:
        """
        Indexe les tags d'un produit.

        Args:
            product_id: Identifiant unique du produit.
            tags:       Liste de tags (non normalisés, la normalisation est interne).

        Raises:
            ValueError: Si le produit est déjà indexé (appeler remove() d'abord).
        """
        if product_id in self.dl:
            raise ValueError(f"BM25: produit {product_id} déjà indexé — appeler remove() d'abord.")
        tags_lower = [t.lower() for t in tags]
        self.dl[product_id] = len(tags_lower)
        self._dl_sum += len(tags_lower)
        self.N += 1
        self.avgdl = self._dl_sum / self.N
        for tag in tags_lower:
            postings = self.tf.setdefault(tag, {})
            if product_id not in postings:
                self.df[tag] = self.df.get(tag, 0) + 1
            postings[product_id] = postings.get(product_id, 0) + 1
        logger.debug("BM25: produit %d indexé (%d tags, avgdl=%.2f)", product_id, len(tags_lower), self.avgdl)

    def remove(self, product_id: int, tags: list[str]) -> None:
        """Désindexe un produit. `tags` : les tags qui avaient été passés à index()."""
        if product_id not in self.dl:
            return
        self._dl_sum -= self.dl.pop(product_id)
        self.N -= 1
        self.avgdl = self._dl_sum / self.N if self.N else 0.0
        for tag in {t.lower() for t in tags}:
            postings = self.tf.get(tag)
            if postings is not None and postings.pop(product_id, None) is not None:
                self.df[tag] -= 1
                if not postings:
                    del self.tf[tag]
                    del self.df[tag]

    def score(self, product_id: int, query_tags: list[str]) -> float:
        """
        Calcule le score BM25 brut pour un produit et une liste de tags requête.

        Args:
            product_id:  ID du produit à scorer.
            query_tags:  Tags issus de la recherche DAWG (matched_tags).

        Returns:
            Score BM25 brut (non normalisé, non plafonné). Typiquement dans [0, 15].
        """
        if self.N == 0 or self.avgdl == 0:
            return 0.0
        total = 0.0
        dl_d = self.dl.get(product_id, 0)
        for tag in query_tags:
            tag = tag.lower()
            tf_val = self.tf.get(tag, {}).get(product_id, 0)
            if tf_val == 0: continue
            df_val = self.df.get(tag, 0)
            idf  = math.log((self.N - df_val + 0.5) / (df_val + 0.5) + 1)
            norm = tf_val * (BM25_K1 + 1) / (tf_val + BM25_K1 * (1 - BM25_B + BM25_B * dl_d / self.avgdl))
            total += idf * norm
        return total


def calculate_final_score(
    product_id: int,
    meta:       ProductMeta,
    bm25_raw:   float,
    prefs:      SearchPreferences,
) -> float | None:
    """
    Re-ranking multidimensionnel Phase 2.

    Formule (multiplicative) :
        final = bm25_norm × quality_mult × type_factor × niche_boost
                × proximity_bonus × price_factor

    Args:
        product_id: ID du produit (utilisé pour le logging).
        meta:       Métadonnées complètes du produit.
        bm25_raw:   Score BM25 brut retourné par BM25Index.score().
        prefs:      Préférences utilisateur pour le re-ranking.

    Returns:
        float arrondi à 4 décimales, ou None si le produit est exclu par un filtre dur.

    Raises:
        TypeError: Si meta ou prefs ne sont pas du bon type.
    """
    if not isinstance(meta, ProductMeta):
        raise TypeError(f"meta doit être ProductMeta, reçu : {type(meta)}")
    if not isinstance(prefs, SearchPreferences):
        raise TypeError(f"prefs doit être SearchPreferences, reçu : {type(prefs)}")

    # ── Filtres durs ────────────────────────────────────────────────────────
    if prefs.max_price is not None and meta.price > prefs.max_price:
        logger.debug("Produit %d exclu : prix %.2f > max %.2f", product_id, meta.price, prefs.max_price)
        return None
    if prefs.min_price is not None and meta.price < prefs.min_price:
        logger.debug("Produit %d exclu : prix %.2f < min %.2f", product_id, meta.price, prefs.min_price)
        return None
    if meta.avg_rating < prefs.min_rating:
        logger.debug("Produit %d exclu : rating %.1f < min %.1f", product_id, meta.avg_rating, prefs.min_rating)
        return None

    # ── Dim 1 : BM25 normalisé ──────────────────────────────────────────────
    bm25_norm = max(min(bm25_raw / BM25_CAP, 1.0), BM25_FLOOR)

    # ── Dim 2 : Qualité Bayesian ────────────────────────────────────────────
    bayesian = (meta.review_count * meta.avg_rating + PRIOR_MEAN * PRIOR_WEIGHT) / (meta.review_count + PRIOR_WEIGHT)
    quality_mult = (bayesian / 5.0) ** QUALITY_EXPONENT

    # ── Dim 3 : Type + Niche ────────────────────────────────────────────────
    type_factor = TYPE_MISMATCH if (
        prefs.preferred_type is not None and meta.product_type != prefs.preferred_type
    ) else 1.0

    niche_factor = NICHE_BOOST if (
        prefs.preferred_niche is not None
        and meta.niche == prefs.preferred_niche.lower()
    ) else 1.0

    # ── Dim 4 : Proximité ───────────────────────────────────────────────────
    if meta.location is None:
        proximity = 1.0
    elif prefs.user_location is not None and meta.location.lower() == prefs.user_location.lower():
        proximity = PROXIMITY_BONUS
    else:
        proximity = 1.0

    # ── Dim 5 : Prix (filtre doux) ──────────────────────────────────────────
    if prefs.max_price is not None and prefs.max_price > 0:
        price_factor = PRICE_BUDGET_BOOST if (meta.price / prefs.max_price) <= 0.5 else 1.0
    else:
        price_factor = 1.0

    final = bm25_norm * quality_mult * type_factor * niche_factor * proximity * price_factor
    result = round(final, 4)
    logger.debug(
        "Produit %d | bm25=%.4f qmult=%.4f type=%.1f niche=%.1f prox=%.2f price=%.1f → %.4f",
        product_id, bm25_norm, quality_mult, type_factor, niche_factor, proximity, price_factor, result
    )
    return result
