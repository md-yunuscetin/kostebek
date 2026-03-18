import os
import hashlib
from datetime import datetime
from typing import Optional, List

import chromadb
from dotenv import load_dotenv
from google import genai

try:
    from chromadb import Documents, EmbeddingFunction, Embeddings
except Exception:
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from src.models import IdeaDraft
from src.utils.logger import get_logger
from src.utils.config_loader import config

logger = get_logger("vector_store")
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")


class GeminiGenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, api_key: str, model_name: str = "gemini-embedding-001"):
        if not api_key:
            raise ValueError("GEMINI_API_KEY tanımlı değil")
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def __call__(self, input: Documents) -> Embeddings:
        texts = [str(x) if x is not None else "" for x in input]
        if not texts:
            return []

        response = self.client.models.embed_content(
            model=self.model_name,
            contents=texts,
        )

        vectors: List[List[float]] = []
        for emb in response.embeddings:
            values = getattr(emb, "values", None)
            if values is None and isinstance(emb, dict):
                values = emb.get("values", [])
            vectors.append([float(v) for v in values])

        return vectors


class VectorStoreManager:
    """ChromaDB tabanlı Vektörel Hafıza Yöneticisi"""

    def __init__(self, persist_directory: str = "./data/vector_store"):
        self.persist_directory = persist_directory
        self.client: Optional[chromadb.PersistentClient] = None
        self.collection = None
        self.embedding_function = None

        os.makedirs(self.persist_directory, exist_ok=True)

        try:
            self.client = chromadb.PersistentClient(path=self.persist_directory)

            if not api_key:
                logger.error(
                    "[VECTOR DB] GEMINI_API_KEY tanımlanmamış. Vektörel işlemler devre dışı."
                )
                return

            self.embedding_function = GeminiGenAIEmbeddingFunction(
                api_key=api_key,
                model_name="gemini-embedding-001",
            )

            logger.info(
                f"[VECTOR DB DEBUG] embedding_function_class={type(self.embedding_function).__name__}"
            )
            logger.info(
                f"[VECTOR DB DEBUG] embedding_model={self.embedding_function.model_name}"
            )

            self.collection = self.client.get_or_create_collection(
                name="business_ideas",
                embedding_function=self.embedding_function,
            )

            logger.info(
                f"[VECTOR DB] ChromaDB başarıyla başlatıldı. Store path: {self.persist_directory}"
            )

        except Exception as e:
            logger.error(f"[VECTOR DB] Başlatma Hatası: {str(e)}")
            self.client = None
            self.collection = None
            self.embedding_function = None

    def save_idea(self, idea: IdeaDraft, final_score: int) -> bool:
        if not self.client or not self.collection:
            return False

        try:
            raw_id = f"{idea.title}|{idea.problem}|{idea.target_audience}"
            idea_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()

            text_content = (
                f"Başlık: {idea.title}\n"
                f"Problem: {idea.problem}\n"
                f"Çözüm: {idea.solution}\n"
                f"Wedge: {idea.wedge}\n"
                f"Hedef Kitle: {idea.target_audience}"
            )

            source_urls_str = ",".join(idea.source_urls) if idea.source_urls else "unknown"

            metadata = {
                "score": int(final_score),
                "date": datetime.now().isoformat(),
                "source": source_urls_str,
                "target_audience": str(idea.target_audience or ""),
                "title": str(idea.title or ""),
            }

            if idea.trend_score is not None:
                metadata["trend_score"] = float(idea.trend_score)

            existing = self.collection.get(ids=[idea_id])
            existing_ids = existing.get("ids", []) if isinstance(existing, dict) else []

            if existing_ids:
                self.collection.update(
                    ids=[idea_id],
                    documents=[text_content],
                    metadatas=[metadata],
                )
                logger.info(f"[VECTOR DB] Fikir güncellendi: {idea.title} (ID: {idea_id})")
            else:
                self.collection.add(
                    ids=[idea_id],
                    documents=[text_content],
                    metadatas=[metadata],
                )
                logger.info(f"[VECTOR DB] Yeni fikir gömüldü: {idea.title} (ID: {idea_id})")

            return True

        except Exception as e:
            logger.error(f"[VECTOR DB] Fikir kaydetme hatası: {str(e)}")
            return False

    def find_similar_past_ideas(
        self,
        query_text: str,
        threshold: float = None,
        limit: int = 3
    ) -> bool:
        if threshold is None:
            threshold = config.get("guard", {}).get("similarity_threshold", 0.97)

        if not self.client or not self.collection:
            return False

        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=limit,
            )

            if not results or "distances" not in results or not results["distances"]:
                return False

            distances = results["distances"][0]
            if not distances:
                return False

            for dist in distances:
                try:
                    dist = float(dist)
                except Exception:
                    continue

                similarity_score = 1 - (dist / 2.0) if dist <= 2.0 else 0.0

                if similarity_score >= threshold:
                    logger.warning(
                        f"[VECTOR DB] Kopya Fikir Tespit Edildi! (Benzerlik Skoru: {similarity_score:.2f})"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"[VECTOR DB] Benzerlik sorgulama hatası: {str(e)}")
            return False


vector_store = VectorStoreManager()
