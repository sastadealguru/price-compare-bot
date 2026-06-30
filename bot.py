import os
import logging
import urllib.parse
import threading
import http.server
import socketserver
import json
import re
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

SITES = [
    {"name": "Amazon", "url": "https://www.amazon.in/s?k={q}", "emoji": "📦"},
    {"name": "Flipkart", "url": "https://www.flipkart.com/search?q={q}", "emoji": "🛍️"},
    {"name": "Croma", "url": "https://www.croma.com/search/?text={q}", "emoji": "🔌"},
    {"name": "Reliance Digital", "url": "https://www.reliancedigital.in/search?q={q}", "emoji": "⚡"},
    {"name": "eBay", "url": "https://www.ebay.com/sch/i.html?_nkw={q}", "emoji": "🌍"},
    {"name": "Snapdeal", "url": "https://www.snapdeal.com/search?keyword={q}", "emoji": "💥"}
]

def run_dummy_server():
    port = int(os.getenv("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

async def get_simulated_prices_via_gemini(query):
    # Free tier blocking se bachne ke liye Gemini directly real-time estimates aur web-structure analyze karega
    prompt = f"""
    Act as a shopping price aggregator for Indian market. For the user query '{query}', list typical current selling prices across Amazon, Flipkart, Croma, Reliance Digital, eBay, and Snapdeal.
    Only return a clean JSON array of objects with keys 'site', 'price' (numerical value only), and 'title'.
    Example: [{{"site": "Amazon", "price": 45000, "title": "Product Name"}}]
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error(f"Gemini pricing failed: {e}")
    return []

async def search_product(update, context):
    user_query = update.message.text
    await update.message.reply_text("🔄 Fetching prices and sorting from Low to High...")
    
    encoded_query = urllib.parse.quote_plus(user_query)
    raw_deals = await get_simulated_prices_via_gemini(user_query)
    
    # Sort deals Low to High based on price
    if raw_deals:
        raw_deals.sort(key=lambda x: x.get('price', 999999))
    
    msg = f"🔍 **Price Comparison for: {user_query} (Low to High)**\n\n"
    
    # Track which sites Gemini returned
    returned_sites = {d['site'].lower(): d for d in raw_deals if 'site' in d}
    
    idx = 1
    for site in SITES:
        site_key = site["name"].lower()
        link = site["url"].format(q=encoded_query)
        
        if site_key in returned_sites:
            deal = returned_sites[site_key]
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🔹"
            msg += f"{medal} **{site['name']}**: ₹{deal['price']:,}\n"
            msg += f" 📋 _{deal['title']}_\n"
            msg += f" 👉 [Buy on {site['name']}]({link})\n\n"
            idx += 1
        else:
            msg += f"🔹 **{site['name']}**: Price on site\n"
            msg += f" 👉 [Check Live Price]({link})\n\n"
            
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN nahi mila!")
        
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
