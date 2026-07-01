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
        return None
    prompt = f"""
    Act as an Indian shopping expert. For the item '{query}', provide the typical current online selling price (in INR) and any ongoing bank/discount offers across these apps: Amazon, Flipkart, JioMart, Blinkit, Zepto, Croma, Reliance Digital, Swiggy Instamart, Snapdeal, eBay.
    Only return a clean JSON array of objects with keys 'site', 'price' (numerical value only), 'title', and 'offer'.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error(f"Gemini limit reached or failed: {e}")
    return None # Return None if limit exceeded

async def handle_user_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    
    if re.match(r'^\d+$', user_msg):
        pending_item = context.user_data.get('pending_item')
        if pending_item:
            target_price = float(user_msg)
            alerts = load_alerts()
            if chat_id not in alerts:
                alerts[chat_id] = {}
            alerts[chat_id][pending_item] = target_price
            save_alerts(alerts)
            context.user_data['pending_item'] = None
            await update.message.reply_text(f"✅ **Alert Set Ho Gaya!**\n\n🛒 Item: {pending_item}\n📉 Target Price: ₹{target_price}\n\nJaise hi price isse kam hoga, main notification bhej dunga!")
            return
        else:
            await update.message.reply_text("❌ Pehle kisi product ka naam likhein.")
            return

    await update.message.reply_text(f"🔍 Fetching links & checking deals for '{user_msg}'...")
    encoded_query = urllib.parse.quote_plus(user_msg)
    
    raw_deals = await get_prices_and_offers_from_gemini(user_msg)
    
    # Simple formatting tracker
    msg = f"🏆 **Comparison Links for: {user_msg}**\n\n"
    
    if raw_deals and isinstance(raw_deals, list):
        raw_deals.sort(key=lambda x: x.get('price', 999999))
        returned_sites = {d['site'].lower(): d for d in raw_deals if 'site' in d}
        
        idx = 1
        for site in ALL_SITES:
            site_key = site["name"].lower()
            match_key = "flipkart" if "flipkart" in site_key else "amazon" if "amazon" in site_key else site_key
            deal = returned_sites.get(match_key) or returned_sites.get(site_key)
            link = site["url"].format(q=encoded_query)
            
            if deal:
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🔹"
                msg += f"{medal} **{site['name']}**: ₹{deal['price']:,}\n"
                msg += f" 🎁 *Offer*: {deal.get('offer', 'Check app')}\n"
                msg += f" 👉 [Open Results]({link})\n\n"
                idx += 1
            else:
                msg += f"🔹 **{site['name']}**:\n 👉 [Check Live Price]({link})\n\n"
    else:
        # FAIL-SAFE: Gemini limit exceeded par bhi links aur interface hamesha chalega!
        msg += "⚠️ _Note: Gemini API free limit temporary full hai, isliye direct live stores se price check karein:_\n\n"
        for site in ALL_SITES:
            link = site["url"].format(q=encoded_query)
            msg += f"{site['emoji']} **{site['name']}**:\n 👉 [Click to open store search]({link})\n\n"
            
    msg += "───────────────────\n"
    msg += f"🤔 **Aapko yeh '{user_msg}' kitne rupaye mein chahiye?**\n"
    msg += "Neeche reply mein bas target price (number) likh dijiye, main auto-alert background mein track karunga! (e.g. 400)"
    
    context.user_data['pending_item'] = user_msg
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def check_prices_background(app):
    while True:
        await asyncio.sleep(7200) # Check interval to 2 hours to avoid free tier lockouts
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
                        msg = f"🚨 **PRICE DROP ALERT!**\n\n💰 **{item}** budget mein hai!\n📈 Target: ₹{target_price}\n🔥 Live Price: ₹{current_price}"
                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                        del alerts[chat_id][item]
                        save_alerts(alerts)
                except:
                    pass

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
