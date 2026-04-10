"""
Bibliothèque Python In-Memory Search — Tags E-commerce
Réalisée par Gillesto66 & Kiro
"""
from .engine import SearchEngine
from .models import ProductMeta, ProductType, SearchPreferences
from .scoring import calculate_final_score

__all__ = [
    "SearchEngine",
    "ProductMeta",
    "ProductType",
    "SearchPreferences",
    "calculate_final_score",
]
