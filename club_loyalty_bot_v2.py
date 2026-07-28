# ==========================================
# CLUB LOYALTY BOT
# Part 1: Configuration + Google Sheets Core
# ==========================================

import logging
import os
import sys
import json
import re
from datetime import datetime
from functools import wraps

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from google.oauth2.service_account import Credentials
import gspread


# ==========================================
# Logging
# ==========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ==========================================
# Environment Configuration
# ==========================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

TOKEN = os.getenv("TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

ADMIN_IDS = [
    # Add Telegram user IDs here
    # Example:
    # 123456789
]


# ==========================================
# Admin Protection Decorator
# ==========================================

def admin_only(func):
    """
    Restrict commands to approved Telegram users
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text(
                "❌ You are not authorised to use this command."
            )
            return

        return await func(update, context)

    return wrapper



# ==========================================
# Google Sheets Connection
# ==========================================

def get_sheets_client():
    """
    Connect to Google Sheets using service account JSON
    """

    try:

        service_account_json = os.getenv(
            "SERVICE_ACCOUNT_JSON"
        )

        if not service_account_json:
            logger.error(
                "SERVICE_ACCOUNT_JSON missing"
            )
            return None


        credentials = Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=SCOPES
        )


        return gspread.authorize(credentials)


    except json.JSONDecodeError:

        logger.error(
            "Invalid SERVICE_ACCOUNT_JSON format"
        )

    except Exception as e:

        logger.error(
            f"Google Sheets connection failed: {e}"
        )


    return None



def get_sheet(sheet_name):
    """
    Shortcut function to retrieve worksheet
    """

    try:

        client = get_sheets_client()

        if not client:
            return None


        spreadsheet = client.open_by_key(
            SPREADSHEET_ID
        )

        return spreadsheet.worksheet(
            sheet_name
        )


    except Exception as e:

        logger.error(
            f"Cannot open sheet {sheet_name}: {e}"
        )

        return None



# ==========================================
# Utility Functions
# ==========================================

def current_datetime():

    return datetime.now().strftime(
        "%d/%m/%y %H:%M"
    )



def current_date():

    return datetime.now().strftime(
        "%d/%m/%y"
    )



def current_time():

    return datetime.now().strftime(
        "%H:%M"
    )



def clean_name(name):

    """
    Normalize names for searching
    """

    return (
        name
        .strip()
        .lower()
    )



# ==========================================
# Customer Search
# ==========================================

def get_customer_by_name(sheet, name):
    """
    Find customer using partial name matching
    """

    try:

        search = clean_name(name)

        records = sheet.get_all_records()


        for record in records:

            customer_name = clean_name(
                str(record.get("Full Name", ""))
            )


            if search in customer_name:
                return record


    except Exception as e:

        logger.error(
            f"Customer lookup failed: {e}"
        )


    return None



def get_customer_row(sheet, name):
    """
    Get Google Sheet row number
    """

    try:

        search = clean_name(name)

        records = sheet.get_all_records()


        for index, record in enumerate(
            records,
            start=2
        ):

            customer_name = clean_name(
                str(record.get("Full Name", ""))
            )


            if search in customer_name:
                return index


    except Exception as e:

        logger.error(
            f"Finding customer row failed: {e}"
        )


    return None

# ==========================================
# Part 2: Customer Management
# ==========================================


def generate_customer_id(sheet):
    """
    Generate next unique customer ID
    """

    try:

        records = sheet.get_all_records()

        ids = []

        for record in records:

            try:
                ids.append(
                    int(record.get("Customer ID", 0))
                )

            except:
                continue


        if not ids:
            return 1


        return max(ids) + 1


    except Exception as e:

        logger.error(
            f"Customer ID generation failed: {e}"
        )

        return 1



def add_customer(sheet, name, phone=""):
    """
    Add new customer
    """

    try:

        customer_id = generate_customer_id(
            sheet
        )


        sheet.append_row(
            [
                customer_id,
                name,
                phone,
                0,              # Points Balance
                0,              # Total Spent
                0,              # Guestlist Count
                current_datetime()
            ]
        )


        logger.info(
            f"Added customer: {name}"
        )


        return True


    except Exception as e:

        logger.error(
            f"Adding customer failed: {e}"
        )


        return False



def update_customer(
        sheet,
        name,
        points_change=0,
        spend_change=0,
        guestlist_change=0
):
    """
    Update customer information
    """

    try:

        row = get_customer_row(
            sheet,
            name
        )


        if not row:
            return None



        records = sheet.get_all_records()

        record = records[row - 2]


        current_points = float(
            record.get(
                "Points Balance",
                0
            )
        )


        current_spent = float(
            record.get(
                "Total Spent",
                0
            )
        )


        current_guestlist = int(
            record.get(
                "Guestlist Count",
                0
            )
        )


        new_points = max(
            0,
            current_points + points_change
        )


        new_spent = (
            current_spent +
            spend_change
        )


        new_guestlist = (
            current_guestlist +
            guestlist_change
        )


        # Update columns
        #
        # D = Points
        # E = Total Spent
        # F = Guestlist Count
        # G = Last Updated

        sheet.update(
            f"D{row}",
            [[new_points]]
        )

        sheet.update(
            f"E{row}",
            [[new_spent]]
        )


        sheet.update(
            f"F{row}",
            [[new_guestlist]]
        )


        sheet.update(
            f"G{row}",
            [[current_datetime()]]
        )


        return new_points



    except Exception as e:

        logger.error(
            f"Customer update failed: {e}"
        )


        return None



# ==========================================
# Transaction Logging
# ==========================================


def get_customer_id(sheet, name):

    try:

        customer = get_customer_by_name(
            sheet,
            name
        )


        if customer:

            return customer.get(
                "Customer ID",
                "?"
            )


    except Exception as e:

        logger.error(
            f"Customer ID lookup failed: {e}"
        )


    return "?"



def log_transaction(
        sheet,
        customer_sheet,
        name,
        trans_type,
        amount="",
        points_change=0,
        new_balance=0,
        venue=""
):
    """
    Add transaction record
    """

    try:

        customer_id = get_customer_id(
            customer_sheet,
            name
        )


        sheet.append_row(
            [
                customer_id,
                name,
                current_date(),
                current_time(),
                trans_type,
                venue,
                amount,
                points_change,
                new_balance
            ]
        )


    except Exception as e:

        logger.error(
            f"Transaction logging failed: {e}"
        )



# ==========================================
# Loyalty Calculation
# ==========================================


def calculate_points(amount):

    """
    LFIS Rule:
    RM2 spent = 1 point
    """

    try:

        return int(
            float(amount) // 2
        )

    except:

        return 0



# ==========================================
# Duplicate Protection
# ==========================================


def customer_exists(sheet, name):

    return (
        get_customer_by_name(
            sheet,
            name
        )
        is not None
    )



def remove_duplicate_names(names):

    """
    Prevent duplicate guestlist entries
    """

    cleaned = []

    seen = set()


    for name in names:

        key = clean_name(name)


        if key not in seen:

            seen.add(key)
            cleaned.append(name)


    return cleaned

# ==========================================
# Part 3: Telegram Commands
# ==========================================


async def start(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    text = """
🎉 LFIS Loyalty Bot 🎉

Available Commands:

📊 Check Points
/check <name>

Example:
/check Hamza


💰 Add Spending
/add_spend <name>, <amount>

Example:
/add_spend Hamza Shakil, 500


🏆 Redeem Points
/redeem <name> <points>

Example:
/redeem Hamza Shakil 100


👥 Parse Guestlist
/parse_guestlist <venue>


🏅 Leaderboard
/top


📜 History
/history <name>
"""

    await update.message.reply_text(text)



# ==========================================
# CHECK POINTS
# ==========================================


@admin_only
async def check(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "❌ Usage:\n/check <name>"
        )

        return


    name = " ".join(
        context.args
    )


    try:

        sheet = get_sheet(
            "Master List"
        )


        if not sheet:

            await update.message.reply_text(
                "❌ Database error"
            )

            return



        customer = get_customer_by_name(
            sheet,
            name
        )


        if not customer:

            await update.message.reply_text(
                f"❌ {name} not found"
            )

            return



        points = float(
            customer.get(
                "Points Balance",
                0
            )
        )


        spent = float(
            customer.get(
                "Total Spent",
                0
            )
        )


        guestlist = customer.get(
            "Guestlist Count",
            0
        )


        await update.message.reply_text(
            f"""
✅ {customer.get('Full Name')}

💎 Points:
{points}

💰 Total Spent:
RM{spent}

👥 Guestlist:
{guestlist}

🎁 Discount Value:
RM{points/100:.2f}
"""
        )


    except Exception as e:

        logger.error(
            f"Check error: {e}"
        )

        await update.message.reply_text(
            "❌ Error checking customer"
        )



# ==========================================
# ADD SPENDING
# ==========================================


@admin_only
async def add_spend(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    text = " ".join(
        context.args
    )


    if "," not in text:

        await update.message.reply_text(
            "❌ Format:\n/add_spend Name, Amount"
        )

        return



    try:

        name, amount = text.split(
            ",",
            1
        )


        name = name.strip()

        amount = float(
            amount.strip()
        )


        master_sheet = get_sheet(
            "Master List"
        )


        transaction_sheet = get_sheet(
            "Transaction Log"
        )


        if not customer_exists(
            master_sheet,
            name
        ):

            add_customer(
                master_sheet,
                name
            )



        points = calculate_points(
            amount
        )


        new_balance = update_customer(
            master_sheet,
            name,
            points_change=points,
            spend_change=amount
        )



        log_transaction(
            transaction_sheet,
            master_sheet,
            name,
            "Spend",
            f"RM{amount}",
            points,
            new_balance
        )



        await update.message.reply_text(
            f"""
✅ Spending Added

👤 {name}

💰 Amount:
RM{amount}

➕ Points Earned:
{points}

💎 New Balance:
{new_balance} pts
"""
        )


    except ValueError:

        await update.message.reply_text(
            "❌ Invalid amount"
        )


    except Exception as e:

        logger.error(
            f"Add spend error: {e}"
        )

        await update.message.reply_text(
            "❌ Failed to add spending"
        )



# ==========================================
# REDEEM
# ==========================================


@admin_only
async def redeem(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    if len(context.args) < 2:

        await update.message.reply_text(
            "❌ Format:\n/redeem Name Points"
        )

        return



    try:

        points = float(
            context.args[-1]
        )


        name = " ".join(
            context.args[:-1]
        )


        master_sheet = get_sheet(
            "Master List"
        )


        transaction_sheet = get_sheet(
            "Transaction Log"
        )


        customer = get_customer_by_name(
            master_sheet,
            name
        )


        if not customer:

            await update.message.reply_text(
                "❌ Customer not found"
            )

            return



        current_points = float(
            customer.get(
                "Points Balance",
                0
            )
        )



        if current_points < points:

            await update.message.reply_text(
                f"""
❌ Insufficient points

Available:
{current_points}

Required:
{points}
"""
            )

            return



        new_balance = update_customer(
            master_sheet,
            name,
            points_change=-points
        )



        discount = points / 100



        log_transaction(
            transaction_sheet,
            master_sheet,
            name,
            "Redeem",
            f"RM{discount}",
            -points,
            new_balance
        )



        await update.message.reply_text(
            f"""
✅ Redemption Successful

👤 {name}

🔥 Used:
{points} points

💳 Discount:
RM{discount:.2f}

💎 Remaining:
{new_balance} points
"""
        )


    except Exception as e:

        logger.error(
            f"Redeem error: {e}"
        )

        await update.message.reply_text(
            "❌ Redemption failed"
        )



# ==========================================
# TOP MEMBERS
# ==========================================


@admin_only
async def top(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    try:

        sheet = get_sheet(
            "Master List"
        )


        records = sheet.get_all_records()



        ranking = sorted(
            records,
            key=lambda x:
                float(
                    x.get(
                        "Points Balance",
                        0
                    )
                ),
            reverse=True
        )


        message = "🏆 LFIS TOP MEMBERS\n\n"


        for index, user in enumerate(
            ranking[:10],
            start=1
        ):

            message += (
                f"{index}. "
                f"{user.get('Full Name')}"
                f" - "
                f"{user.get('Points Balance')} pts\n"
            )


        await update.message.reply_text(
            message
        )


    except Exception as e:

        logger.error(
            f"Leaderboard error: {e}"
        )



# ==========================================
# CUSTOMER HISTORY
# ==========================================


@admin_only
async def history(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "❌ Usage:\n/history Name"
        )

        return


    name = " ".join(
        context.args
    )


    try:

        sheet = get_sheet(
            "Transaction Log"
        )


        records = sheet.get_all_records()



        results = []


        for row in records:

            if clean_name(name) in clean_name(
                str(row.get("Full Name",""))
            ):

                results.append(row)



        if not results:

            await update.message.reply_text(
                "❌ No history found"
            )

            return



        message = (
            f"📜 History: {name}\n\n"
        )


        for item in results[-10:]:

            message += (
                f"{item.get('Date')} "
                f"{item.get('Type')} "
                f"{item.get('Points Change')} pts\n"
            )


        await update.message.reply_text(
            message
        )


    except Exception as e:

        logger.error(
            f"History error: {e}"
        )

# ==========================================
# Part 4: Guestlist System
# ==========================================


async def parse_guestlist(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    """
    Start guestlist parsing process

    Usage:
    /parse_guestlist ArtePlus
    """

    if not context.args:

        await update.message.reply_text(
            """
❌ Usage:

/parse_guestlist <venue>

Example:
/parse_guestlist ArtePlus
"""
        )

        return



    venue = " ".join(
        context.args
    )


    context.user_data[
        "parsing_venue"
    ] = venue



    await update.message.reply_text(
        f"""
📋 Guestlist Mode Activated

Venue:
{venue}

Please paste the guestlist below.

Example:

Ahmed
John
Sarah
Mike
"""
    )



# ==========================================
# Guestlist Text Parser
# ==========================================


def parse_names_from_text(text):

    """
    Clean guestlist text
    """

    names = []


    lines = text.split(
        "\n"
    )


    ignored_words = [
        "free",
        "rsvp",
        "guestlist",
        "gl",
        "girl",
        "girls",
        "guy",
        "guys",
        "male",
        "female",
        "comm",
        "commission",
        "pax"
    ]



    for line in lines:

        line = line.strip()


        if not line:
            continue



        # Remove emojis

        line = re.sub(
            r"[🚺🚹👤♀♂]",
            "",
            line
        )


        # Remove numbering

        line = re.sub(
            r"^\d+[\.\)\-\s]+",
            "",
            line
        )


        # Remove gender tags

        line = re.sub(
            r"\((F|M|Female|Male)\)",
            "",
            line,
            flags=re.IGNORECASE
        )


        # Remove prices

        line = re.sub(
            r"RM\d+",
            "",
            line,
            flags=re.IGNORECASE
        )


        # Remove common labels

        words = line.split()

        filtered = []


        for word in words:

            if word.lower() not in ignored_words:

                filtered.append(word)



        line = " ".join(
            filtered
        ).strip()



        # Validation

        if (
            len(line) >= 2
            and not any(
                symbol in line
                for symbol in [
                    "/",
                    "|",
                    "—",
                    "–"
                ]
            )
        ):

            names.append(line)



    return remove_duplicate_names(
        names
    )



# ==========================================
# Handle Pasted Guestlist
# ==========================================


async def handle_guestlist_paste(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):


    if (
        "parsing_venue"
        not in context.user_data
    ):

        return



    text = update.message.text


    venue = context.user_data[
        "parsing_venue"
    ]



    names = parse_names_from_text(
        text
    )



    if not names:

        await update.message.reply_text(
            "❌ No valid names detected"
        )

        return



    master_sheet = get_sheet(
        "Master List"
    )


    existing = []

    new = []



    for name in names:


        if customer_exists(
            master_sheet,
            name
        ):

            existing.append(
                name
            )

        else:

            new.append(
                name
            )



    context.user_data[
        "pending_new"
    ] = new


    context.user_data[
        "pending_existing"
    ] = existing



    summary = (
        f"📋 Guestlist Preview\n\n"
        f"📍 Venue:\n{venue}\n\n"
        f"🆕 New Customers:\n"
        f"{len(new)}\n\n"
    )



    if new:

        summary += "\n".join(
            new[:10]
        )



    if len(new) > 10:

        summary += (
            f"\n...and {len(new)-10} more"
        )



    summary += (
        "\n\n"
        f"⚠️ Existing Customers:\n"
        f"{len(existing)}\n\n"
        "Proceed?\n"
        "Reply YES or NO"
    )



    await update.message.reply_text(
        summary
    )



# ==========================================
# Confirm Guestlist
# ==========================================


async def confirm_guestlist(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):


    if (
        "pending_new"
        not in context.user_data
    ):

        return



    response = (
        update.message.text
        .strip()
        .upper()
    )



    if response == "NO":


        context.user_data.clear()


        await update.message.reply_text(
            "❌ Guestlist cancelled"
        )


        return



    if response != "YES":

        return



    venue = context.user_data.get(
        "parsing_venue",
        "Unknown"
    )



    names = context.user_data[
        "pending_new"
    ]



    master_sheet = get_sheet(
        "Master List"
    )


    transaction_sheet = get_sheet(
        "Transaction Log"
    )



    added = 0



    for name in names:


        if not customer_exists(
            master_sheet,
            name
        ):

            add_customer(
                master_sheet,
                name
            )



        new_balance = update_customer(
            master_sheet,
            name,
            points_change=0.5,
            guestlist_change=1
        )



        log_transaction(
            transaction_sheet,
            master_sheet,
            name,
            "Guestlist",
            "",
            0.5,
            new_balance,
            venue
        )


        added += 1



    context.user_data.clear()



    await update.message.reply_text(
        f"""
✅ Guestlist Added

📍 Venue:
{venue}

👥 Customers:
{added}

⭐ Points Awarded:
+0.5 each
"""
    )

# ==========================================
# Part 5: Bot Startup
# ==========================================


async def error_handler(
        update: object,
        context: ContextTypes.DEFAULT_TYPE
):

    """
    Global Telegram error handler
    """

    logger.error(
        "Telegram error occurred",
        exc_info=context.error
    )


    try:

        if update and hasattr(
            update,
            "effective_message"
        ):

            await update.effective_message.reply_text(
                "❌ An unexpected error occurred."
            )


    except Exception:

        pass



# ==========================================
# Startup Validation
# ==========================================


def validate_configuration():

    """
    Check required environment variables
    """

    missing = []


    if not TOKEN:

        missing.append(
            "TOKEN"
        )


    if not SPREADSHEET_ID:

        missing.append(
            "SPREADSHEET_ID"
        )


    if not os.getenv(
        "SERVICE_ACCOUNT_JSON"
    ):

        missing.append(
            "SERVICE_ACCOUNT_JSON"
        )



    if missing:

        print(
            "❌ Missing configuration:"
        )

        for item in missing:

            print(
                f"- {item}"
            )

        return False



    return True



# ==========================================
# Main Function
# ==========================================


def main():

    """
    Start LFIS Loyalty Bot
    """


    if not validate_configuration():

        return



    print(
        """
=================================

🎉 LFIS Loyalty Bot Started

Commands:
✅ /check
✅ /add_spend
✅ /redeem
✅ /parse_guestlist
✅ /top
✅ /history

=================================
"""
    )



    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )



    # Commands

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    app.add_handler(
        CommandHandler(
            "check",
            check
        )
    )


    app.add_handler(
        CommandHandler(
            "add_spend",
            add_spend
        )
    )


    app.add_handler(
        CommandHandler(
            "redeem",
            redeem
        )
    )


    app.add_handler(
        CommandHandler(
            "parse_guestlist",
            parse_guestlist
        )
    )


    app.add_handler(
        CommandHandler(
            "top",
            top
        )
    )


    app.add_handler(
        CommandHandler(
            "history",
            history
        )
    )


    # Guestlist workflow
    #
    # 1. Paste list
    # 2. Preview
    # 3. YES / NO


    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_guestlist_paste
        )
    )


    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            confirm_guestlist
        )
    )



    # Error handling

    app.add_error_handler(
        error_handler
    )



    try:

        app.run_polling(
            poll_interval=0.5
        )


    except KeyboardInterrupt:

        print(
            "\n❌ Bot stopped"
        )

        sys.exit(0)




# ==========================================
# Windows Compatibility
# ==========================================


if __name__ == "__main__":


    if sys.platform == "win32":

        import asyncio

        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )


    main()
