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
model = genai.GenerativeModel('gemini-1.5-flash')

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
    prompt = f"""Extract top 3 products from this {site_name} search HTML.
Provide: product title, selling price, MRP, and bank offer.
Return ONLY JSON array: [{{"title": "...", "price": "₹...", "mrp": "₹...", "bank_offer": "..."}}]
If none, return [].
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

def find_cheapest(products, site_name, user_query):
    best = None
    best_price = float('inf')
    
    # Query ke keywords nikalne ke liye (jaise 'iphone', '15')
    query_words = [w.lower() for w in re.findall(r'\w+', user_query) if len(w) > 1]

    for p in products:
        title = p.get('title', '').lower()
        
        # STRICT FILTER: Agar query ka koi bhi important word title mein nahi hai, toh skip karo
        if query_words and not any(word in title for word in query_words):
            continue
            
        price_str = p.get('price', '').replace('₹', '').replace(',', '').strip()
        try:
            price = float(price_str)
        except:
            continue
        discount = 0
        offer_text = p.get('bank_offer', '')
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
        return {"site": site["name"], "status": "No data"}
    # Yahan user_query pass ki filter karne ke liye
    best = find_cheapest(products, site["name"], user_query)
    return best if best else {"site": site["name"], "status": "Not found"}

async def search_product(update, context):
    user_query = update.message.text
    await update.message.reply_text("⚡ Searching all sites simultaneously... Fetching best deals!")

    tasks = [process_single_site(site, user_query) for site in SITES]
    final_results = await asyncio.gather(*tasks)

    valid = [r for r in final_results if r and 'effective_price' in r]
    valid.sort(key=lambda x: x['effective_price'])

    if not valid:
        await update.message.reply_text("❌ Product not found or perfect match unavailable on the stores right now.")
        return

    msg = "🏆 **Cheapest Deal Found!**\n\n"
    for idx, deal in enumerate(valid):
        medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉"
        msg += f"{medal} **{deal['site']}**: {deal['title']}\n"
        msg += f" 💰 Price: ₹{deal['original_price']} | Discount: ₹{deal['discount']} | *Final: ₹{deal['effective_price']}*\n"
        site_obj = next(s for s in SITES if s["name"] == deal["site"])
        link = site_obj["search_url"].format(query=requests.utils.quote(user_query))
        msg += f" [Open on {deal['site']}]({link})\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def start(update, context):
    await update.message.reply_text("🛍️ Welcome to Sasta Deal Guru!\nSend me a product name and I'll find the cheapest price instantly.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN nahi mila!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
