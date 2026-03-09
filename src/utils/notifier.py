import os
import requests
from src.utils.logger import get_logger

logger = get_logger("notifier")

def send_telegram_alert(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("Telegram Bot Token veya Chat ID bulunamadı, bildirim atlandı.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram bildirimi başarıyla gönderildi.")
            return True
        else:
            logger.error(f"Telegram API hatası: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram bildirimi gönderilirken hata oluştu: {e}")
        return False
