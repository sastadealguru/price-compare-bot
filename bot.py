import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

SITES = [
    {"name": "Amazon", "search_url": "https://www.amazon.in/s?k={query}", "emoji": "📦"},
    {"name": "Flipkart", "search_url": "https://www.flipkart.com/search?q={query}", "emoji": "🛍️"},
    {"name": "Croma", "search_url": "https://www.croma.com/search/?text={query}", "emoji": "🔌"},
    {"name": "Reliance Digital", "search_url": "https://www.reliancedigital.in/search?q={query}", "emoji": "⚡"},
]

async def search_product(update, context):
    user_query = update.message.text
    encoded_query = requests.utils.quote(user_query)
    
    msg = f"🔍 **Live Deal Links for: {user_query}**\n\n"
    msg += "Click below to open direct search results with live bank offers:\n\n"
    
    for site in SITES:
        link = site["search_url"].format(query=encoded_query)
        msg += f"{site['emoji']} **{site['name']}**:\n👉 [Check Cheapest Price on {site['name']}]({link})\n\n"
        
    msg += "💡 _Tip: Check bank discounts directly on the store pages for the final sasta price!_"
    
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def start(update, context):
    await update.message.reply_text("🛍️ Welcome to Sasta Deal Guru!\nSend me any product name and I'll fetch instant live search links for you.")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Error: TELEGRAM_TOKEN nahi mila!")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_product))
    app.run_polling()

if __name__ == "__main__":
    main()
