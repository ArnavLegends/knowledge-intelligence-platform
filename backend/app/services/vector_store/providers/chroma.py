"""ChromaDB vector store provider adapter."""

import os
import uuid
from collections.abc import Sequence
from typing import Any

import chromadb

from app.core.exceptions import VectorStoreError
from app.services.vector_store.base import VectorStoreProvider
from app.services.vector_store.models import StoredVector, VectorSearchResult


def _deterministic_point_id(workspace_id: str, chunk_id: str) -> str:
    """Generate deterministic point UUID scoped to workspace."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kip://{workspace_id}/{chunk_id}"))


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

    def upsert(self, records: Sequence[StoredVector], workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector upsert.")
        if not records:
            return

        ids = [_deterministic_point_id(workspace_id, record.id) for record in records]
        embeddings = [record.vector for record in records]
        metadatas = []
        for record in records:
            meta = record.metadata.copy() if record.metadata else {}
            meta["workspace_id"] = workspace_id
            meta["chunk_id"] = record.id
            metadatas.append(meta)

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB upsert failed: {e}") from e

    def retrieve(self, ids: Sequence[str], workspace_id: str) -> list[StoredVector]:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector retrieve.")
        if not ids:
            return []

        point_ids = [_deterministic_point_id(workspace_id, cid) for cid in ids]

        try:
            result = self._collection.get(
                ids=point_ids,
                where={"workspace_id": workspace_id},
                include=["embeddings", "metadatas"],
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

        if not (
            len(retrieved_ids) == len(retrieved_embeddings) == len(retrieved_metadatas)
        ):
            raise VectorStoreError("ChromaDB returned malformed data.")

        records = []
        for i, _ in enumerate(retrieved_ids):
            meta = retrieved_metadatas[i] or {}
            orig_id = meta.get("chunk_id", retrieved_ids[i])
            records.append(
                StoredVector(
                    id=orig_id,
                    vector=retrieved_embeddings[i],
                    metadata=meta,
                )
            )
        return records

    def delete(self, ids: Sequence[str], workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector delete.")
        if not ids:
            return

        point_ids = [_deterministic_point_id(workspace_id, cid) for cid in ids]
        try:
            self._collection.delete(
                ids=point_ids,
                where={"workspace_id": workspace_id},
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB delete failed: {e}") from e

    def count(self, workspace_id: str | None = None) -> int:
        try:
            if workspace_id:
                res = self._collection.get(
                    where={"workspace_id": workspace_id},
                    include=[],
                )
                return len(res["ids"]) if res and "ids" in res else 0
            return self._collection.count()
        except Exception as e:
            raise VectorStoreError(f"ChromaDB count failed: {e}") from e

    def document_exists(self, document_id: str, workspace_id: str) -> bool:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for document_exists.")
        if not document_id:
            return False

        try:
            result = self._collection.get(
                where={
                    "$and": [
                        {"document_id": document_id},
                        {"workspace_id": workspace_id},
                    ]
                },
                limit=1,
            )
            return bool(result and result["ids"])
        except Exception as e:
            raise VectorStoreError(f"ChromaDB document_exists failed: {e}") from e

    def delete_document(self, document_id: str, workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for delete_document.")
        if not document_id:
            return

        try:
            self._collection.delete(
                where={
                    "$and": [
                        {"document_id": document_id},
                        {"workspace_id": workspace_id},
                    ]
                }
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB delete_document failed: {e}") from e

    def list_documents(self, workspace_id: str) -> list[dict[str, Any]]:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for list_documents.")

        try:
            result = self._collection.get(
                where={"workspace_id": workspace_id},
                include=["metadatas"],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB list_documents failed: {e}") from e

        metadatas = result.get("metadatas") or [] if result else []
        docs_map: dict[str, dict[str, Any]] = {}
        for m in metadatas:
            if not m:
                continue
            doc_id = m.get("document_id")
            if not doc_id:
                continue
            if doc_id not in docs_map:
                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "filename": m.get("filename", "unknown"),
                    "chunks_indexed": 0,
                    "media_type": m.get("media_type", "application/octet-stream"),
                    "size_bytes": m.get("size_bytes", 0),
                    "parser": m.get("parser", ""),
                    "status": "indexed",
                }
            docs_map[doc_id]["chunks_indexed"] += 1

        return list(docs_map.values())

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        workspace_id: str,
        threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector search.")
        if not query_vector or top_k <= 0:
            return []

        try:
            result = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where={"workspace_id": workspace_id},
                include=["embeddings", "metadatas", "distances"],
            )
        except Exception as e:
            raise VectorStoreError(f"ChromaDB search failed: {e}") from e

        if not result or not result["ids"] or not result["ids"][0]:
            return []

        retrieved_ids = result["ids"][0]
        embeddings_raw = result.get("embeddings")
        if embeddings_raw is not None and len(embeddings_raw) > 0:
            retrieved_embeddings = embeddings_raw[0]
        else:
            retrieved_embeddings = [[]] * len(retrieved_ids)

        metadatas_raw = result.get("metadatas")
        if metadatas_raw is not None and len(metadatas_raw) > 0:
            retrieved_metadatas = metadatas_raw[0]
        else:
            retrieved_metadatas = [{}] * len(retrieved_ids)

        distances_raw = result.get("distances")
        if distances_raw is not None and len(distances_raw) > 0:
            retrieved_distances = distances_raw[0]
        else:
            retrieved_distances = [None] * len(retrieved_ids)

        records = []
        for i, record_id in enumerate(retrieved_ids):
            meta = retrieved_metadatas[i] or {}
            # Defensive check
            if meta.get("workspace_id") != workspace_id:
                continue

            distance = retrieved_distances[i]
            if threshold is not None and distance is not None and distance > threshold:
                continue

            orig_id = meta.get("chunk_id", record_id)
            records.append(
                VectorSearchResult(
                    id=orig_id,
                    vector=retrieved_embeddings[i],
                    metadata=meta,
                    distance=distance,
                )
            )

        return records
