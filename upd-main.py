import os
import json
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import spacy
from langdetect import detect

# Load environment variables
load_dotenv()

# Initialize bot and dispatcher
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Load spaCy models for English and Russian
nlp_en = spacy.load("en_core_web_sm")
nlp_ru = spacy.load("ru_core_news_sm")

# Admin user IDs (Add your user ID here)
ADMIN_IDS = [935535807]  # Replace with actual admin user IDs

# Define States for FSM
class Form(StatesGroup):
    waiting_for_request = State()

# Function to save the request in the appropriate folder
def save_request(user_id, message_text, category):
    folder_path = os.path.join('requests', category)
    os.makedirs(folder_path, exist_ok=True)  # Ensure the folder exists

    # Generate a filename based on category and current datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{category}_{timestamp}.json"
    file_path = os.path.join(folder_path, file_name)

    # Save the request details in the file
    new_request = {
        'order_number': f"#{user_id}_{timestamp}",
        'user_id': user_id,
        'message': message_text,
        'category': category,
        'timestamp': timestamp
    }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(new_request, f, ensure_ascii=False, indent=2)
    
    print(f"Saved request to {file_path}")  # Debugging information

# Function to categorize text based on basic keyword matching and spaCy NLP processing
def categorize_text(text):
    try:
        lang = detect(text)
    except:
        lang = "unknown"
    
    print(f"Detected language: {lang}")  # Debugging information

    # Use spaCy for entity recognition
    if lang == "ru":
        doc = nlp_ru(text)
    elif lang == "en":
        doc = nlp_en(text)
    else:
        return "gibberish"

    # Print detected entities for debugging
    print(f"Detected entities: {[ent.text for ent in doc.ents]}")

    # Keyword-based detection of categories
    personal_keywords = ["влад", "владислав", "vlad", "vladislav"]  # Add your name/nickname variations
    offer_keywords = ["offer", "ad", "advertisement", "work", "collaboration", "proposal", "job", "предложение", "реклама", "работа", "сотрудничество", "вакансия"]

    # Check for personal category: keywords and entity detection
    if any(ent.label_ == 'PERSON' for ent in doc.ents) or any(word.lower() in personal_keywords for word in text.lower().split()):
        print("Categorized as personal")  # Debugging information
        return "personal"

    # Check for offers
    if any(word.lower() in offer_keywords for word in text.lower().split()):
        print("Categorized as offers")  # Debugging information
        return "offers"

    # If no specific category is detected, classify as gibberish
    print("Categorized as gibberish")  # Debugging information
    return "gibberish"

# Function to generate inline keyboard with admin options for admin users
def get_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton(text="Отправить сообщение", callback_data="send_message")],
        [InlineKeyboardButton(text="Помощь", callback_data="help")]
    ]

    # Add admin buttons if the user is an admin
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(text="Статистика", callback_data="admin_stats")])
        keyboard.append([InlineKeyboardButton(text="Топ категории", callback_data="admin_top_categories")])
        keyboard.append([InlineKeyboardButton(text="Топ пользователей", callback_data="admin_top_users")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Async function to delete messages after a delay
async def delete_message_later(chat_id: int, message_id: int):
    await asyncio.sleep(60)  # Wait for 60 seconds
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")

# Start command handler
@dp.message(Command("start"))
async def start_command(message: types.Message):
    response = await message.answer("Здесь можно отправить сообщение лапчику", reply_markup=get_keyboard(message.from_user.id))
    asyncio.create_task(delete_message_later(message.chat.id, message.message_id))
    asyncio.create_task(delete_message_later(response.chat.id, response.message_id))

# Callback query handler for sending messages
@dp.callback_query(F.data == "send_message")
async def process_send_message(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_request)
    await callback_query.message.answer("Напишите ваш запрос", reply_markup=ReplyKeyboardRemove())
    await callback_query.answer()

# Callback query handler for help
@dp.callback_query(F.data == "help")
async def process_help(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Это бот для отправки сообщений. Нажмите 'Отправить сообщение', чтобы начать.")
    await callback_query.answer()

# Message handler for processing user requests
@dp.message(Form.waiting_for_request)
async def handle_request(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    request_text = message.text

    category = categorize_text(request_text)
    save_request(user_id, request_text, category)

    await state.clear()
    response = await message.answer("🥰 Запрос улетел", reply_markup=get_keyboard(user_id))
    asyncio.create_task(delete_message_later(message.chat.id, message.message_id))
    asyncio.create_task(delete_message_later(response.chat.id, response.message_id))

# Callback query handler for admin statistics
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback_query: types.CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS:
        await callback_query.answer("У вас нет доступа к этой команде.")
        return

    total_requests, unique_users = 0, 0
    category_counts = defaultdict(int)

    for category in ['gibberish', 'offers', 'personal']:
        folder_path = os.path.join('requests', category)
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith(".json"):
                    total_requests += 1
                    with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                        request_data = json.load(f)
                        category_counts[category] += 1

    stats_message = (
        f"Всего запросов: {total_requests}\n"
        f"Запросы по категориям:\n"
        f"- Gibberish: {category_counts['gibberish']}\n"
        f"- Offers: {category_counts['offers']}\n"
        f"- Personal: {category_counts['personal']}"
    )
    await callback_query.message.answer(stats_message)
    await callback_query.answer()

# Callback query handler for top categories
@dp.callback_query(F.data == "admin_top_categories")
async def admin_top_categories(callback_query: types.CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS:
        await callback_query.answer("У вас нет доступа к этой команде.")
        return

    all_categories = []

    for category in ['gibberish', 'offers', 'personal']:
        folder_path = os.path.join('requests', category)
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith(".json"):
                    all_categories.append(category)

    category_counts = Counter(all_categories)
    top_categories = category_counts.most_common(3)

    categories_message = "Топ категории:\n" + "\n".join(f"{cat}: {count}" for cat, count in top_categories)
    await callback_query.message.answer(categories_message)
    await callback_query.answer()

# Callback query handler for top users
@dp.callback_query(F.data == "admin_top_users")
async def admin_top_users(callback_query: types.CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS:
        await callback_query.answer("У вас нет доступа к этой команде.")
        return

    user_requests = defaultdict(int)

    for category in ['gibberish', 'offers', 'personal']:
        folder_path = os.path.join('requests', category)
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                if filename.endswith(".json"):
                    with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                        try:
                            request_data = json.load(f)
                            if isinstance(request_data, dict) and 'user_id' in request_data:
                                user_requests[request_data['user_id']] += 1
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON from file: {filename}")

    top_users = sorted(user_requests.items(), key=lambda x: x[1], reverse=True)[:5]
    top_users_message = "Топ пользователей:\n" + "\n".join(f"User {user_id}: {count} запросов" for user_id, count in top_users)
    await callback_query.message.answer(top_users_message)
    await callback_query.answer()

# Catch-all message handler for other messages
@dp.message()
async def handle_other_messages(message: types.Message):
    response = await message.answer("Чтобы отправить сообщение, нажмите кнопку 'Отправить сообщение'", reply_markup=get_keyboard(message.from_user.id))
    asyncio.create_task(delete_message_later(message.chat.id, message.message_id))
    asyncio.create_task(delete_message_later(response.chat.id, response.message_id))

# Main function to start the bot
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
