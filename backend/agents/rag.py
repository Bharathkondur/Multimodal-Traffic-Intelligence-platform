"""
Retrieval-Augmented Generation (RAG) for detection events.

Provides semantic search and retrieval over detection events with support
for embeddings, time-aware filtering, and context management.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, List
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """Represents a single detection event."""
    timestamp: datetime
    detection_type: str  # vehicle, incident, hazard
    vehicle_type: Optional[str] = None
    location: str = "unknown"
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None
    text_representation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert detection to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.detection_type,
            "vehicle_type": self.vehicle_type,
            "location": self.location,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class DetectionDocument:
    """Document representation for RAG."""
    id: str
    content: str
    timestamp: datetime
    location: str
    detection_type: str
    metadata: dict = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "location": self.location,
            "type": self.detection_type,
            "metadata": self.metadata,
        }


class SimpleEmbedder:
    """
    Simple embedding model for demonstration.

    In production, use OpenAI embeddings, Ollama embeddings, or other
    sophisticated embedding models.
    """

    def __init__(self, dimension: int = 384):
        """Initialize embedder."""
        self.dimension = dimension
        logger.info(f"Initialized SimpleEmbedder with dimension={dimension}")

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        This is a mock implementation. In production, use:
        - OpenAI: OpenAIEmbeddings()
        - Ollama: OllamaEmbeddings(model="mistral")
        - HuggingFace: HuggingFaceEmbeddings()

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        # Create deterministic "embedding" based on text
        # In production, use real embedding models
        np.random.seed(hash(text) % (2**32))
        return np.random.randn(self.dimension).astype(np.float32)

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed multiple texts."""
        return [self.embed_text(text) for text in texts]


class FAISSIndex:
    """
    Simple in-memory FAISS-like index for demonstration.

    In production, use actual FAISS library:
    - pip install faiss-cpu  or  faiss-gpu
    - import faiss
    """

    def __init__(self, dimension: int = 384):
        """Initialize index."""
        self.dimension = dimension
        self.embeddings: List[np.ndarray] = []
        self.documents: List[DetectionDocument] = []
        logger.info(f"Initialized FAISSIndex with dimension={dimension}")

    def add(self, embedding: np.ndarray, document: DetectionDocument) -> None:
        """Add embedding and document to index."""
        if embedding.shape[0] != self.dimension:
            raise ValueError(
                f"Embedding dimension {embedding.shape[0]} "
                f"does not match index dimension {self.dimension}"
            )
        self.embeddings.append(embedding)
        self.documents.append(document)

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
    ) -> tuple[List[float], List[DetectionDocument]]:
        """
        Search for k nearest neighbors.

        Args:
            query_embedding: Query vector
            k: Number of results

        Returns:
            Tuple of (distances, documents)
        """
        if not self.embeddings:
            return [], []

        # Calculate cosine similarity
        similarities = []
        for emb in self.embeddings:
            # Normalize vectors
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
            emb_norm = emb / (np.linalg.norm(emb) + 1e-10)
            similarity = np.dot(query_norm, emb_norm)
            similarities.append(similarity)

        # Get top k indices
        top_indices = np.argsort(similarities)[-k:][::-1]
        top_similarities = [similarities[i] for i in top_indices]
        top_documents = [self.documents[i] for i in top_indices]

        return top_similarities, top_documents

    def clear(self) -> None:
        """Clear index."""
        self.embeddings = []
        self.documents = []


