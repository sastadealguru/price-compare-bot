import os
import logging
import urllib.parse
import threading
import http.server
import socketserver
import json
import re
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

# Sabhi platforms jo Grocery aur Electronics dono check karenge
ALL_SITES = [
    {"name": "Amazon", "url": "https://www.amazon.in/s?k={q}", "emoji": "📦"},
    {"name": "Flipkart", "url": "https://www.flipkart.com/search?q={q}", "emoji": "🛍️"},
    {"name": "JioMart", "url": "https://www.jiomart.com/search/{q}", "emoji": "🏪"},
    {"name": "Blinkit", "url": "https://blinkit.com/s/?q={q}", "emoji": "🥛"},
    {"name": "Zepto", "url": "https://www.zeptonow.com/search?q={q}", "emoji": "⚡"},
    {"name": "Croma", "url": "https://www.croma.com/search/?text={q}", "emoji": "🔌"},
    {"name": "Reliance Digital", "url": "https://www.reliancedigital.in/search?q={q}", "emoji": "⚡"},
    {"name": "Swiggy Instamart", "url": "https://www.swiggy.com/instamart/search?q={q}", "emoji": "🛒"},
    {"name": "Snapdeal", "url": "https://www.snapdeal.com/search?keyword={q}", "emoji": "💥"},
    {"name": "eBay", "url": "https://www.ebay.com/sch/i.html?_nkw={q}", "emoji": "🌍"}
]

async def get_prices_and_offers_from_gemini(query):
    if not model:
        return []
    prompt = f"""
    Act as an Indian shopping expert. For the item '{query}', provide the typical current online selling price (in INR) and any ongoing bank/discount offers across these apps: Amazon, Flipkart, JioMart, Blinkit, Zepto, Croma, Reliance Digital, Swiggy Instamart, Snapdeal, eBay.
    Only return a clean JSON array of objects with keys 'site', 'price' (numerical value only), 'title', and 'offer' (short text about bank/discount offer, or "No offer").
    Example: [{{"site": "Amazon", "price": 45000, "title": "Product Name", "offer": "10% off on SBI Cards"}}]
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error(f"Gemini payload failed: {e}")
    return []

async def handle_user_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    
    # User agar price reply kar rha hai alert ke liye
    if context.user_data.get('waiting_for_price'):
        try:
            target_price = float(re.sub(r'[^\d.]', '', user_msg))
            pending_item = context.user_data.get('pending_item')
            
            alerts = load_alerts()
            if chat_id not in alerts:
                alerts[chat_id] = {}
            alerts[chat_id][pending_item] = target_price
            save_alerts(alerts)
            
            context.user_data['waiting_for_price'] = False
            await update.message.reply_text(f"✅ **Alert Set Ho Gaya!**\n\n🛒 Item: {pending_item}\n📉 Target Price: ₹{target_price}\n\nJaise hi price isse kam hoga, main notification bhej dunga!")
            return
        except ValueError:
            await update.message.reply_text("❌ Please sirf ek valid price (number) likhein. Jaise: 40000")
            return

    # Normal Search Process
    await update.message.reply_text(f"🔍 Searching grocery & electronics platforms for '{user_msg}'...")
    encoded_query = urllib.parse.quote_plus(user_msg)
    raw_deals = await get_prices_and_offers_from_gemini(user_msg)
    
    # Sort Low to High
    if raw_deals:
        raw_deals.sort(key=lambda x: x.get('price', 999999))
        
    returned_sites = {d['site'].lower(): d for d in raw_deals if 'site' in d}
    
    msg = f"🏆 **Price & Offer Comparison for: {user_msg}**\n*(🔥 Sasta Sabse Upar)*\n\n"
    
    idx = 1
    for site in ALL_SITES:
        site_key = site["name"].lower()
        match_key = "flipkart" if "flipkart" in site_key else "amazon" if "amazon" in site_key else site_key
        
        deal = None
        for k, v in returned_sites.items():
            if match_key in k:
                deal = v
                break
                
        link = site["url"].format(q=encoded_query)
        if deal:
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🔹"
            msg += f"{medal} **{site['name']}**: ₹{deal['price']:,}\n"
            msg += f" 📋 _{deal['title']}_\n"
            msg += f" 🎁 **Offer**: {deal.get('offer', 'No offer')}\n"
            msg += f" 👉 [Open Search Results]({link})\n\n"
            idx += 1
        else:
            msg += f"🔹 **{site['name']}**:\n"
            msg += f" 👉 [Check Live Price & Offers]({link})\n\n"
            
    msg += "───────────────────\n"
    msg += f"🤔 **Aapko yeh '{user_msg}' kitne tak mein chahiye?**\n"
    msg += "Neeche reply mein bas apna target price (number) likh dein, main alert set kar dunga! (e.g. 500)"
    
    context.user_data['waiting_for_price'] = True
    context.user_data['pending_item'] = user_msg
    
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def check_prices_background(app):
    while True:
        await asyncio.sleep(3600) # Check every hour
        alerts = load_alerts()
        if not alerts or not model:
            continue
            
        for chat_id, user_alerts in list(alerts.items()):
            for item, target_price in list(user_alerts.items()):
                prompt = f"What is the typical lowest current price in INR for '{item}' online? Return ONLY the number."
                try:
                    response = model.generate_content(prompt)
                    current_price = float(re.sub(r'[^\d.]', '', response.text.strip()))
                    
                    if current_price <= target_price:
                        msg = f"🚨 **PRICE DROP ALERT!**\n\n💰 **{item}** aapke budget mein aa gaya hai!\n"
                        msg += f"📉 Aapka Target: ₹{target_price}\n🔥 Live Price: ₹{current_price}\n\nCheck default store apps now!"
                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                        del alerts[chat_id][item]
                        save_alerts(alerts)
                except Exception as e:
                    logger.error(f"Background check failed: {e}")

def run_dummy_server():
    port = int(os.getenv("PORT", 8080))
    with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_msg))
    
    loop = asyncio.get_event_loop()
    loop.create_task(check_prices_background(app))
    app.run_polling()

if __name__ == "__main__":
    main()
