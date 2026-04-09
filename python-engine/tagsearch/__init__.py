"""tagsearch — In-memory tag search engine for e-commerce."""
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
