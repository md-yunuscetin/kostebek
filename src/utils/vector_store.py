import os
import hashlib
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

from src.models import IdeaDraft
from src.utils.logger import get_logger
from src.utils.config_loader import config

logger = get_logger("vector_store")
load_dotenv()

# GEMINI_API_KEY environment variable üzerinden alınır
api_key = os.getenv("GEMINI_API_KEY")

class VectorStoreManager:
    """ChromaDB tabanlı Vektörel Hafıza Yöneticisi (Agentic RAG)"""
    
    def __init__(self, persist_directory="./data/vector_store"):
        self.persist_directory = persist_directory
        
        # Eğer data dizini yoksa oluştur
        os.makedirs(self.persist_directory, exist_ok=True)
        
        try:
            # ChromaDB yerel PersistentClient'ı başlatılıyor
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            
            # Gemini Embedding Function
            if not api_key:
                logger.error("[VECTOR DB] GEMINI_API_KEY tanımlanmamış. Vektörel işlemler başarısız olacak.")
            
            self.embedding_function = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
                api_key=api_key
            )
            
            # business_ideas koleksiyonu (Yoksa yarat, varsa getir)
            self.collection = self.client.get_or_create_collection(
                name="business_ideas",
                embedding_function=self.embedding_function
            )
            logger.info(f"[VECTOR DB] ChromaDB başarıyla başlatıldı. Store path: {self.persist_directory}")
            
        except Exception as e:
            logger.error(f"[VECTOR DB] Başlatma Hatası: {str(e)}")
            self.client = None

    def save_idea(self, idea: IdeaDraft, final_score: int):
        """Onaylanan fikri ChromaDB'ye vektörel olarak gömer."""
        if not self.client:
            return False
            
        try:
            # Benzersiz ID oluştur
            idea_id = hashlib.md5(idea.title.encode("utf-8")).hexdigest()
            
            # Fikrden anlamlı bir özet/bağlam metni çıkar
            text_content = f"Başlık: {idea.title}\nProblem: {idea.problem}\nÇözüm: {idea.solution}\nWedge: {idea.wedge}\nHedef Kitle: {idea.target_audience}"
            
            # Etiketler için kaynakların listesini virgülle birleştir
            source_urls_str = ",".join(idea.source_urls) if idea.source_urls else "unknown"
            
            metadata = {
                "score": final_score,
                "date": datetime.now().isoformat(),
                "source": source_urls_str,
                "target_audience": idea.target_audience
            }
            
            # Opsiyonel Trend Score ekleme
            if idea.trend_score is not None:
                metadata["trend_score"] = idea.trend_score
            
            self.collection.add(
                documents=[text_content],
                metadatas=[metadata],
                ids=[idea_id]
            )
            logger.info(f"[VECTOR DB] Yeni fikir gömüldü: {idea.title} (ID: {idea_id})")
            return True
            
        except Exception as e:
            logger.error(f"[VECTOR DB] Fikir kaydetme hatası: {str(e)}")
            return False

    def find_similar_past_ideas(self, query_text: str, threshold: float = None, limit: int = 3) -> bool:
        """
        Geçmişte benzer bir fikir üretilip üretilmediğini kontrol eder.
        Dönen skora göre kopya eşiğini test eder.
        """
        if threshold is None:
            threshold = config.get("guard", {}).get("similarity_threshold", 0.97)
        if not self.client:
            return False # DB yoksa kontrol passed (kopya yok sayılır)
            
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=limit
            )
            
            # Eğer koleksiyon boşsa dict içinde distances key'i boş liste gelir
            if not results or "distances" not in results or not results["distances"]:
                return False
                
            distances = results["distances"][0]
            
            if not distances:
                return False
                
            # Cosine Mesafe (Chroma L2 döner ama Gemini text embeddings için mesafe kontrolü yapılır)
            # Distance 0'a ne kadar yakınsa, o kadar benzer demektir. (1 - distance) benzerlik skorudur.
            # Dolayısıyla 0.15'ten küçük L2 distance demek (1 - 0.15 = 0.85) %85 benzerlik demektir.
            is_duplicate = False
            for dist in distances:
                # L2 distance olduğu için, eşik genelde 0.3 altı "çok benzer" kabul edilir.
                # Threshold (0.85) kullanıcının belirttiği metoti. Distance karşılığı kabaca:
                similarity_score = 1 - (dist / 2.0) if dist <= 2.0 else 0 
                
                if similarity_score >= threshold:
                    is_duplicate = True
                    logger.warning(f"[VECTOR DB] Kopya Fikir Tespit Edildi! (Benzerlik Skoru: {similarity_score:.2f})")
                    break
                    
            return is_duplicate
            
        except Exception as e:
            logger.error(f"[VECTOR DB] Benzerlik sorgulama hatası: {str(e)}")
            return False

# Tekil bir instance oluşturup dışa aktar
vector_store = VectorStoreManager()
