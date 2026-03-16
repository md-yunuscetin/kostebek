import os
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler
from src.utils.logger import get_logger

logger = get_logger("telegram_gate")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

async def ask_via_telegram(message: str, options: list[str]) -> str:
    """Kullanıcıya Telegram'dan butonlu mesaj yollar ve cevabı (callback_data) bekler."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("[TELEGRAM] Token veya Chat ID eksik! Otomatik olarak 'reject' dönülüyor.")
        return "reject"

    bot = Bot(token=BOT_TOKEN)

    # Inline Butonları (Örn: approve, reject) oluştur
    keyboard = [[InlineKeyboardButton(opt.upper(), callback_data=opt)] for opt in options]
    markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=message,
            reply_markup=markup, 
            parse_mode="Markdown"
        )
        logger.info(f"[TELEGRAM] Onay mesajı gönderildi: {message[:30]}...")
    except Exception as e:
        logger.error(f"[TELEGRAM] Mesaj gönderilemedi: {e}")
        return "reject"

    # Cevap bekleniyor... Event looper.
    response_event = asyncio.Event()
    user_choice = {}

    async def callback_handler(update: Update, context):
        query = update.callback_query
        await query.answer() # Tıklama sonrası butondaki yükleniyor dönmesini bitir
        user_choice["value"] = query.data
        logger.info(f"[TELEGRAM] Kullanıcı seçimi alındı: {query.data}")
        response_event.set()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(callback_handler))

    try:
        async with app:
            await app.start()
            await app.updater.start_polling() # Polling'i manuel başlat
            logger.info("[TELEGRAM] Cevap bekleniyor (Timeout: 1 saat)...")
            # 1 saat boyunca insanın telefona veya bilgisayara bakıp onaylamasını bekle
            await asyncio.wait_for(response_event.wait(), timeout=3600)  
            await app.updater.stop() # Polling'i durdur
            await app.stop()
    except asyncio.TimeoutError:
        logger.warning("[TELEGRAM] 1 saat geçti, cevap verilmedi. Otomatik Red.")
        return "reject"
    except Exception as e:
        logger.error(f"[TELEGRAM] Polling hatası: {e}")
        return "reject"

    return user_choice.get("value", "reject")

async def send_telegram_notification(message: str):
    """Kullanıcıya Telegram'dan sadece bilgi mesajı yollar (onay beklemez)."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("[TELEGRAM] Token veya Chat ID eksik! Bildirim atılamadı.")
        return

    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=CHAT_ID, 
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"[TELEGRAM] Bildirim gönderildi: {message[:30]}...")
    except Exception as e:
        logger.error(f"[TELEGRAM] Bildirim gönderilemedi: {e}")
        from io import BytesIO  # en üstteki import'lara EKLE

...

async def send_telegram_report_document(filename: str, content: str):
    """
    Tam raporu Telegram'a .md dosyası olarak yollar.
    filename: 'kostebek-2026-03-16.md' gibi.
    content:  Markdown raporunun tam metni.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("[TELEGRAM] Token veya Chat ID eksik! Rapor gönderilemedi.")
        return

    bot = Bot(token=BOT_TOKEN)

    try:
        data = content.encode("utf-8")
        f = BytesIO(data)
        f.name = filename

        await bot.send_document(
            chat_id=CHAT_ID,
            document=f,
            caption="📄 Günlük Köstebek Raporu"
        )
        logger.info(f"[TELEGRAM] Rapor dokümanı gönderildi: {filename}")
    except Exception as e:
        logger.error(f"[TELEGRAM] Rapor dokümanı gönderilemedi: {e}")


