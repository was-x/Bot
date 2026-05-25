import telebot
import re
import requests
from urllib.parse import quote
import logging
from threading import Thread
import time

# --- Configuration ---
BOT_TOKEN = "8772967393:AAF5ti5vgdPxx1LCZP7n_i8jyKyN-vFOyOA"
API_BASE_URL = "https://stripe-hitter.onrender.com"

# --- Setup ---
bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def encode_url(url: str) -> str:
    """Encode URL with # replaced by %23"""
    # First encode the URL properly
    encoded = quote(url, safe='')
    return encoded

def format_response(response_data: dict) -> str:
    """Format API response for better display"""
    if response_data.get("success"):
        msg = "✅ **SUCCESSFUL PAYMENT** ✅\n\n"
        msg += f"📊 **Attempts:** {response_data.get('attempts', 1)}\n"
        
        if response_data.get("card"):
            card = response_data["card"]
            msg += f"💳 **Card:** •••• {card.get('last4', 'N/A')}\n"
            msg += f"📅 **Expiry:** {card.get('exp', 'N/A')}\n"
        
        msg += f"💰 **Amount:** ${response_data.get('amount', 'N/A')}\n"
        msg += f"🌐 **Currency:** {response_data.get('currency', 'usd').upper()}\n"
        
        if response_data.get("requires3DS"):
            msg += "⚠️ **3DS Challenge Required**\n"
            if response_data.get("paymentIntent"):
                pi = response_data["paymentIntent"]
                msg += f"🆔 **Payment Intent:** `{pi.get('id', 'N/A')}`\n"
                msg += f"📌 **Status:** {pi.get('status', 'N/A')}\n"
        
        msg += "\n💸 Payment processed successfully!"
        return msg
    else:
        msg = "❌ **PAYMENT FAILED** ❌\n\n"
        msg += f"📊 **Attempts:** {response_data.get('attempts', 1)}\n"
        msg += f"📝 **Message:** {response_data.get('message', 'Unknown error')}\n"
        
        if response_data.get("error"):
            error = response_data["error"]
            msg += f"\n⚠️ **Error Details:**\n"
            msg += f"• Type: {error.get('type', 'N/A')}\n"
            msg += f"• Code: {error.get('code', 'N/A')}\n"
            msg += f"• Decline Code: {error.get('decline_code', 'N/A')}\n"
            msg += f"• Message: {error.get('message', 'N/A')}\n"
            
            if error.get("doc_url"):
                msg += f"• Docs: {error.get('doc_url')}\n"
        
        return msg

def validate_card(card_input: str) -> tuple:
    """Validate and parse card input: CC|MM|YYYY|CVV"""
    parts = card_input.replace(' ', '').split('|')
    
    if len(parts) != 4:
        return False, "Invalid format! Use: `CC|MM|YYYY|CVV`\nExample: `4111111111111111|02|2030|123`"
    
    cc, mm, yyyy, cvv = parts
    
    # Basic validations
    if not cc.isdigit() or len(cc) < 15 or len(cc) > 16:
        return False, "Invalid card number! Must be 15-16 digits"
    
    if not mm.isdigit() or int(mm) < 1 or int(mm) > 12:
        return False, "Invalid month! Must be 01-12"
    
    if not yyyy.isdigit() or len(yyyy) != 4:
        return False, "Invalid year! Must be 4 digits (e.g., 2030)"
    
    if not cvv.isdigit() or len(cvv) < 3 or len(cvv) > 4:
        return False, "Invalid CVV! Must be 3-4 digits"
    
    return True, (cc, mm, yyyy, cvv)

def validate_url(url: str) -> tuple:
    """Validate Stripe checkout URL"""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    
    if "stripe.com" not in url:
        return False, "Not a valid Stripe URL!"
    
    return True, url

