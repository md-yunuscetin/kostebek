from pytrends.request import TrendReq
from src.utils.logger import get_logger

logger = get_logger("gtrends_tools")

def get_trend_score(keyword: str) -> int:
    """Belirli bir anahtar kelime için Google Trends üzerinden 0-100 arası trend puanı döner."""
    try:
        pytrends = TrendReq(hl='en-US', tz=180)  # Türkiye saati / Genel dil İngilizce
        # Trendleri son 3 ay icerisinde arar
        pytrends.build_payload([keyword], timeframe='today 3-m')
        data = pytrends.interest_over_time()
        
        if data.empty:
            return 0
            
        # Ortalama trend ilgisini döndür
        return int(data[keyword].mean())
    except Exception as e:
        logger.warning(f"Google Trends hatası ({keyword}): {e}. Puan: 0 varsayılıyor.")
        return 0
