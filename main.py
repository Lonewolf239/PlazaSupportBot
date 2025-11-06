import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
STORAGE_FILE = "chats_storage.json"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class ChatStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"

def escape_markdown(text: str) -> str:
    """Экранирует опасные символы Markdown"""
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text

def truncate_text(text: str, max_length: int = 4096) -> str:
    """Обрезает текст до максимальной длины"""
    if not text:
        return ""
    return text[:max_length]

@dataclass
class ChatMessage:
    sender_type: str
    sender_id: int
    sender_name: str
    text: str
    timestamp: str

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return ChatMessage(**data)

@dataclass
class VirtualChat:
    user_id: int
    user_name: str
    created_at: str
    messages: List[ChatMessage]
    status: str = ChatStatus.OPEN.value
    assigned_admin: Optional[int] = None

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "created_at": self.created_at,
            "messages": [msg.to_dict() for msg in self.messages],
            "status": self.status,
            "assigned_admin": self.assigned_admin
        }

    @staticmethod
    def from_dict(data):
        messages = [ChatMessage.from_dict(msg) for msg in data.get("messages", [])]
        return VirtualChat(
            user_id=data["user_id"],
            user_name=data["user_name"],
            created_at=data["created_at"],
            messages=messages,
            status=data.get("status", ChatStatus.OPEN.value),
            assigned_admin=data.get("assigned_admin")
        )

class SupportStates(StatesGroup):
    admin_browsing = State()
    admin_viewing_chat = State()
    admin_replying = State()

class AdvancedChatStorage:
    def __init__(self, filename: str):
        self.filename = filename
        self.chats: Dict[int, VirtualChat] = {}
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.chats = {
                        int(user_id): VirtualChat.from_dict(chat_data)
                        for user_id, chat_data in data.items()
                    }
            except Exception as e:
                print(f"Ошибка загрузки: {e}")
                self.chats = {}

    def save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                data = {str(user_id): chat.to_dict() for user_id, chat in self.chats.items()}
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")

    def add_or_get_chat(self, user_id: int, user_name: str) -> VirtualChat:
        if user_id not in self.chats:
            self.chats[user_id] = VirtualChat(
                user_id=user_id,
                user_name=user_name or "Неизвестный пользователь",
                created_at = datetime.now().strftime("%d.%m.%Y %H:%M"),
                messages=[]
            )
        return self.chats[user_id]

    def add_message(self, user_id: int, sender_type: str, sender_id: int, sender_name: str, text: str):
        """Безопасно добавляет сообщение"""
        if user_id in self.chats:
            safe_text = truncate_text(text or "")
            safe_name = (sender_name or "Пользователь")[:100]
            msg = ChatMessage(
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=safe_name,
                text=safe_text,
                timestamp=datetime.now().strftime("%d.%m.%Y %H:%M")
            )
            self.chats[user_id].messages.append(msg)
            self.save()

    def get_chat_preview(self, user_id: int, max_length: int = 50) -> str:
        if user_id not in self.chats:
            return ""
        messages = self.chats[user_id].messages
        if not messages:
            return "(нет сообщений)"
        last_msg = messages[-1].text[:max_length]
        status_emoji = "🟢" if self.chats[user_id].status == ChatStatus.OPEN else "🔴"
        return f"{status_emoji} ...{last_msg}"

    def get_all_chats_list(self, filter_status: Optional[str] = None) -> List[tuple]:
        chats = [(uid, chat.user_name) for uid, chat in self.chats.items()]
        if filter_status:
            chats = [(uid, name) for uid, name in chats if self.chats[uid].status == filter_status]
        return chats

    def set_chat_status(self, user_id: int, status: str):
        if user_id in self.chats:
            self.chats[user_id].status = status
            self.save()

    def assign_admin(self, user_id: int, admin_id: int):
        if user_id in self.chats:
            self.chats[user_id].assigned_admin = admin_id
            self.save()

    def get_unread_count(self) -> int:
        """Чаты, ждущие ответа"""
        return sum(1 for chat in self.chats.values()
            if chat.status == ChatStatus.OPEN.value)

storage = AdvancedChatStorage(STORAGE_FILE)

@dp.message(Command("start"))
async def start(message: Message):
    try:
        user_id = message.from_user.id
        if user_id in ADMIN_IDS:
            await message.answer(
                "👨‍💻 Панель администратора\n\n"
                "Используйте кнопки ниже для управления чатами",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Все чаты", callback_data="admin_view_all")],
                    [InlineKeyboardButton(text="⏳ Ожидающие ответа", callback_data="admin_view_waiting")],
                    [InlineKeyboardButton(text="✅ Закрытые", callback_data="admin_view_closed")]
                ])
            )
        else:
            storage.add_or_get_chat(user_id, message.from_user.full_name)
            storage.set_chat_status(user_id, ChatStatus.OPEN.value)
            await message.answer(
                "👋 Добро пожаловать в техподдержку!\n\n"
                "Напишите вашу проблему, и мы вам поможем."
            )
    except Exception as e:
        print(f"Ошибка в start: {e}")
        await message.answer("❌ Произошла ошибка")