def call_stripe_api(stripe_url: str, card_data: tuple = None) -> dict:
    """Call the Stripe API with or without card"""
    try:
        # Encode the URL properly
        encoded_url = quote(stripe_url, safe='')
        
        if card_data:
            # With card details
            cc, mm, yyyy, cvv = card_data
            api_url = f"{API_BASE_URL}/stripe/checkout-based/url/{encoded_url}"
            
            # Format card as required by API: CC|MM|YYYY|CVV
            card_string = f"{cc}|{mm}|{yyyy}|{cvv}"
            
            response = requests.post(
                api_url,
                json={"card": card_string},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
        else:
            # Without card - just get status
            api_url = f"{API_BASE_URL}/stripe/checkout-based/url/{encoded_url}"
            response = requests.get(api_url, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "message": f"API Error: {response.status_code}", "error": response.text}
    
    except requests.exceptions.Timeout:
        return {"success": False, "message": "Request timeout! API took too long to respond"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "Connection error! Cannot reach API server"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}

# --- Bot Commands ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Welcome message with inline keyboard"""
    user_name = message.from_user.first_name or "User"
    
    welcome_text = f"""
🎯 **Welcome to Auto Stripe Hitter** 🎯

Hello {user_name}! I'm a powerful Stripe payment testing bot.

**Features:**
• Test Stripe checkout URLs
• Process payments with custom cards
• Real-time response formatting
• 3DS challenge handling

**Commands:**
/cc - Process payment with card
/help - Show help menu

**How to use:**
Send a Stripe checkout URL directly, or use:
`/cc {stripe_url} {card_details}`

Example:
`/cc https://checkout.stripe.com/c/pay/... 4111111111111111|02|2030|123`
    """
    
    # Create inline keyboard
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📝 Help", callback_data="help"),
        InlineKeyboardButton("ℹ️ About", callback_data="about"),
        InlineKeyboardButton("⚡ Test Card", callback_data="test_card"),
        InlineKeyboardButton("👤 Profile", callback_data="profile")
    ]
    keyboard.add(*buttons)
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=['help'])
def send_help(message):
    """Help command"""
    help_text = """
📚 **Auto Stripe Hitter - Help Guide**

**Commands:**
/start - Show welcome menu
/help - Show this help
/cc - Process payment with card details

**Usage Examples:**

1️⃣ **Send URL only** (to check status):
Just send a Stripe checkout URL directly

2️⃣ **Process with card**:
`/cc https://checkout.stripe.com/c/pay/... 4111111111111111|02|2030|123`

**Card Format:**
`CC|MM|YYYY|CVV`

**Examples:**
• `4111111111111111|02|2030|123`
• `5555555555554444|12|2025|789`

**Test Cards:**
• Visa: 4111111111111111
• Mastercard: 5555555555554444
• Amex: 378282246310005

**Note:** Live mode requires real cards for actual charges!

**Support:** Contact @SupportBot for issues
    """
    
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['cc'])
def process_cc_command(message):
    """Process /cc command with URL and card"""
    try:
        # Remove command and split
        text = message.text.replace('/cc', '').strip()
        
        # Split by space - first part URL, rest is card
        parts = text.split(' ', 1)
        
        if len(parts) < 2:
            bot.reply_to(message, 
                "❌ **Invalid Usage!**\n\n"
                "Use: `/cc {stripe_url} {CC|MM|YYYY|CVV}`\n\n"
                "Example:\n"
                "`/cc https://checkout.stripe.com/c/pay/... 4111111111111111|02|2030|123`",
                parse_mode="Markdown"
            )
            return
        
        url = parts[0].strip()
        card_input = parts[1].strip()
        
        # Send processing message
        processing_msg = bot.reply_to(message, "🔄 **Processing payment...**\n⏳ Please wait...", parse_mode="Markdown")
        
        # Validate URL
        is_valid, url_result = validate_url(url)
        if not is_valid:
            bot.edit_message_text(f"❌ {url_result}", message.chat.id, processing_msg.message_id, parse_mode="Markdown")
            return
        
        # Validate card
        is_valid, card_result = validate_card(card_input)
        if not is_valid:
            bot.edit_message_text(f"❌ {card_result}", message.chat.id, processing_msg.message_id, parse_mode="Markdown")
            return
        
        # Call API with card
        response = call_stripe_api(url_result, card_result)
        
        # Format and send response
        formatted_response = format_response(response)
        bot.edit_message_text(formatted_response, message.chat.id, processing_msg.message_id, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ **Error:** `{str(e)}`", parse_mode="Markdown")
        logger.error(f"Error in cc command: {e}")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    """Handle any text message (Stripe URLs)"""
    text = message.text.strip()
    
    # Skip if it's a command
    if text.startswith('/'):
        return
    
    # Check if it looks like a URL
    if not text.startswith('http'):
        bot.reply_to(message, 
            "❌ **Invalid Input!**\n\n"
            "Please send a valid Stripe checkout URL or use:\n"
            "`/cc {url} {card_details}`\n\n"
            "Type `/help` for more info",
            parse_mode="Markdown"
        )
        return
    
    # Process as Stripe URL
    processing_msg = bot.reply_to(message, "🔄 **Checking Stripe URL...**\n⏳ Please wait...", parse_mode="Markdown")
    
    # Validate URL
    is_valid, url_result = validate_url(text)
    if not is_valid:
        bot.edit_message_text(f"❌ {url_result}", message.chat.id, processing_msg.message_id, parse_mode="Markdown")
        return
    
    # Call API without card
    response = call_stripe_api(url_result)
    
    # Format and send response
    formatted_response = format_response(response)
    bot.edit_message_text(formatted_response, message.chat.id, processing_msg.message_id, parse_mode="Markdown")

# --- Callback Handlers for Inline Buttons ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle inline button callbacks"""
    if call.data == "help":
        send_help(call.message)
        bot.answer_callback_query(call.id)
    
    elif call.data == "about":
        about_text = """
🤖 **About Auto Stripe Hitter**

**Version:** 1.0
**Developer:** Stripe Testing Bot
**API:** Stripe Hitter API

**Features:**
• Fast payment processing
• 3DS challenge support
• Real-time validation
• Secure card handling

**Disclaimer:**
This bot is for testing purposes only. Only use with your own payment methods or test cards.

**API Status:** 🟢 Online
        """
        bot.edit_message_text(about_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    elif call.data == "test_card":
        test_card_text = """
💳 **Test Cards (Stripe)**

**Visa:**
`4111111111111111|02|2030|123`

**Mastercard:**
`5555555555554444|12|2025|789`

**Amex:**
`378282246310005|03|2026|1234`

**Discover:**
`6011111111111117|01|2028|123`

**Live Mode Warning:**
• Test cards work only in test mode
• Live mode requires real cards
• Use at your own risk
        """
        bot.send_message(call.message.chat.id, test_card_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
    
    elif call.data == "profile":
        user = call.from_user
        profile_text = f"""
👤 **User Profile**

**ID:** `{user.id}`
**Name:** {user.first_name or 'N/A'} {user.last_name or ''}
**Username:** @{user.username if user.username else 'N/A'}
**Language:** {user.language_code or 'N/A'}

**Stats:**
• Member since: {call.message.date.strftime('%Y-%m-%d')}
• Premium: No

**API Limit:** Unlimited requests
        """
        bot.send_message(call.message.chat.id, profile_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

# --- Error Handler ---
@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    """Handle unknown commands"""
    bot.reply_to(message, 
        "❓ **Unknown command**\n\n"
        "Use `/start` to see available commands or `/help` for assistance.",
        parse_mode="Markdown"
    )

# --- Main Function ---
def main():
    """Start the bot"""
    print("🤖 Starting Auto Stripe Hitter Bot...")
    print(f"✅ Bot Token: {BOT_TOKEN[:10]}...")
    print(f"📡 API URL: {API_BASE_URL}")
    print("🚀 Bot is running... Press Ctrl+C to stop")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped!")
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    main()
