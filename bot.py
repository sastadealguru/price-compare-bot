import os
import logging
import requests
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
SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')

SITES = [
    {"name": "Amazon", "search_url": "https://www.amazon.in/s?k={query}"},
    {"name": "Flipkart", "search_url": "https://www.flipkart.com/search?q={query}"},
    {"name": "Croma", "search_url": "https://www.croma.com/search/?text={query}"},
    {"name": "Reliance Digital", "search_url": "https://www.reliancedigital.in/search?q={query}"},
]

async def fetch_page_async(url):
    params = {
        'api_key': SCRAPINGBEE_KEY,
        'url': url,
        'render_js': 'false',
    }
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(None, lambda: requests.get('https://app.scrapingbee.com/api/v1/', params=params, timeout=20))
        if resp.status_code == 200:
            return resp.text
        else:
            logger.error(f"ScrapingBee error {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"ScrapingBee exception: {e}")
        return None

async def extract_product_info_async(html, site_name):
    if not html:
        return []
    html_snippet = html[:8000]
    prompt = f"""Extract top 2 visible items/products from this {site_name} HTML snippet.
Provide: product title, selling price, MRP, and bank offer.
Return ONLY JSON array: [{{"title": "...", "price": "₹...", "mrp": "₹...", "bank_offer": "..."}}]
If nothing is found at all, return [].
HTML: {html_snippet}"""
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        return []
    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        return []

def find_cheapest(products, site_name):
    best = None
    best_price = float('inf')

    for p in products:
        # Strict matching filter ko hata diya hai testing ke liye
        price_str = (p.get('price') or '').replace('₹', '').replace(',', '').strip()
        try:
            price = float(price_str)
        except:
            continue
            
        discount = 0
        offer_text = p.get('bank_offer') or ''
        discount_matches = re.findall(r'₹(\d+)', offer_text)
        if discount_matches:
            discount = max([int(x) for x in discount_matches])
            
        effective = price - discount
        if effective < best_price:
            best_price = effective
            best = {**p, "effective_price": effective, "site": site_name, "original_price": price, "discount": discount}
    return best

async def process_single_site(site, user_query):
    search_url = site["search_url"].format(query=requests.utils.quote(user_query))
    html = await fetch_page_async(search_url)
    products = await extract_product_info_async(html, site["name"])
    if not products:
        return None
    return find_cheapest(products, site["name"])

async def search_product(update, context):
    user_query = update.message.text
    await update.message.reply_text("⚡ Testing API responses... Fetching whatever the sites are returning!")

    tasks = [process_single_site(site, user_query) for site in SITES]
    final_results = await asyncio.gather(*tasks)

    valid = [r for r in final_results if r and 'effective_price' in r]
    valid.sort(key=lambda x: x['effective_price'])

    if not valid:
        await update.message.reply_text("❌ Sabhi sites ne completely block kar diya hai ya HTML khali hai.")
        return

    msg = "📊 **Raw Data Found from Sites:**\n\n"
    for idx, deal in enumerate(valid):
        medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉"
        msg += f"{medal} **{deal['site']}**: {deal['title']}\n"
        msg += f" 💰 Price: ₹{deal['original_price']} | *Final: ₹{deal['effective_price']}*\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def start(update, context):
    await update.message.reply_text("🛍️ Welcome to Sasta Deal Guru!\nSend me a product name.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN nahi mila!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
