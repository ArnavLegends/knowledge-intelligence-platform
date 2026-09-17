"""ChromaDB vector store provider adapter."""

import os
from collections.abc import Sequence

import chromadb

from app.core.exceptions import VectorStoreError
from app.services.vector_store.base import VectorStoreProvider
from app.services.vector_store.models import StoredVector, VectorSearchResult


class ChromaVectorStoreProvider(VectorStoreProvider):
    """Adapter for ChromaDB."""

    def __init__(
        self, collection_name: str, persist_directory: str | None = None
    ) -> None:
        try:
            if persist_directory:
                # Ensure directory exists if persisting
                os.makedirs(persist_directory, exist_ok=True)
                self._client = chromadb.PersistentClient(path=persist_directory)
            else:
                self._client = chromadb.EphemeralClient()

            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},  # Default to cosine similarity
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to initialize ChromaDB: {e}") from e

    @property
    def name(self) -> str:
        return "chroma"

    def upsert(self, records: Sequence[StoredVector]) -> None:
        if not records:
            return

        ids = [record.id for record in records]
        embeddings = [record.vector for record in records]
        # ChromaDB rejects empty dicts, so we use None for empty metadata
        metadatas = [record.metadata if record.metadata else None for record in records]

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB upsert failed: {e}") from e

    def retrieve(self, ids: Sequence[str]) -> list[StoredVector]:
        if not ids:
            return []

        try:
            result = self._collection.get(
                ids=list(ids), include=["embeddings", "metadatas"]
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB retrieve failed: {e}") from e

        if not result or not result["ids"]:
            return []

        retrieved_ids = result["ids"]
        retrieved_embeddings = result.get("embeddings")
        if retrieved_embeddings is None:
            retrieved_embeddings = []

        retrieved_metadatas = result.get("metadatas")
        if retrieved_metadatas is None:
            retrieved_metadatas = []

        # Protect against mismatched lengths from chroma API
        if not (
            len(retrieved_ids) == len(retrieved_embeddings) == len(retrieved_metadatas)
        ):
            raise VectorStoreError("ChromaDB returned malformed data.")

        records = []
        for i, record_id in enumerate(retrieved_ids):
            records.append(
                StoredVector(
                    id=record_id,
                    vector=retrieved_embeddings[i],
                    metadata=retrieved_metadatas[i] or {},
                )
            )
        return records

    def delete(self, ids: Sequence[str]) -> None:
        if not ids:
            return

        try:
            self._collection.delete(ids=list(ids))
        except Exception as e:
            raise VectorStoreError(f"ChromaDB delete failed: {e}") from e

    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception as e:
            raise VectorStoreError(f"ChromaDB count failed: {e}") from e

    def search(
        self, query_vector: list[float], top_k: int, threshold: float | None = None
    ) -> list[VectorSearchResult]:
        if not query_vector:
            return []

        if top_k <= 0:
            return []

        try:
            result = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["embeddings", "metadatas", "distances"],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB search failed: {e}") from e

        if not result or not result["ids"] or not result["ids"][0]:
            return []

        # Chroma query returns a list of lists because we can send multiple queries
        retrieved_ids = result["ids"][0]
        retrieved_embeddings = result.get("embeddings")
        if retrieved_embeddings is None or not retrieved_embeddings:
            retrieved_embeddings = [[]] * len(retrieved_ids)
        else:
            retrieved_embeddings = retrieved_embeddings[0]

        retrieved_metadatas = result.get("metadatas")
        if retrieved_metadatas is None or not retrieved_metadatas:
            retrieved_metadatas = [[]] * len(retrieved_ids)
        else:
            retrieved_metadatas = retrieved_metadatas[0]

        retrieved_distances = result.get("distances")
        if retrieved_distances is None or not retrieved_distances:
            retrieved_distances = [None] * len(retrieved_ids)
        else:
            retrieved_distances = retrieved_distances[0]

        # Ensure lengths match
        if not (
            len(retrieved_ids)
            == len(retrieved_embeddings)
            == len(retrieved_metadatas)
            == len(retrieved_distances)
        ):
            raise VectorStoreError("ChromaDB returned malformed search data.")

        records = []
        for i, record_id in enumerate(retrieved_ids):
            distance = retrieved_distances[i]
            if threshold is not None and distance is not None and distance > threshold:
                continue

            records.append(
                VectorSearchResult(
                    id=record_id,
                    vector=retrieved_embeddings[i],
                    metadata=retrieved_metadatas[i] or {},
                    distance=distance,
                )
            )

        return records
