import os
import logging
import urllib.parse
import threading
import http.server
import socketserver
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

# Ekdam accurate aur tested search URLs
SITES = [
    {"name": "Amazon", "search_url": "https://www.amazon.in/s?k={query}", "emoji": "📦"},
    {"name": "Flipkart", "search_url": "https://www.flipkart.com/search?q={query}", "emoji": "🛍️"},
    {"name": "Croma", "search_url": "https://www.croma.com/search/?text={query}", "emoji": "🔌"},
    {"name": "Reliance Digital", "search_url": "https://www.reliancedigital.in/search?q={query}", "emoji": "⚡"},
]

def run_dummy_server():
    port = int(os.getenv("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        logger.info(f"Dummy server running on port {port}")
        httpd.serve_forever()

async def search_product(update, context):
    user_query = update.message.text
    
    # URL encoding ko sahi karne ke liye standard urllib use kiya hai
    encoded_query = urllib.parse.quote_plus(user_query)
    
    msg = f"🔍 **Live Deals for: {user_query}**\n\n"
    msg += "Niche diye gaye links par click karein, yeh aapko seedhe product search page par le jayenge:\n\n"
    
    for site in SITES:
        link = site["search_url"].format(query=encoded_query)
        msg += f"{site['emoji']} **{site['name']}**:\n👉 [Open {site['name']} Search Results]({link})\n\n"
        
    msg += "💡 _Tip: Agar aapke phone mein inke official apps hain, toh link par click karte hi direct app mein sahi product page khul jayega!_"
    
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def start(update, context):
    await update.message.reply_text("🛍️ Welcome to Sasta Deal Guru!\nSend me any product name.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN nahi mila!")
        
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
