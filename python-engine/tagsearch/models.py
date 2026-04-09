"""
tagsearch.models
================
Structures de données métier : ProductType, ProductMeta, SearchPreferences.
Tous les dataclasses utilisent slots=True (Python 3.10+) pour minimiser la RAM.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ProductType(Enum):
    """Type de produit. Encodé comme entier pour comparaison O(1)."""
    PHYSICAL = 0
    DIGITAL  = 1

    @classmethod
    def from_str(cls, value: str) -> "ProductType":
        """Parse depuis une chaîne JSON ('PHYSICAL' | 'DIGITAL')."""
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(f"ProductType invalide : '{value}'. Attendu : PHYSICAL | DIGITAL")


@dataclass(slots=True)
class ProductMeta:
    """
    Métadonnées complètes d'un produit.

    Args:
        name:         Nom affiché du produit.
        product_type: PHYSICAL ou DIGITAL.
        niche:        Catégorie (gaming, cuisine, beauté…). Interné via sys.intern.
        price:        Prix en euros (float).
        location:     Zone de livraison. None pour les produits digitaux.
        avg_rating:   Note moyenne des avis (0.0–5.0).
        review_count: Nombre d'avis. Pondère la fiabilité du rating (Bayesian).
        tags:         Liste de tags indexés.
    """
    name         : str
    product_type : ProductType
    niche        : str
    price        : float
    location     : str | None
    avg_rating   : float
    review_count : int
    tags         : list[str]

    def __post_init__(self) -> None:
        import sys
        self.niche = sys.intern(self.niche.lower())
        if not 0.0 <= self.avg_rating <= 5.0:
            raise ValueError(f"avg_rating doit être dans [0.0, 5.0], reçu : {self.avg_rating}")
        if self.review_count < 0:
            raise ValueError(f"review_count doit être >= 0, reçu : {self.review_count}")
        if self.price < 0:
            raise ValueError(f"price doit être >= 0, reçu : {self.price}")


@dataclass(slots=True)
class SearchPreferences:
    """
    Préférences utilisateur pour le re-ranking multidimensionnel.
    Toutes les valeurs sont optionnelles (None = neutre).

    Args:
        preferred_type:  Filtre doux sur le type (PHYSICAL/DIGITAL).
        preferred_niche: Boost +20% si la niche correspond.
        max_price:       Filtre dur : exclut les produits au-dessus.
        min_price:       Filtre dur : exclut les produits en-dessous.
        user_location:   Bonus +15% si la zone de livraison correspond.
        min_rating:      Filtre dur : exclut les produits en-dessous de ce seuil.
    """
    preferred_type  : ProductType | None = None
    preferred_niche : str | None         = None
    max_price       : float | None       = None
    min_price       : float | None       = None
    user_location   : str | None         = None
    min_rating      : float              = 0.0
