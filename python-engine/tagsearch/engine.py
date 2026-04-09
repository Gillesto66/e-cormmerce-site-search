"""
tagsearch.engine
================
SearchEngine : point d'entrée public de la bibliothèque.
Orchestre DAWG, BM25Index, CompressedPostingsList, LRUCache et calculate_final_score.
"""

from __future__ import annotations
import json
import logging
import sys
from pathlib import Path

from .models import ProductMeta, ProductType, SearchPreferences
from .scoring import BM25Index, calculate_final_score
from .structures import DAWG, CompressedPostingsList, LRUCache

logger = logging.getLogger(__name__)


class SearchEngine:
    """
    Moteur de recherche in-memory pour tags e-commerce.

    Architecture :
        DAWG                  → index des tags (autocomplete + fuzzy Levenshtein)
        CompressedPostingsList → inverted index compressé (delta + VarInt)
        BM25Index             → scoring textuel
        calculate_final_score → re-ranking 5 dimensions
        LRUCache              → cache des résultats de recherche

    Example:
        >>> engine = SearchEngine()
        >>> engine.load_catalog("shared-assets/catalog.json")
        >>> results, status = engine.search("gaming", fuzzy=True)

    Args:
        cache_size: Capacité du cache LRU (nombre de requêtes mémorisées).
    """

    def __init__(self, cache_size: int = 200) -> None:
        self._all_tags: list[str] = []
        self.dawg: DAWG = DAWG()
        self.inverted_index: dict[str, CompressedPostingsList] = {}
        self.catalog: dict[int, ProductMeta] = {}
        self.bm25: BM25Index = BM25Index()
        self.cache: LRUCache = LRUCache(capacity=cache_size)
        logger.info("SearchEngine initialisé (cache_size=%d)", cache_size)

    # ── Chargement ──────────────────────────────────────────────────────────

    def load_catalog(self, path: str | Path) -> None:
        """
        Charge un catalogue depuis un fichier JSON (format shared-assets/catalog.json).

        Args:
            path: Chemin vers le fichier JSON.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            ValueError:        Si le JSON est malformé ou un produit est invalide.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Catalogue introuvable : {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON malformé dans {path} : {exc}") from exc

        products = data.get("products", [])
        if not products:
            logger.warning("Catalogue vide : aucun produit chargé depuis %s", path)
            return

        for raw in products:
            try:
                meta = ProductMeta(
                    name         = raw["name"],
                    product_type = ProductType.from_str(raw["type"]),
                    niche        = raw["niche"],
                    price        = float(raw["price"]),
                    location     = raw.get("location"),
                    avg_rating   = float(raw["avg_rating"]),
                    review_count = int(raw["review_count"]),
                    tags         = [str(t) for t in raw["tags"]],
                )
                self.add_product(int(raw["id"]), meta)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Produit invalide (id={raw.get('id', '?')}) : {exc}") from exc

        logger.info("Catalogue chargé : %d produits depuis %s", len(products), path)

    def add_product(self, product_id: int, meta: ProductMeta) -> None:
        """
        Indexe un produit.

        Args:
            product_id: Identifiant unique (entier positif).
            meta:       Métadonnées complètes du produit.

        Raises:
            ValueError: Si product_id est négatif ou déjà présent.
        """
        if product_id < 0:
            raise ValueError(f"product_id doit être >= 0, reçu : {product_id}")
        if product_id in self.catalog:
            logger.warning("Produit %d déjà indexé — écrasement.", product_id)

        self.catalog[product_id] = meta

        for tag in meta.tags:
            tag_lower = tag.lower()
            if tag_lower not in self.inverted_index:
                self.inverted_index[tag_lower] = CompressedPostingsList()
                self._all_tags.append(tag_lower)
            self.inverted_index[tag_lower].add(product_id)

        self.bm25.index(product_id, meta.tags)

        for pl in self.inverted_index.values():
            pl.flush()
        self.dawg = DAWG.build(self._all_tags)
        self.cache.invalidate()
        logger.debug("Produit %d indexé : '%s'", product_id, meta.name)

    # ── Recherche ────────────────────────────────────────────────────────────

    def search(
        self,
        query    : str,
        prefs    : SearchPreferences | None = None,
        fuzzy    : bool = True,
        max_dist : int  = 1,
        top_k    : int  = 10,
    ) -> tuple[list[dict], str]:
        """
        Recherche multidimensionnelle in-memory.

        Flux :
            1. DAWG fuzzy/autocomplete → matched_tags
            2. CompressedPostingsList  → candidate_ids
            3. BM25Index.score()       → bm25_raw par produit
            4. calculate_final_score() → score final (5 dimensions)
            5. Tri décroissant + top_k + cache LRU

        Args:
            query:    Requête utilisateur (chaîne brute, normalisée en interne).
            prefs:    Préférences de re-ranking. None = comportement neutre.
            fuzzy:    Si True, utilise la recherche floue (Levenshtein + pruning).
            max_dist: Distance de Levenshtein maximale (1 = 1 faute de frappe).
            top_k:    Nombre maximum de résultats retournés.

        Returns:
            Tuple (results, status) où :
                results : liste de dicts triés par score décroissant.
                    Champs : id, name, type, niche, price, rating, reviews, score.
                status  : "CACHÉ" | "CALCULÉ" | "MISS".

        Raises:
            ValueError: Si query est vide ou max_dist < 0.
        """
        if not query or not query.strip():
            raise ValueError("La requête ne peut pas être vide.")
        if max_dist < 0:
            raise ValueError(f"max_dist doit être >= 0, reçu : {max_dist}")
        if not self.catalog:
            logger.warning("search() appelé sur un index vide.")
            return [], "MISS"

        if prefs is None:
            prefs = SearchPreferences()

        cache_key = f"{query.strip().lower()}|{prefs}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache HIT pour '%s'", query)
            return cached, "CACHÉ"

        query_lower = query.strip().lower()

        # 1. Tags via DAWG
        try:
            matched_tags = (
                self.dawg.fuzzy_search(query_lower, max_dist)
                if fuzzy else
                self.dawg.autocomplete(query_lower)
            )
        except Exception as exc:
            logger.error("Erreur DAWG pour '%s' : %s", query, exc)
            return [], "MISS"

        if not matched_tags:
            logger.debug("Aucun tag trouvé pour '%s'", query)
            return [], "MISS"

        # 2. Candidats via inverted index
        candidate_ids: set[int] = set()
        for tag in matched_tags:
            if tag in self.inverted_index:
                try:
                    candidate_ids.update(self.inverted_index[tag].decompress())
                except Exception as exc:
                    logger.error("Erreur décompression postings '%s' : %s", tag, exc)

        if not candidate_ids:
            return [], "MISS"

        # 3. BM25 + re-ranking
        results: list[dict] = []
        for pid in candidate_ids:
            meta = self.catalog.get(pid)
            if meta is None:
                logger.warning("product_id %d dans l'index mais absent du catalogue.", pid)
                continue
            try:
                bm25_raw    = self.bm25.score(pid, matched_tags)
                final_score = calculate_final_score(pid, meta, bm25_raw, prefs)
            except Exception as exc:
                logger.error("Erreur scoring produit %d : %s", pid, exc)
                continue

            if final_score is None:
                continue

            results.append({
                "id"     : pid,
                "name"   : meta.name,
                "type"   : meta.product_type.name,
                "niche"  : meta.niche,
                "price"  : meta.price,
                "rating" : meta.avg_rating,
                "reviews": meta.review_count,
                "score"  : final_score,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        final_list = results[:top_k]

        self.cache.put(cache_key, final_list)
        logger.info("Recherche '%s' : %d résultats (%d candidats)", query, len(final_list), len(candidate_ids))
        return final_list, "CALCULÉ"
