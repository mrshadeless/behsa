import json
import random
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime
import logging
import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram import Bot, BotCommand

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture more detailed logs
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Ensure logging level is set to INFO

required_env_vars = ['TELEGRAM_TOKEN', 'DYNAMODB_TABLE', 'S3_BUCKET_NAME', 'S3_KEY_FILE']
for var in required_env_vars:
    if var not in os.environ:
        logger.error(f"Environment variable '{var}' is not set.")
        raise EnvironmentError(f"Required environment variable '{var}' is missing.")

# Initialize Services
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
bot = telegram.Bot(token=os.environ['TELEGRAM_TOKEN'])
bucket_name = os.getenv("S3_BUCKET_NAME")  # Replace with actual bucket
key_file = os.getenv("S3_KEY_FILE")  # Path to the JSON file
lambda_client = boto3.client('lambda')
s3 = boto3.client("s3")

# Lambda Handler
def lambda_handler(event, context):
    if "body" in event:  # Telegram webhook
        logger.info(f"Telegram webhook received: {event}")
        process_telegram_event(event)
    else:
        logger.warning("Unknown event source")
        return {"statusCode": 400, "body": "Unsupported event source"}
    return {"statusCode": 200, "body": json.dumps('Message processed')}

# Function to Process callback data
def process_callback_data(user_id, update):
    logger.info(f"Processing a callback query from user {user_id}")
    callback_data = update.callback_query.data  # Extract the callback data
    # Process the rating callback
    if callback_data.startswith("register_"):
        response = str(callback_data.split("_")[1])
        handle_register_response(user_id, update, response)

# Function to handle Telegram events (existing logic)
def process_telegram_event(event):
    # Parse the incoming update from Telegram
    # logger.info(f"An Event received: {event}")
    update = telegram.Update.de_json(json.loads(event['body']), bot)

    # Handle callback query (inline keyboard responses)
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)  # Extract user_id
        logger.info(f"A callback query was received from user {user_id}")
        process_callback_data(user_id, update)

    # Check if the update contains a message
    elif update.message:
        chat_id = update.message.chat_id
        user_id = str(update.message.from_user.id)
        logger.info(f"A Message from User: {user_id}")

        # Check Commands

        # Handle the /start command
        if update.message.text == '/start':
            logger.info(f" User {user_id} started the bot with /start")
            # Send a welcome message
            welcome_message = """
            با سلام.
            به <نام بات> خوش آمدید.
            باانتخاب گزینه فال از منو می توانید فال بگیرید
            یا برای دریافت روزانه غزلهای حافظ ثبت نام کنید .
            """
            bot.send_message(chat_id=chat_id, text=make_rtl(welcome_message))

        elif update.message.text == '/horoscope':
            logger.info(f" User {user_id} asked for a random horoscope with /horoscope")
            try:
                # Fetch the JSON file from S3
                response = s3.get_object(Bucket=bucket_name, Key=key_file)
                materials = json.loads(response['Body'].read().decode('utf-8'))

                # Select a random ghazal number
                random_key = random.choice(list(materials.keys()))  # Select a random key from JSON
                ghazal = materials[random_key]  # Retrieve corresponding poem
                message = f"""
                غزل شماره {random_key}
                {ghazal}
                """
                bot.send_message(chat_id=chat_id, text=make_rtl(message))
            except Exception as e:
                logger.error(f"Error fetching materials from S3: {e}", exc_info=True)
                return {}

        elif update.message.text == '/dailyhoroscope':
            logger.info(f"/dailyhoroscope")
            daily_horoscope_setting(user_id)

        # Handle the /about command (optional)
        elif update.message.text == '/about':
            logger.info(f"/about")
            about_message = """
            از <نام بات> می توانید برای گرفتن فال حافظ و یا دریافت روزانه غزلهای حافظ استفاده کنید.
            باانتخاب گزینه فال از منو می توانید فال بگیرید
            یا برای دریافت روزانه غزلهای حافظ ثبت نام کنید .
            """
            bot.send_message(chat_id=chat_id, text=make_rtl(about_message))


        # Handle the /help command (optional)
        elif update.message.text == '/help':
            logger.info(f"/help")
            help_message = """
            /start - شروع
            /about - درباره
            /horoscope - فال
            /daily-horoscope - تنظیمات دریافت غزل بصورت روزانه
            """
            bot.send_message(chat_id=chat_id, text=make_rtl(help_message))


    return {
        'statusCode': 200,
        'body': json.dumps('Message processed')
    }

