import os
import logging
import urllib.parse
import threading
import http.server
import socketserver
import json
import asyncio
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None

# Free local database file path
ALERT_FILE = "alerts.json"

def load_alerts():
    if os.path.exists(ALERT_FILE):
        try:
            with open(ALERT_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_alerts(alerts):
    with open(ALERT_FILE, "w") as f:
        json.dump(alerts, f)

async def check_prices_background(app):
    """Yeh function har 1 ghante mein piche se khud chalega bina paise diye"""
    while True:
        await asyncio.sleep(3600) # Har 1 ghante (3600 seconds) mein check karega
        alerts = load_alerts()
        if not alerts or not model:
            continue
            
        logger.info("Background auto-price check running...")
        for chat_id, user_alerts in list(alerts.items()):
            for item, target_price in list(user_alerts.items()):
                prompt = f"What is the typical lowest current grocery price in INR for '{item}' across Zepto/Blinkit right now? Return ONLY the number."
                try:
                    response = model.generate_content(prompt)
                    current_price = float(re.sub(r'[^\d.]', '', response.text.strip()))
                    
                    if current_price <= target_price:
                        # Price kam hote hi Notification bhejega
                        msg = f"🚨 **FREE PRICE ALERT!**\n\n💰 **{item}** ka price kam ho gaya hai!\n"
                        msg += f"📉 Aapka Target: ₹{target_price}\n🔥 Live Price: ₹{current_price}\n\n"
                        msg += f"Turant check karein!"
                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                        
                        # Ek baar alert bhejne ke baad delete kar dega taaki baar-baar disturb na kare
                        del alerts[chat_id][item]
                        save_alerts(alerts)
                except Exception as e:
                    logger.error(f"Auto-check failed for {item}: {e}")

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User command: /setalert milk, 30"""
    chat_id = str(update.effective_chat.id)
    try:
        # Command ke baad ka text nikalne ke liye
        args = " ".join(context.args).split(",")
        if len(args) < 2:
            await update.message.reply_text("❌ Galat tarika! Aise likhein:\n`/setalert milk, 30`", parse_mode="Markdown")
            return
            
        item = args[0].strip()
        target_price = float(args[1].strip())
        
        alerts = load_alerts()
        if chat_id not in alerts:
            alerts[chat_id] = {}
        alerts[chat_id][item] = target_price
        save_alerts(alerts)
        
        await update.message.reply_text(f"✅ **Alert Set Ho Gaya!**\n\n🛒 Item: {item}\n📉 Target Price: ₹{target_price}\n\nJaise hi price isse kam hoga, main notification bhej dunga!")
    except Exception as e:
        await update.message.reply_text("❌ Kuch error aaya. Format check karein: `/setalert milk, 30`")

async def search_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Purana search logic waise hi chalega jab aap normal text bhejenge
    user_query = update.message.text
    await update.message.reply_text(f"🔄 Looking for {user_query}...")
    # (Baki search formatting code)
    await update.message.reply_text(f"🔍 Here are the links for {user_query}. You can also set an auto-alert using `/setalert {user_query}, 40`")

def run_dummy_server():
    port = int(os.getenv("PORT", 8080))
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("setalert", set_alert))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    
    # Background automation loop start karne ke liye
    loop = asyncio.get_event_loop()
    loop.create_task(check_prices_background(app))
    
    app.run_polling()

if __name__ == "__main__":
    main()
