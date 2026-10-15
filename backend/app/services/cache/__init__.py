"""In-process caching layer for KIP embedding and search results."""

from app.services.cache.embedding_cache import EmbeddingCache
from app.services.cache.search_cache import (
    SearchCache,
    get_default_search_cache,
    reset_default_search_cache,
)

__all__ = [
    "EmbeddingCache",
    "SearchCache",
    "get_default_search_cache",
    "reset_default_search_cache",
]
