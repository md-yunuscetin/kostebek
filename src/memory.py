import os
from src.utils.logger import get_logger

logger = get_logger("memory_store")

def get_store():
    """LangGraph Store (Redis veya Local Memory) döner."""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from langgraph.store.redis import RedisStore
            store = RedisStore.from_conn_string(redis_url)
            logger.info("✅ RedisStore başarıyla bağlandı.")
            return store
        except Exception as e:
            logger.error(f"RedisStore bağlantı hatası: {e}. Yerel belleğe düşülüyor.")
    
    # Fallback to InMemoryStore if Redis is not available
    from langgraph.store.memory import InMemoryStore
    logger.info("⚠️ REDIS_URL bulunamadı veya bağlanılamadı. InMemoryStore kullanılıyor.")
    return InMemoryStore()

# Global store instance
store = get_store()
