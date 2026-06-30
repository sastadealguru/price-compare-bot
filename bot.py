import os
import logging
import requests
import json
import re
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables fetch karne ke liye fallback
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Sabhi shopping sites ki URLs list
SITES = [
    {"name": "Amazon", "search_url": "https://www.amazon.in/s?k={query}"},
    {"name": "Flipkart", "search_url": "https://www.flipkart.com/search?q={query}"},
    {"name": "Croma", "search_url": "https://www.croma.com/search/?text={query}"},
    {"name": "Reliance Digital", "search_url": "https://www.reliancedigital.in/search?q={query}"},
]

def fetch_page(url):
    # Free trial/account ke liye params ko simple rakha hai taaki Error 400 na aaye
    params = {
        'api_key': SCRAPINGBEE_KEY,
        'url': url,
        'render_js': 'false',
    }
    try:
        resp = requests.get('https://app.scrapingbee.com/api/v1/', params=params, timeout=30)
        if resp.status_code == 200:
            return resp.text
        else:
            logger.error(f"ScrapingBee error {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"ScrapingBee exception: {e}")
        return None

def extract_product_info(html, site_name):
    if not html:
        return []
    html_snippet = html[:15000]
    prompt = f"""Extract the top 3-5 product listings from this {site_name} search results HTML.
For each product provide: product title, selling price (after discount), MRP if visible, and any bank offer text.
Return ONLY a JSON array like: [{{"title": "...", "price": "₹...", "mrp": "₹...", "bank_offer": "..."}}]
If no results found, return [].

HTML: {html_snippet}"""
    try:
        response = model.generate_content(prompt)
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

async def search_product(update, context):
    user_query = update.message.text
    await update.message.reply_text("🔍 Searching Amazon, Flipkart, Croma, Reliance Digital... Please wait 15-20 sec.")

    final_results = []
    for site in SITES:
        search_url = site["search_url"].format(query=requests.utils.quote(user_query))
        html = fetch_page(search_url)
        products = extract_product_info(html, site["name"])
        if not products:
            final_results.append({"site": site["name"], "status": "No data"})
            continue
        best = find_cheapest(products, site["name"])
        if best:
            final_results.append(best)
        else:
            final_results.append({"site": site["name"], "status": "Not found"})

    valid = [r for r in final_results if 'effective_price' in r]
    valid.sort(key=lambda x: x['effective_price'])

    if not valid:
        await update.message.reply_text("❌ Product not found on any site.")
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
    await update.message.reply_text("🛍️ Welcome to Sasta Deal Guru!\nSend me a product name and I'll find the cheapest price with bank offers.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN ya TELEGRAM_BOT_TOKEN environment variable nahi mila!")
        
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
