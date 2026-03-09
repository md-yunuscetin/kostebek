
import os
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

async def test_telegram():
    if not BOT_TOKEN or not CHAT_ID:
        print("Token or Chat ID missing")
        return

    print(f"Testing with Token: {BOT_TOKEN[:10]}... and Chat ID: {CHAT_ID}")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    response_event = asyncio.Event()
    
    async def callback_handler(update: Update, context):
        query = update.callback_query
        print(f"RECEIVED CALLBACK: {query.data}")
        await query.answer(text=f"Received: {query.data}")
        response_event.set()

    app.add_handler(CallbackQueryHandler(callback_handler))

    keyboard = [[InlineKeyboardButton("APPROVE", callback_data="approve"), 
                 InlineKeyboardButton("REJECT", callback_data="reject")]]
    markup = InlineKeyboardMarkup(keyboard)

    async with app:
        await app.bot.send_message(chat_id=CHAT_ID, text="TEST MESSAGE: Click a button!", reply_markup=markup)
        print("Message sent. Waiting for polling...")
        
        # v20+ requires manual polling start if using 'async with app'
        await app.updater.start_polling()
        print("Polling started. Please click a button in Telegram.")
        
        try:
            await asyncio.wait_for(response_event.wait(), timeout=30)
            print("Event SET! Success.")
        except asyncio.TimeoutError:
            print("Timeout waiting for button click.")
        finally:
            await app.updater.stop()
            await app.stop()

if __name__ == "__main__":
    asyncio.run(test_telegram())