# Fuction for /daily_horoscope_setting
def daily_horoscope_setting(user_id):
    test_db = test_dynamodb_connection()
    if test_db == True:
        try:
            # Send the feedback request
            message = """
            تنظیمات دریافت غزل بصورت روزانه
            """
            # Create a keyboard with Yes/No options for confirmation
            keyboard = [
                [{"text": "فعال", "callback_data": f"register_y"}],
                [{"text": "غیرفعال", "callback_data": f"register_n"}],
            ]
            reply_markup = {"inline_keyboard": keyboard}
            bot.send_message(chat_id=user_id, text=make_rtl(message), reply_markup=reply_markup)
            logger.info(f"Confirmation request sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send Restart request to user {user_id}: {e}", exc_info=True)
    else:
        logger.error(f"DynamoDB is not available")

# Handle the Response to a user
def handle_register_response(user_id, update, response):
    try:
        if not user_exists(user_id):  # User does NOT exist
            if response == "y":
                # Register User
                logger.info(f"Registering new user {user_id}")
                table.put_item(
                    Item={
                        'user_id': user_id,
                    }
                )
                message = """تنظیمات اعمال شد."""
            else:
                message = "تنظیمات اعمال شد."
        else:  # User exists
            if response == "n":
                # Remove User
                logger.info(f"Removing user {user_id}")
                table.delete_item(Key={'user_id': user_id})
                message = "تنظیمات اعمال شد."
            else:
                message = "تنظیمات اعمال شد."

        # Replace the original message with a confirmation
        bot.edit_message_text(
            chat_id=user_id,
            message_id=update.callback_query.message.message_id,
            text=make_ltr(message),
            reply_markup=None  # Removes the inline keyboard
        )

    except Exception as e:
        logger.error(f"Error handling user registration: {str(e)}")

def user_exists(user_id):
    """Check if the user already exists in DynamoDB"""
    response = table.get_item(Key={'user_id': user_id})
    return 'Item' in response  # Returns True if user exists, False otherwise

def test_dynamodb_connection():
    try:
        dynamodb_client = boto3.client('dynamodb')
        table_name = os.environ.get('DYNAMODB_TABLE')
        if not table_name:
            logger.error(f"Error: DYNAMODB_TABLE environment variable is not set.")

        # Attempt to describe the table
        response = dynamodb_client.describe_table(TableName=table_name)
        logger.info(f"Table '{table_name}' is accessible. Status: {response['Table']['TableStatus']}")
        return True

    except Exception as e:
        logger.error(f"Error accessing table '{table_name}': {str(e)}")
        return False

# Function to send and pin a message
def send_and_pin_message(chat_id, text):
    # Send the message
    sent_message = bot.send_message(chat_id=chat_id, text=text)
    # Pin the message
    bot.pin_chat_message(chat_id=chat_id, message_id=sent_message.message_id)

# Function to send long messages
def send_long_message(bot, chat_id, message, max_length=4096):
    """
    Splits a long message and sends it in chunks to Telegram.
    """
    for i in range(0, len(message), max_length):
        bot.send_message(chat_id=chat_id, text=message[i:i + max_length])

# Fuction to make text right to left
def make_rtl(text):
    return "\u202B" + "\n".join(line.strip() for line in text.split("\n")) + "\u202C"

# Fuction to make text right to left
def make_ltr(text):
    return "\u202A" + "\n".join(line.strip() for line in text.split("\n")) + "\u202C"  # LRE (Start LTR) + Text + PDF (End)

# Create Menu
def set_bot_menu():
    commands = [
        BotCommand("start", "شروع"),
        BotCommand("about", "درباره"),
        BotCommand("horoscope", "فال حافظ"),
        BotCommand("dailyhoroscope", "تنظیمات دریافت غزل بصورت روزانه"),
    ]
    bot.set_my_commands(commands)  # This automatically enables the menu button

    print("Commands set successfully!")
# Call this ONCE per deployment (not on every request)
set_bot_menu()