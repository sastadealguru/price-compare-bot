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
    Only return a clean JSON array of objects with keys 'site', 'price' (numerical value only), 'title', and 'offer'.
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
    
    # Check if the message is JUST a number (e.g., "20" or "450")
    if re.match(r'^\d+$', user_msg):
        pending_item = context.user_data.get('pending_item')
        
        if pending_item:
            target_price = float(user_msg)
            alerts = load_alerts()
            if chat_id not in alerts:
                alerts[chat_id] = {}
            alerts[chat_id][pending_item] = target_price
            save_alerts(alerts)
            
            # Clear the context state
            context.user_data['pending_item'] = None
            
            await update.message.reply_text(f"✅ **Alert Set Ho Gaya!**\n\n🛒 Item: {pending_item}\n📉 Target Price: ₹{target_price}\n\nJaise hi price isse kam hoga, main aapko automatic bta dunga!")
            return
        else:
            await update.message.reply_text("❌ Pehle kisi product ka naam likhein (jaise: Milk), uske baad price set karein.")
            return

    # Normal Product Search
    await update.message.reply_text(f"🔍 Searching grocery & electronics platforms for '{user_msg}'...")
    encoded_query = urllib.parse.quote_plus(user_msg)
    raw_deals = await get_prices_and_offers_from_gemini(user_msg)
    
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
            msg += f" 👉 [Check Live Price]({link})\n\n"
            
    msg += "───────────────────\n"
    msg += f"🤔 **Aapko yeh '{user_msg}' kitne rupaye mein chahiye?**\n"
    msg += "Neeche reply mein bas woh number (price) likh dijiye, koi command nahi lagani! (e.g. 35)"
    
    # Save the item name in bot memory for this user
    context.user_data['pending_item'] = user_msg
    
    await update.message.reply_text(msg, parse_mode="
