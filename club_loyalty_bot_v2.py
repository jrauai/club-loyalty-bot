import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
import re
import sys
import os

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
TOKEN = os.getenv('TOKEN')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Initialize gspread client
def get_sheets_client():
    """Connect to Google Sheets"""
    try:
        import json
        service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            logger.error("SERVICE_ACCOUNT_JSON not found in environment variables")
            return None
        creds = Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=SCOPES
        )
        return gspread.authorize(creds)
    except FileNotFoundError:
        logger.error("service_account.json not found!")
        return None
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets: {e}")
        return None

def get_customer_by_name(sheet, name):
    """Find customer in Master List by name"""
    try:
        records = sheet.get_all_records()
        for record in records:
            if record.get('Full Name', '').lower() == name.lower():
                return record
    except:
        return None
    return None

def add_customer(sheet, name, phone=""):
    """Add new customer to Master List"""
    try:
        next_id = len(sheet.get_all_records()) + 1
        sheet.append_row([
            next_id,
            name,
            phone,
            0,  # Points Balance
            0,  # Total Spent
            0,  # Guestlist Count
            datetime.now().strftime("%d/%m/%y %H:%M")
        ])
        return True
    except Exception as e:
        logger.error(f"Error adding customer: {e}")
        return False

def update_customer(sheet, name, points_change=0, spend_change=0, guestlist_change=0):
    """Update customer record"""
    try:
        records = sheet.get_all_records()
        for i, record in enumerate(records, start=2):
            if record.get('Full Name', '').lower() == name.lower():
                new_points = float(record.get('Points Balance', 0)) + points_change
                new_spent = float(record.get('Total Spent', 0)) + spend_change
                new_guestlist = int(record.get('Guestlist Count', 0)) + guestlist_change
                
                # Update each cell
                sheet.update(f'D{i}', [[new_points]])
                sheet.update(f'E{i}', [[new_spent]])
                sheet.update(f'F{i}', [[new_guestlist]])
                sheet.update(f'G{i}', [[datetime.now().strftime("%d/%m/%y %H:%M")]])
                
                return new_points
    except Exception as e:
        logger.error(f"Error updating customer: {e}")
    return 0