class DetectionRAG:
    """
    Retrieval-Augmented Generation over detection events.

    Enables semantic search, temporal filtering, and context-aware
    retrieval of detection events for the AI agent.

    Supports:
    - Semantic similarity search
    - Time-aware filtering (recent, time range)
    - Location-based filtering
    - Batch indexing and incremental updates
    - Context window management
    """

    def __init__(
        self,
        embedding_dim: int = 384,
        max_context_tokens: int = 8000,
        use_faiss: bool = False,
    ):
        """
        Initialize DetectionRAG.

        Args:
            embedding_dim: Embedding dimension
            max_context_tokens: Maximum context tokens for retrieval
            use_faiss: Whether to use actual FAISS (if available)
        """
        self.embedding_dim = embedding_dim
        self.max_context_tokens = max_context_tokens
        self.use_faiss = use_faiss

        # Initialize embedder
        self.embedder = SimpleEmbedder(dimension=embedding_dim)

        # Initialize index
        self.index = FAISSIndex(dimension=embedding_dim)

        # Metadata storage
        self.detections: List[DetectionDocument] = []
        self.doc_id_counter = 0

        logger.info(
            f"Initialized DetectionRAG: dim={embedding_dim}, "
            f"max_tokens={max_context_tokens}"
        )

    def add_detection(
        self,
        detection_type: str,
        content: str,
        timestamp: datetime,
        location: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Add a detection event to the RAG store.

        Args:
            detection_type: Type of detection (vehicle, incident, hazard)
            content: Text description of detection
            timestamp: Detection timestamp
            location: Detection location
            metadata: Additional metadata

        Returns:
            Document ID
        """
        doc_id = f"det_{self.doc_id_counter}"
        self.doc_id_counter += 1

        # Create document
        doc = DetectionDocument(
            id=doc_id,
            content=content,
            timestamp=timestamp,
            location=location,
            detection_type=detection_type,
            metadata=metadata or {},
        )

        # Generate embedding
        doc.embedding = self.embedder.embed_text(content)

        # Add to index
        self.index.add(doc.embedding, doc)
        self.detections.append(doc)

        logger.debug(f"Added detection: {doc_id}")
        return doc_id

    def add_batch(
        self,
        detections: List[dict[str, Any]],
    ) -> List[str]:
        """
        Add multiple detections in batch.

        Args:
            detections: List of detection dictionaries with keys:
                - detection_type: str
                - content: str
                - timestamp: datetime or str
                - location: str
                - metadata: dict (optional)

        Returns:
            List of document IDs
        """
        doc_ids = []
        for det in detections:
            timestamp = det.get("timestamp")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            doc_id = self.add_detection(
                detection_type=det["detection_type"],
                content=det["content"],
                timestamp=timestamp,
                location=det["location"],
                metadata=det.get("metadata"),
            )
            doc_ids.append(doc_id)

        return doc_ids

    def retrieve(
        self,
        query: str,
        k: int = 5,
        time_range: Optional[tuple[datetime, datetime]] = None,
        location_filter: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        """
        Retrieve relevant detections using semantic search.

        Args:
            query: Search query
            k: Number of results
            time_range: Optional (start_time, end_time) tuple
            location_filter: Optional location filter

        Returns:
            List of relevant detection documents
        """
        logger.info(
            f"Retrieving detections: query='{query}', k={k}, "
            f"time_range={time_range}, location={location_filter}"
        )

        # Generate query embedding
        query_embedding = self.embedder.embed_text(query)

        # Search index
        similarities, candidates = self.index.search(query_embedding, k=k * 2)

        # Filter by time range if provided
        if time_range:
            start_time, end_time = time_range
            candidates = [
                doc for doc in candidates
                if start_time <= doc.timestamp <= end_time
            ]

        # Filter by location if provided
        if location_filter:
            candidates = [
                doc for doc in candidates
                if location_filter.lower() in doc.location.lower()
            ]

        # Return top k results
        results = []
        for i, doc in enumerate(candidates[:k]):
            results.append({
                "id": doc.id,
                "content": doc.content,
                "timestamp": doc.timestamp.isoformat(),
                "location": doc.location,
                "type": doc.detection_type,
                "relevance_score": float(similarities[i]) if i < len(similarities) else 0.0,
                "metadata": doc.metadata,
            })

        return results

    def retrieve_recent(
        self,
        hours: int = 1,
        detection_type: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict[str, Any]]:
        """
        Retrieve recent detections.

        Args:
            hours: Look back this many hours
            detection_type: Optional filter by type
            location: Optional location filter
            limit: Maximum results

        Returns:
            List of recent detections
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        results = []
        for doc in reversed(self.detections):  # Most recent first
            if doc.timestamp < cutoff_time:
                continue

            if detection_type and doc.detection_type != detection_type:
                continue

            if location and location.lower() not in doc.location.lower():
                continue

            results.append(doc.to_dict())

            if len(results) >= limit:
                break

        return results

    def retrieve_by_location(
        self,
        location: str,
        hours: int = 24,
        limit: int = 20,
    ) -> List[dict[str, Any]]:
        """
        Retrieve detections from a specific location.

        Args:
            location: Location to filter by
            hours: Time range in hours
            limit: Maximum results

        Returns:
            List of detections at location
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        results = []
        for doc in reversed(self.detections):
            if doc.timestamp < cutoff_time:
                continue

            if location.lower() not in doc.location.lower():
                continue

            results.append(doc.to_dict())

            if len(results) >= limit:
                break

        return results

    def retrieve_incidents(
        self,
        hours: int = 1,
        severity: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        """
        Retrieve incident detections.

        Args:
            hours: Time range in hours
            severity: Optional severity filter

        Returns:
            List of incident detections
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        results = []
        for doc in reversed(self.detections):
            if doc.timestamp < cutoff_time:
                continue

            if doc.detection_type != "incident":
                continue

            # Check severity if specified
            if severity and doc.metadata.get("severity") != severity:
                continue

            results.append(doc.to_dict())

        return results

    def get_context(
        self,
        query: str,
        k: int = 5,
    ) -> str:
        """
        Get formatted context string for LLM.

        Retrieves relevant documents and formats them for inclusion
        in LLM context window with token management.

        Args:
            query: Search query
            k: Number of documents to retrieve

        Returns:
            Formatted context string
        """
        results = self.retrieve(query, k=k)

        if not results:
            return "No relevant detection events found in the database."

        context = "## Relevant Detection Events\n\n"
        token_count = 0

        for result in results:
            doc_text = (
                f"**{result['type'].upper()}** ({result['location']}) "
                f"at {result['timestamp']}\n"
                f"Relevance: {result['relevance_score']:.2%}\n"
                f"{result['content']}\n\n"
            )

            # Estimate tokens (roughly 1 token per 4 characters)
            token_count += len(doc_text) // 4

            if token_count > self.max_context_tokens:
                logger.warning(
                    f"Context window exceeded ({token_count} tokens), "
                    "truncating results"
                )
                break

            context += doc_text

        return context

    def clear(self) -> None:
        """Clear all stored detections and index."""
        self.index.clear()
        self.detections = []
        self.doc_id_counter = 0
        logger.info("Cleared DetectionRAG")

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about stored detections."""
        if not self.detections:
            return {
                "total_documents": 0,
                "detection_types": {},
                "locations": {},
                "time_range": None,
            }

        detection_types = {}
        locations = {}

        for doc in self.detections:
            detection_types[doc.detection_type] = \
                detection_types.get(doc.detection_type, 0) + 1
            locations[doc.location] = \
                locations.get(doc.location, 0) + 1

        timestamps = [doc.timestamp for doc in self.detections]

        return {
            "total_documents": len(self.detections),
            "detection_types": detection_types,
            "locations": locations,
            "time_range": {
                "earliest": min(timestamps).isoformat(),
                "latest": max(timestamps).isoformat(),
            },
            "index_size": len(self.index.embeddings),
        }
