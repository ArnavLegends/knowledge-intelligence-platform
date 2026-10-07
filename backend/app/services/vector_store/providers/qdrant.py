"""Qdrant vector store provider adapter with payload-based multitenancy."""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.exceptions import VectorStoreError
from app.services.vector_store.base import VectorStoreProvider
from app.services.vector_store.models import StoredVector, VectorSearchResult

logger = logging.getLogger(__name__)


def _deterministic_point_id(workspace_id: str, chunk_id: str) -> str:
    """Generate deterministic point UUID scoped to workspace."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kip://{workspace_id}/{chunk_id}"))


class QdrantVectorStoreProvider(VectorStoreProvider):
    """Adapter for Qdrant Cloud and local in-memory instances."""

    def __init__(
        self,
        collection_name: str = "knowledge_base",
        url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        embedding_dimensions: int = 768,
        client: QdrantClient | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._embedding_dimensions = embedding_dimensions

        try:
            if client is not None:
                self._client = client
            elif url == ":memory:" or (not url and not api_key):
                self._client = QdrantClient(":memory:")
            else:
                self._client = QdrantClient(
                    url=url,
                    api_key=api_key or None,
                    timeout=timeout_seconds,
                )

            self._ensure_collection()
        except Exception as e:
            if isinstance(e, VectorStoreError):
                raise
            raise VectorStoreError(f"Failed to initialize Qdrant: {e}") from e

    def _ensure_collection(self) -> None:
        """Create collection if absent, or validate dimensions and distance."""
        exists = self._client.collection_exists(collection_name=self._collection_name)

        if not exists:
            logger.info(
                "Creating Qdrant collection %s with dim %d and COSINE distance",
                self._collection_name,
                self._embedding_dimensions,
            )
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self._embedding_dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            # Create payload keyword index for workspace_id for multitenant filtering
            try:
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="workspace_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                logger.warning("Could not create payload index on workspace_id: %s", e)

            try:
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name="document_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                logger.warning("Could not create payload index on document_id: %s", e)
        else:
            # Validate existing collection configuration
            info = self._client.get_collection(collection_name=self._collection_name)
            vectors_config = info.config.params.vectors

            if isinstance(vectors_config, dict):
                # Named vectors or default empty-key vector
                vector_params = vectors_config.get("") or next(
                    iter(vectors_config.values())
                )
            else:
                vector_params = vectors_config

            actual_size = getattr(vector_params, "size", None)
            actual_distance = getattr(vector_params, "distance", None)

            if actual_size != self._embedding_dimensions:
                raise VectorStoreError(
                    f"Qdrant collection '{self._collection_name}' dimension mismatch: "
                    f"configured {self._embedding_dimensions}, found {actual_size}."
                )

            if actual_distance != qmodels.Distance.COSINE:
                raise VectorStoreError(
                    f"Qdrant collection '{self._collection_name}' "
                    f"distance metric mismatch: "
                    f"configured COSINE, found {actual_distance}."
                )

    @property
    def name(self) -> str:
        return "qdrant"

    def upsert(self, records: Sequence[StoredVector], workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector upsert.")
        if not records:
            return

        points = []
        for record in records:
            point_id = _deterministic_point_id(workspace_id, record.id)
            payload = {
                **record.metadata,
                "workspace_id": workspace_id,
                "document_id": record.metadata.get("document_id")
                or record.metadata.get("doc"),
                "chunk_id": record.id,
                "filename": record.metadata.get("filename"),
                "text": record.metadata.get("text"),
            }
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=record.vector,
                    payload=payload,
                )
            )

        try:
            self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Qdrant upsert failed: {e}") from e

    def retrieve(self, ids: Sequence[str], workspace_id: str) -> list[StoredVector]:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector retrieve.")
        if not ids:
            return []

        point_ids = [
            _deterministic_point_id(workspace_id, chunk_id) for chunk_id in ids
        ]

        try:
            records = self._client.retrieve(
                collection_name=self._collection_name,
                ids=point_ids,
                with_payload=True,
                with_vectors=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Qdrant retrieve failed: {e}") from e

        results = []
        for rec in records:
            payload = rec.payload or {}
            # Verify workspace ownership
            if payload.get("workspace_id") != workspace_id:
                continue

            chunk_id = payload.get("chunk_id", str(rec.id))
            vector = rec.vector
            if isinstance(vector, dict):
                vector = list(vector.values())[0]

            results.append(
                StoredVector(
                    id=chunk_id,
                    vector=vector if isinstance(vector, list) else list(vector),
                    metadata=payload,
                )
            )
        return results

    def delete(self, ids: Sequence[str], workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for vector delete.")
        if not ids:
            return

        point_ids = [
            _deterministic_point_id(workspace_id, chunk_id) for chunk_id in ids
        ]

        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=qmodels.PointIdsList(points=point_ids),
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Qdrant delete failed: {e}") from e

    def count(self, workspace_id: str | None = None) -> int:
        try:
            if workspace_id:
                filter_ = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="workspace_id",
                            match=qmodels.MatchValue(value=workspace_id),
                        )
                    ]
                )
                res = self._client.count(
                    collection_name=self._collection_name,
                    count_filter=filter_,
                    exact=True,
                )
            else:
                res = self._client.count(
                    collection_name=self._collection_name,
                    exact=True,
                )
            return res.count
        except Exception as e:
            raise VectorStoreError(f"Qdrant count failed: {e}") from e

    def document_exists(self, document_id: str, workspace_id: str) -> bool:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for document_exists.")
        if not document_id:
            return False

        try:
            filter_ = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=workspace_id),
                    ),
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    ),
                ]
            )
            res = self._client.count(
                collection_name=self._collection_name,
                count_filter=filter_,
                exact=True,
            )
            return res.count > 0
        except Exception as e:
            raise VectorStoreError(f"Qdrant document_exists failed: {e}") from e

    def delete_document(self, document_id: str, workspace_id: str) -> None:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for delete_document.")
        if not document_id:
            return

        try:
            filter_ = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=workspace_id),
                    ),
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    ),
                ]
            )
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=filter_,
                wait=True,
            )
        except Exception as e:
            raise VectorStoreError(f"Qdrant delete_document failed: {e}") from e

    def list_documents(self, workspace_id: str) -> list[dict[str, Any]]:
        if not workspace_id or not workspace_id.strip():
            raise VectorStoreError("workspace_id is required for list_documents.")

        try:
            filter_ = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=workspace_id),
                    )
                ]
            )
            points, _ = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=filter_,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            raise VectorStoreError(f"Qdrant list_documents failed: {e}") from e

        docs_map: dict[str, dict[str, Any]] = {}
        for pt in points:
            p = pt.payload or {}
            doc_id = p.get("document_id")
            if not doc_id:
                continue

            if doc_id not in docs_map:
                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "filename": p.get("filename", "unknown"),
                    "chunks_indexed": 0,
                    "media_type": p.get("media_type", "application/octet-stream"),
                    "size_bytes": p.get("size_bytes", 0),
                    "parser": p.get("parser", ""),
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

        filter_ = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="workspace_id",
                    match=qmodels.MatchValue(value=workspace_id),
                )
            ]
        )

        try:
            # Query points in Qdrant with workspace filter
            search_results = self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=filter_,
                limit=top_k,
                with_payload=True,
                with_vectors=True,
            ).points
        except Exception as e:
            raise VectorStoreError(f"Qdrant search failed: {e}") from e

        results = []
        for hit in search_results:
            payload = hit.payload or {}
            # Defensive check: ensure returned hit belongs to the requested workspace
            if payload.get("workspace_id") != workspace_id:
                continue

            chunk_id = payload.get("chunk_id", str(hit.id))
            # Qdrant score for COSINE distance is cosine similarity: higher is better
            # In KIP cosine distance, distance = 1 - similarity if score is similarity
            score = hit.score
            # Distance: 1 - cosine_similarity (capped at 0)
            distance = max(0.0, 1.0 - score) if score is not None else None

            if threshold is not None and distance is not None and distance > threshold:
                continue

            vector = hit.vector
            if isinstance(vector, dict):
                vector = list(vector.values())[0]

            results.append(
                VectorSearchResult(
                    id=chunk_id,
                    vector=vector if isinstance(vector, list) else list(vector),
                    metadata=payload,
                    distance=distance,
                )
            )

        return results
