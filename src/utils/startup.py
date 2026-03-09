import os
import redis
import sys
from src.utils.logger import get_logger

logger = get_logger("startup")

def check_redis_connection(url: str = None) -> bool:
    """Windows üzerinde Memurai veya Bulut üzerinde Redis bağlantısını kontrol eder."""
    if url is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis.from_url(url)
        r.ping()
        logger.info("✅ Redis (Memurai) bağlantısı başarılı. V8 Memory Engine devrede.")
        return True
    except redis.ConnectionError:
        logger.critical(
            "❌ Redis (Memory Saver) bağlantısı kurulamadı!\n"
            "V8 ajan mimarisi State ve Memory Checkpoint için Redis gerektiriyor.\n"
            "Memurai kurulu değilse: https://www.memurai.com/get-memurai\n"
            "Kuruluysa: Windows Services > Memurai (veya redis-server) start edildiğinden emin olun."
        )
        sys.exit(1)
