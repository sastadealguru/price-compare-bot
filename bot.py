import os
import urllib.parse
import threading
import http.server
import socketserver
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Top Indian E-commerce Sites ka Accurate Search Path
SITES = [
    {"name": "Amazon", "url": "https://www.amazon.in/s?k={q}"},
    {"name": "Flipkart", "url": "https://www.flipkart.com/search?q={q}"},
    {"name": "Croma", "url": "https://www.croma.com/search/?text={q}"},
    {"name": "Reliance", "url": "https://www.reliancedigital.in/search?q={q}"},
    {"name": "eBay", "url": "https://www.ebay.com/sch/i.html?_nkw={q}"},
]

def run_dummy_server():
    port = int(os.getenv("PORT", 8080))
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

async def get_deals(update, context):
    query = update.message.text
    encoded = urllib.parse.quote_plus(query)
    
    msg = f"🏆 **Deals for: {query}**\n\n"
    for site in SITES:
        link = site["url"].format(q=encoded)
        msg += f"🔹 **{site['name']}**: [Click to check price]({link})\n\n"
        
    msg += "⚠️ _Price dikhane ke liye scraping ki zaroorat hoti hai jo ye sites block karti hain. In links par click karke aap direct live price dekh sakte hain._"
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_deals))
    app.run_polling()

if __name__ == "__main__":
    main()