async def notify_admins_about_message(user_id: int, user_name: str):
    """Отправляет уведомление админам при новом сообщении"""
    for admin_id in ADMIN_IDS:
        try:
            chat_preview = storage.get_chat_preview(user_id, max_length=30)
            await bot.send_message(
                admin_id,
                f"📩 Новое сообщение от пользователя:\n"
                f"👤 {escape_markdown(user_name)}\n"
                f"{chat_preview}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔗 Открыть чат", callback_data=f"chat_{user_id}")]
                ])
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления админу {admin_id}: {e}")

@dp.message(StateFilter(None), F.from_user.id.not_in(ADMIN_IDS))
async def user_message(message: Message):
    try:
        user_id = message.from_user.id
        text = message.text or "(пусто)"
        chat = storage.add_or_get_chat(user_id, message.from_user.full_name)
        was_closed = chat.status == ChatStatus.CLOSED.value
        if was_closed:
            storage.set_chat_status(user_id, ChatStatus.OPEN.value)
        storage.add_message(
            user_id=user_id,
            sender_type="user",
            sender_id=user_id,
            sender_name=message.from_user.full_name,
            text=text
        )
        if was_closed:
            await message.answer(
                "🔄 Ваш чат был закрыт. Он открыт заново.\n"
                "✅ Ваше новое сообщение отправлено в техподдержку\n"
                "⏳ Ожидайте ответа..."
            )
            await notify_admins_about_message(user_id, message.from_user.full_name)
        else:
            await notify_admins_about_message(user_id, message.from_user.full_name)
    except Exception as e:
        print(f"Ошибка в user_message: {e}")
        await message.answer("❌ Ошибка при обработке сообщения")

def get_chats_keyboard(chats_list: List[tuple], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    if not chats_list:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Нет чатов", callback_data="admin_menu")]
        ])
    total_pages = (len(chats_list) + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_chats = chats_list[start_idx:end_idx]
    keyboard = []
    for user_id, user_name in page_chats:
        preview = storage.get_chat_preview(user_id, max_length=25)
        btn_text = f"👤 {user_name}\n{preview}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"chat_{user_id}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page_all_{page - 1}"))
    if end_idx < len(chats_list):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page_all_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data == "admin_menu")
async def admin_menu(query: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        await query.message.edit_text(
            "👨‍💻 Панель администратора",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Все чаты", callback_data="admin_view_all")],
                [InlineKeyboardButton(text="⏳ Ожидающие ответа", callback_data="admin_view_waiting")],
                [InlineKeyboardButton(text="✅ Закрытые", callback_data="admin_view_closed")]
            ])
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_menu: {e}")

