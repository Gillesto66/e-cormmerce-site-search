"""
tagsearch.engine
================
Réalisée par Gillesto66 & Kiro
SearchEngine : point d'entrée public de la bibliothèque.
Orchestre DAWG, BM25Index, CompressedPostingsList, LRUCache et calculate_final_score.
"""

from __future__ import annotations
import json
import logging
from collections.abc import Iterable
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

    Indexation paresseuse : add_product()/add_products() n'enregistrent que les
    données ; le DAWG est reconstruit UNE fois, au premier search() suivant ou
    via commit(). Charger N produits coûte donc O(N), pas O(N²).

    Example:
        >>> engine = SearchEngine()
        >>> engine.load_catalog("shared-assets/catalog.json")
        >>> results, status = engine.search("gaming", fuzzy=True)

    Args:
        cache_size: Capacité du cache LRU (nombre de requêtes mémorisées).
    """

    def __init__(self, cache_size: int = 200) -> None:
        self.dawg: DAWG = DAWG()
        self.inverted_index: dict[str, CompressedPostingsList] = {}
        self.catalog: dict[int, ProductMeta] = {}
        self.bm25: BM25Index = BM25Index()
        self.cache: LRUCache = LRUCache(capacity=cache_size)
        self._dirty_tags: set[str] = set()     # postings à compresser au prochain commit
        self._vocab_changed: bool = False       # DAWG à reconstruire au prochain commit
        logger.info("SearchEngine initialisé (cache_size=%d)", cache_size)

    # ── Chargement ──────────────────────────────────────────────────────────

    def load_catalog(self, path: str | Path) -> None:
        """
        Charge un catalogue depuis un fichier JSON (format shared-assets/catalog.json).
        Atomique : si un produit est invalide, rien n'est ajouté.

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

        raw_products = data.get("products", [])
        if not raw_products:
            logger.warning("Catalogue vide : aucun produit chargé depuis %s", path)
            return

        parsed: list[tuple[int, ProductMeta]] = []
        for raw in raw_products:
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
                parsed.append((int(raw["id"]), meta))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Produit invalide (id={raw.get('id', '?')}) : {exc}") from exc

        self.add_products(parsed)
        logger.info("Catalogue chargé : %d produits depuis %s", len(parsed), path)

    def add_product(self, product_id: int, meta: ProductMeta) -> None:
        """
        Enregistre un produit. L'index de recherche est mis à jour au prochain
        search() ou commit() (reconstruction unique, pas une par produit).
        Un identifiant déjà présent est REMPLACÉ proprement (postings et BM25 mis à jour).

        Raises:
            ValueError: Si product_id est négatif.
        """
        self._add(product_id, meta)
        self.cache.invalidate()

    def add_products(self, items: Iterable[tuple[int, ProductMeta]]) -> int:
        """
        Ajoute un lot de produits puis reconstruit l'index une seule fois.

        Args:
            items: itérable de (product_id, meta).

        Returns:
            Nombre de produits traités.
        """
        count = 0
        for product_id, meta in items:
            self._add(product_id, meta)
            count += 1
        self.cache.invalidate()
        self.commit()
        return count

    def remove_product(self, product_id: int) -> bool:
        """Retire un produit de l'index. Retourne False s'il n'existait pas."""
        if product_id not in self.catalog:
            return False
        self._remove(product_id)
        self.cache.invalidate()
        return True

    def commit(self) -> None:
        """
        Finalise l'index : compresse uniquement les postings modifiés et
        reconstruit le DAWG si le vocabulaire a changé. Idempotent.
        """
        for tag in self._dirty_tags:
            postings = self.inverted_index.get(tag)
            if postings is not None:
                postings.flush()
        self._dirty_tags.clear()
        if self._vocab_changed:
            self.dawg = DAWG.build(self.inverted_index.keys())
            self._vocab_changed = False
            logger.debug("DAWG reconstruit : %d nœuds", self.dawg.node_count())

    @property
    def dirty(self) -> bool:
        """True si des produits ont été ajoutés/retirés depuis le dernier commit()."""
        return bool(self._dirty_tags) or self._vocab_changed

    def _add(self, product_id: int, meta: ProductMeta) -> None:
        if product_id < 0:
            raise ValueError(f"product_id doit être >= 0, reçu : {product_id}")
        if product_id in self.catalog:
            logger.warning("Produit %d déjà indexé — remplacement.", product_id)
            self._remove(product_id)

        self.catalog[product_id] = meta
        for tag in {t.lower() for t in meta.tags}:
            postings = self.inverted_index.get(tag)
            if postings is None:
                postings = self.inverted_index[tag] = CompressedPostingsList()
                self._vocab_changed = True
            postings.add(product_id)
            self._dirty_tags.add(tag)
        self.bm25.index(product_id, meta.tags)

    def _remove(self, product_id: int) -> None:
        meta = self.catalog.pop(product_id)
        for tag in {t.lower() for t in meta.tags}:
            postings = self.inverted_index[tag]
            postings.remove(product_id)
            if len(postings) == 0:
                del self.inverted_index[tag]
                self._dirty_tags.discard(tag)
                self._vocab_changed = True
            else:
                self._dirty_tags.add(tag)
        self.bm25.remove(product_id, meta.tags)

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
            5. Tri (score décroissant, puis id croissant) + top_k + cache LRU

        Ordre déterministe : les ex æquo de score sont départagés par `id` croissant,
        et les tags appariés sont ordonnés (distance, tag) — règle identique en
        Python, JS et PHP.

        Args:
            query:    Requête utilisateur (chaîne brute, normalisée en interne).
            prefs:    Préférences de re-ranking. None = comportement neutre.
            fuzzy:    Si True, utilise la recherche floue (Levenshtein + pruning).
            max_dist: Distance de Levenshtein maximale (1 = 1 faute de frappe).
            top_k:    Nombre maximum de résultats retournés (>= 1).

        Returns:
            Tuple (results, status) où :
                results : liste de dicts triés par score décroissant.
                    Champs : id, name, type, niche, price, rating, reviews, score.
                status  : "CACHÉ" | "CALCULÉ" | "MISS".

        Raises:
            ValueError: Si query est vide, max_dist < 0 ou top_k < 1.
                Toute autre exception est une vraie erreur et remonte telle quelle.
        """
        if not query or not query.strip():
            raise ValueError("La requête ne peut pas être vide.")
        if max_dist < 0:
            raise ValueError(f"max_dist doit être >= 0, reçu : {max_dist}")
        if top_k < 1:
            raise ValueError(f"top_k doit être >= 1, reçu : {top_k}")
        if not self.catalog:
            logger.warning("search() appelé sur un index vide.")
            return [], "MISS"

        if prefs is None:
            prefs = SearchPreferences()
        if self.dirty:
            self.commit()

        query_lower = query.strip().lower()
        cache_key = f"{query_lower}|{prefs}|{fuzzy}|{max_dist}|{top_k}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache HIT pour '%s'", query)
            return [dict(r) for r in cached], "CACHÉ"

        # 1. Tags via DAWG
        matched_tags = (
            self.dawg.fuzzy_search(query_lower, max_dist)
            if fuzzy else
            self.dawg.autocomplete(query_lower)
        )
        if not matched_tags:
            logger.debug("Aucun tag trouvé pour '%s'", query)
            return [], "MISS"

        # 2. Candidats via inverted index
        candidate_ids: set[int] = set()
        for tag in matched_tags:
            candidate_ids.update(self.inverted_index[tag].decompress())
        if not candidate_ids:
            return [], "MISS"

        # 3. BM25 + re-ranking
        results: list[dict] = []
        for pid in candidate_ids:
            meta = self.catalog[pid]
            bm25_raw    = self.bm25.score(pid, matched_tags)
            final_score = calculate_final_score(pid, meta, bm25_raw, prefs)
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

        results.sort(key=lambda r: (-r["score"], r["id"]))
        final_list = results[:top_k]

        self.cache.put(cache_key, final_list)
        logger.info("Recherche '%s' : %d résultats (%d candidats)", query, len(final_list), len(candidate_ids))
        return [dict(r) for r in final_list], "CALCULÉ"