def log_transaction(sheet, name, trans_type, amount="", points_change=0, new_balance=0):
    """Log transaction to Transaction Log sheet"""
    try:
        customer_id = "?"
        client = get_sheets_client()
        if not client:
            return
        
        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        records = master_sheet.get_all_records()
        for record in records:
            if record.get('Full Name', '').lower() == name.lower():
                customer_id = record.get('Customer ID', '?')
                # Get the actual new balance from master sheet
                new_balance = record.get('Points Balance', 0)
                break
        
        sheet.append_row([
            customer_id,
            name,
            datetime.now().strftime("%d/%m/%y"),
            datetime.now().strftime("%H:%M"),
            trans_type,
            amount,
            points_change,
            new_balance,
            ""
        ])
    except Exception as e:
        logger.error(f"Error logging transaction: {e}")

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    help_text = "🎉 Club Loyalty Bot 🎉\n\n"
    help_text += "Available commands:\n\n"
    help_text += "📊 /check name - Check points\n"
    help_text += "💰 /add_spend name amount - Log spending\n"
    help_text += "🏆 /redeem name points - Redeem discount\n"
    help_text += "👥 /parse_guestlist venue - Parse guestlist\n"
    help_text += "📋 /list_venues - Show venues\n\n"
    help_text += "Examples:\n"
    help_text += "/check abd\n"
    help_text += "/add_spend abd 550\n"
    help_text += "/redeem abd 100\n"
    help_text += "/parse_guestlist ArtePlus"
    
    await update.message.reply_text(help_text)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check customer points"""
    if not context.args:
        await update.message.reply_text("❌ Usage: /check <name>\nExample: /check abd")
        return
    
    name = " ".join(context.args)
    
    try:
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return
            
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        customer = get_customer_by_name(sheet, name)
        
        if customer:
            points = customer.get('Points Balance', 0)
            spent = customer.get('Total Spent', 0)
            guestlist = customer.get('Guestlist Count', 0)
            worth = points / 100
            await update.message.reply_text(
                f"✅ {customer.get('Full Name')}\n"
                f"💎 Points: {points} Worth: RM{worth}\n"
                f"💰 Total Spent: RM{spent}\n"
                f"👥 Guestlist Count: {guestlist}"
            )
        else:
            await update.message.reply_text(f"❌ Customer '{name}' not found in database")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in check command: {e}")

async def add_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add customer spending"""
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /add_spend <name>, <amount>\nExample: /add_spend Hamza Shakil, 2000")
        return
    
    text = " ".join(context.args)
    
    if ',' not in text:
        await update.message.reply_text("❌ Usage: /add_spend <name>, <amount>\nExample: /add_spend Hamza Shakil, 2000")
        return
    
    name, amount_str = text.split(',', 1)
    name = name.strip()
    amount_str = amount_str.strip()
    
    try:
        amount = float(amount_str)
        points_earned = amount / 2
        
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return
            
        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        trans_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Transaction Log')
        
        customer = get_customer_by_name(master_sheet, name)
        
        if not customer:
            add_customer(master_sheet, name)
            customer = get_customer_by_name(master_sheet, name)
        
        new_points = update_customer(master_sheet, name, points_change=points_earned, spend_change=amount)
        log_transaction(trans_sheet, name, "Spend", f"RM{amount}", points_earned, new_points)
        
        await update.message.reply_text(
            f"✅ {name} spent RM{amount}\n"
            f"➕ Earned {points_earned} points\n"
            f"📊 New Balance: {new_points} pts"
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Use numbers only (e.g., 550)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in add_spend: {e}")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem points"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /redeem <name> <points>\nExample: /redeem abd 100")
        return
    
    name = context.args[0]
    try:
        points = float(context.args[1])
        discount = points / 100
        
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return
            
        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        trans_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Transaction Log')
        
        customer = get_customer_by_name(master_sheet, name)
        
        if not customer:
            await update.message.reply_text(f"❌ Customer '{name}' not found")
            return
        
        current_points = float(customer.get('Points Balance', 0))
        
        if current_points < points:
            await update.message.reply_text(
                f"❌ {name} doesn't have enough points\n"
                f"Has: {current_points} pts\n"
                f"Needs: {points} pts"
            )
            return
        
        new_points = update_customer(master_sheet, name, points_change=-points)
        log_transaction(trans_sheet, name, "Redeem", f"RM{discount} discount", -points, new_points)
        
        await update.message.reply_text(
            f"✅ {name} redeemed {points} points\n"
            f"💳 Discount: RM{discount}\n"
            f"📊 New Balance: {new_points} pts"
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid points. Use numbers only (e.g., 100)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in redeem: {e}")

async def parse_guestlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add guestlist - comma separated names in one command"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /parse_guestlist <venue> <name1>, <name2>, <name3>\n"
            "Example: /parse_guestlist ArtePlus lfis ahmed sheikh, mfis erty, jack is gay"
        )
        return

    venue = context.args[0]
    names_text = " ".join(context.args[1:])
    names = [name.strip() for name in names_text.split(',') if name.strip()]

    if not names:
        await update.message.reply_text("❌ No names found")
        return

    try:
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return

        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        trans_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Transaction Log')

        added = 0
        for name in names:
            customer = get_customer_by_name(master_sheet, name)
            if not customer:
                add_customer(master_sheet, name)
            update_customer(master_sheet, name, points_change=0.5, guestlist_change=1)
            log_transaction(trans_sheet, name, "Guestlist", f"{venue}", 0.5, 0)
            added += 1

        await update.message.reply_text(f"✅ Added {added} people from {venue}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error: {e}")

    try:
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return

        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        trans_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Transaction Log')

        added = 0
        for name in names:
            customer = get_customer_by_name(master_sheet, name)
            if not customer:
                add_customer(master_sheet, name)
            update_customer(master_sheet, name, points_change=0.5, guestlist_change=1)
            log_transaction(trans_sheet, name, "Guestlist", f"{venue}", 0.5, 0)
            added += 1

        await update.message.reply_text(f"✅ Added {added} people from {venue}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in parse_guestlist: {e}")

async def handle_guestlist_paste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pasted guestlist text"""
    if 'parsing_venue' not in context.user_data:
        return
    
    venue = context.user_data['parsing_venue']
    text = update.message.text
    
    names = parse_names_from_text(text)
    
    if not names:
        await update.message.reply_text("❌ No names found in the pasted text")
        return
    
    try:
        client = get_sheets_client()
        if not client:
            await update.message.reply_text("❌ Database connection error")
            return
            
        master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
        
        existing = []
        new_names = []
        
        for name in names:
            if get_customer_by_name(master_sheet, name):
                existing.append(name)
            else:
                new_names.append(name)
        
        summary = f"📊 Guestlist for {venue}\n\n"
        summary += f"✅ New names: {len(new_names)}\n"
        if new_names:
            summary += "  " + "\n  ".join(new_names[:5])
            if len(new_names) > 5:
                summary += f"\n  ... and {len(new_names) - 5} more\n"
        
        if existing:
            summary += f"\n⚠️  Already exist ({len(existing)}):\n"
            summary += "  " + "\n  ".join(existing[:5])
            if len(existing) > 5:
                summary += f"\n  ... and {len(existing) - 5} more\n"
        
        summary += f"\n\nProceed? Reply with YES or NO"
        
        context.user_data['pending_names'] = new_names
        context.user_data['pending_existing'] = existing
        
        await update.message.reply_text(summary)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in handle_guestlist_paste: {e}")

async def confirm_guestlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and add guestlist"""
    response = update.message.text.upper().strip()
    
    if 'pending_names' not in context.user_data:
        return
    
    if response == "YES":
        venue = context.user_data.get('parsing_venue', 'Unknown')
        new_names = context.user_data['pending_names']
        
        try:
            client = get_sheets_client()
            if not client:
                await update.message.reply_text("❌ Database connection error")
                return
                
            master_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Master List')
            trans_sheet = client.open_by_key(SPREADSHEET_ID).worksheet('Transaction Log')
            
            added_count = 0
            for name in new_names:
                add_customer(master_sheet, name)
                update_customer(master_sheet, name, points_change=0.5, guestlist_change=1)
                log_transaction(trans_sheet, name, "Guestlist", f"{venue}", 0.5, 0.5)
                added_count += 1
            
            await update.message.reply_text(
                f"✅ Added {added_count} customers from {venue} guestlist"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding guestlist: {str(e)}")
            logger.error(f"Error adding guestlist: {e}")
        
        context.user_data.pop('parsing_venue', None)
        context.user_data.pop('pending_names', None)
        context.user_data.pop('pending_existing', None)
    
    elif response == "NO":
        await update.message.reply_text("❌ Cancelled guestlist parsing")
        context.user_data.pop('parsing_venue', None)
        context.user_data.pop('pending_names', None)
        context.user_data.pop('pending_existing', None)

async def list_venues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List common venues"""
    venues = """
📍 Common Venues:
• ArtePlus
• Lane23
• ykō
• Nono Club KL
• Baby Pery
• Project X
• kyo

Usage: /parse_guestlist <VenueName>
    """
    await update.message.reply_text(venues)

def parse_names_from_text(text):
    """Extract names from messy guestlist text"""
    lines = text.split('\n')
    names = []
    
    for line in lines:
        line = line.strip()
        
        if not line or line.lower() in ['free', 'rsvp', 'gl', 'guy', 'girl', 'm', 'f']:
            continue
        
        line = re.sub(r'[🚺🚹👤]', '', line)
        line = re.sub(r'\(F\)|\(M\)|\(female\)|\(male\)', '', line, flags=re.IGNORECASE)
        line = re.sub(r'♀|♂', '', line)
        
        line = re.sub(r'^\d+[\.\)\-\s]+', '', line)
        
        if 'RM' in line or 'comm' in line.lower() or 'jager' in line.lower():
            continue
        
        line = re.sub(r'\b(guy|girl|m|f|rm\d+|comm|free|pax)\b', '', line, flags=re.IGNORECASE)
        
        line = line.strip()
        
        if len(line) >= 2 and not any(x in line for x in ['/', '|', '—', '–']):
            names.append(line)
    
    return names

def main():
    """Start the bot - Windows compatible version"""
    
    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: TOKEN not configured in the script!")
        print("Replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token")
        return
    
    if not SPREADSHEET_ID or SPREADSHEET_ID == "YOUR_SPREADSHEET_ID_HERE":
        print("❌ ERROR: SPREADSHEET_ID not configured in the script!")
        print("Replace 'YOUR_SPREADSHEET_ID_HERE' with your actual spreadsheet ID")
        return
    
    print("✅ Starting Club Loyalty Bot...")
    print("Press Ctrl+C to stop")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("add_spend", add_spend))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("parse_guestlist", parse_guestlist))
    app.add_handler(CommandHandler("list_venues", list_venues))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_guestlist))
    
    # Use run_polling with no_warn for Windows compatibility
    try:
        app.run_polling(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n\n❌ Bot stopped by user")
        sys.exit(0)

if __name__ == '__main__':
    # Windows event loop fix
    if sys.platform == 'win32':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    main()