@dp.callback_query(F.data == "admin_view_all")
async def admin_view_all(query: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(SupportStates.admin_browsing)
        chats_list = storage.get_all_chats_list()
        keyboard = get_chats_keyboard(chats_list, page=0)
        unread = storage.get_unread_count()
        await query.message.edit_text(
            f"📋 Все чаты ({len(chats_list)})\n⏳ Ожидающих ответа: {unread}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_view_all: {e}")

@dp.callback_query(F.data == "admin_view_waiting")
async def admin_view_waiting(query: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(SupportStates.admin_browsing)
        chats_list = storage.get_all_chats_list(filter_status=ChatStatus.OPEN.value)
        keyboard = get_chats_keyboard(chats_list, page=0)
        await query.message.edit_text(
            f"⏳ Чаты ожидающие ответа ({len(chats_list)})",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_view_waiting: {e}")

@dp.callback_query(F.data == "admin_view_closed")
async def admin_view_closed(query: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(SupportStates.admin_browsing)
        chats_list = storage.get_all_chats_list(filter_status=ChatStatus.CLOSED.value)
        keyboard = get_chats_keyboard(chats_list, page=0)
        await query.message.edit_text(
            f"✅ Закрытые чаты ({len(chats_list)})",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_view_closed: {e}")

@dp.callback_query(F.data.startswith("page_all_"))
async def admin_change_page(query: CallbackQuery):
    try:
        page = int(query.data.split("_")[2])
        chats_list = storage.get_all_chats_list()
        keyboard = get_chats_keyboard(chats_list, page=page)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_change_page: {e}")

def build_chat_display_text(chat: VirtualChat) -> str:
    """Формирует текст отображения чата"""
    messages_text = f"💬 {escape_markdown(chat.user_name)}\n"
    messages_text += f"Статус: {'🟢 Открыт' if chat.status == ChatStatus.OPEN else '🔴 Закрыт'}\n"
    messages_text += "═" * 40 + "\n\n"
    if not chat.messages:
        messages_text += "(нет сообщений)"
    else:
        for msg in chat.messages:
            try:
                sender_label = "👤" if msg.sender_type == "user" else "👨‍💻‍"
                dt = datetime.strptime(msg.timestamp, "%d.%m.%Y %H:%M")
                time = dt.strftime("%H:%M")
                safe_msg_text = escape_markdown(msg.text)
                messages_text += f"{sender_label} {escape_markdown(msg.sender_name)} ({time}):\n{safe_msg_text}\n\n"
            except Exception as e:
                print(f"Ошибка форматирования сообщения: {e}")
                continue
    return truncate_text(messages_text)

def build_chat_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Формирует клавиатуру для просмотра чата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data=f"close_{user_id}"),
        InlineKeyboardButton(text="🔄 Открыть", callback_data=f"open_{user_id}")],
        [InlineKeyboardButton(text="🔁 Обновить", callback_data=f"refresh_{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_view_all")]
    ])

@dp.callback_query(F.data.startswith("chat_"))
async def admin_view_chat(query: CallbackQuery, state: FSMContext):
    try:
        user_id = int(query.data.split("_")[1])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        await state.update_data(selected_chat_id=user_id)
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text = build_chat_display_text(chat)
        keyboard = build_chat_keyboard(user_id)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_view_chat: {e}")

@dp.callback_query(F.data.startswith("refresh_"))
async def refresh_chat(query: CallbackQuery, state: FSMContext):
    """Обновляет чат"""
    try:
        user_id = int(query.data.split("_")[1])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        await state.update_data(selected_chat_id=user_id)
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text = build_chat_display_text(chat)
        keyboard = build_chat_keyboard(user_id)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer("🔄 Чат обновлен")
    except Exception as e:
        print(f"Ошибка в refresh_chat: {e}")

@dp.callback_query(F.data.startswith("close_"))
async def close_chat(query: CallbackQuery):
    try:
        user_id = int(query.data.split("_")[1])
        storage.set_chat_status(user_id, ChatStatus.CLOSED.value)
        try:
            await bot.send_message(
                user_id,
                "❌ Ваш чат был закрыт администратором.\n"
                "Если у вас есть еще вопросы, напишите /start чтобы создать новый чат.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю: {e}")
        await query.answer("✅ Чат закрыт")
        chat = storage.chats[user_id]
        messages_text = build_chat_display_text(chat)
        messages_text += "\n\n🔴 Чат закрыт администратором"
        keyboard = build_chat_keyboard(user_id)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка в close_chat: {e}")

@dp.callback_query(F.data.startswith("open_"))
async def open_chat(query: CallbackQuery):
    try:
        user_id = int(query.data.split("_")[1])
        storage.set_chat_status(user_id, ChatStatus.OPEN.value)
        await query.answer("✅ Чат открыт")
        chat = storage.chats[user_id]
        messages_text = build_chat_display_text(chat)
        keyboard = build_chat_keyboard(user_id)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка в open_chat: {e}")

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_prompt(query: CallbackQuery, state: FSMContext):
    try:
        user_id = int(query.data.split("_")[1])
        await state.update_data(selected_chat_id=user_id)
        await state.set_state(SupportStates.admin_replying)
        await query.message.edit_text(
            "✍️ Напишите ответ пользователю:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"chat_{user_id}")]
            ])
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_reply_prompt: {e}")

@dp.message(SupportStates.admin_replying)
async def admin_send_reply(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data.get("selected_chat_id")
        if not user_id or user_id not in storage.chats:
            await message.answer("❌ Ошибка: чат не найден")
            await state.clear()
            return
        reply_text = message.text or "(пусто)"
        storage.add_message(
            user_id=user_id,
            sender_type="admin",
            sender_id=message.from_user.id,
            sender_name="Администратор",
            text=reply_text
        )
        try:
            safe_text = escape_markdown(reply_text)
            await bot.send_message(
                user_id,
                f"📨 Ответ от техподдержки:\n{safe_text}",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка отправки пользователю: {e}")
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text = build_chat_display_text(chat)
        keyboard = build_chat_keyboard(user_id)
        await message.answer(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    except Exception as e:
        print(f"Ошибка в admin_send_reply: {e}")
        await message.answer("❌ Произошла ошибка при отправке ответа")
        await state.clear()

@dp.error()
async def error_handler(exception):
    print(f"❌ Необработанная ошибка: {exception}")

async def main():
    print("🤖 Бот техподдержки запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
