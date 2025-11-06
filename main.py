import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, PhotoSize, Document
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
    media_files: List[Dict] = field(default_factory=list)

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
    admin_viewing_images = State()


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
                created_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
                messages=[]
            )
        return self.chats[user_id]

    def add_message(self, user_id: int, sender_type: str, sender_id: int, sender_name: str, text: str,
                    media_files: List[Dict] = None):
        """Безопасно добавляет сообщение"""
        if user_id in self.chats:
            safe_text = truncate_text(text or "")
            safe_name = (sender_name or "Пользователь")[:100]
            msg = ChatMessage(
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=safe_name,
                text=safe_text,
                timestamp=datetime.now().strftime("%d.%m.%Y %H:%M"),
                media_files=media_files or []
            )
            self.chats[user_id].messages.append(msg)
            self.save()

    def get_chat_preview(self, user_id: int, max_length: int = 50) -> str:
        if user_id not in self.chats:
            return ""
        messages = self.chats[user_id].messages
        if not messages:
            return "(нет сообщений)"
        last_msg = messages[-1]
        preview_text = last_msg.text[:max_length] if last_msg.text else f"[{len(last_msg.media_files)} файлов]"
        status_emoji = "🟢" if self.chats[user_id].status == ChatStatus.OPEN else "🔴"
        return f"{status_emoji} ...{preview_text}"

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

    def get_last_messages(self, user_id: int, count: int = 6) -> List[ChatMessage]:
        """Получить последние N сообщений"""
        if user_id not in self.chats:
            return []
        messages = self.chats[user_id].messages
        return messages[-count:] if len(messages) > count else messages


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
                "[🤖] 👋 Добро пожаловать в техподдержку!\n\n"
                "Напишите вашу проблему, и мы вам поможем."
            )
    except Exception as e:
        print(f"Ошибка в start: {e}")


async def notify_admins_about_message(user_id: int, user_name: str):
    """Отправляет уведомление админам при новом сообщении с медиа"""
    for admin_id in ADMIN_IDS:
        try:
            chat_preview = storage.get_chat_preview(user_id, max_length=30)
            await bot.send_message(
                admin_id,
                f"📩 Новое сообщение от пользователя:\n"
                f"👤 {user_name}\n"
                f"{chat_preview}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔗 Открыть чат", callback_data=f"chat_{user_id}")]
                ])
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления админу {admin_id}: {e}")


@dp.message(StateFilter(None), F.from_user.id.not_in(ADMIN_IDS), F.photo)
async def user_photo(message: Message):
    try:
        user_id = message.from_user.id
        chat = storage.add_or_get_chat(user_id, message.from_user.full_name)
        was_closed = chat.status == ChatStatus.CLOSED.value
        if was_closed:
            storage.set_chat_status(user_id, ChatStatus.OPEN.value)
        photo = message.photo[-1]
        caption = message.caption or ""
        storage.add_message(
            user_id=user_id,
            sender_type="user",
            sender_id=message.from_user.id,
            sender_name=message.from_user.full_name,
            text=caption,
            media_files=[{
                "type": "photo",
                "file_id": photo.file_id,
                "file_unique_id": photo.file_unique_id,
                "caption": caption
            }]
        )
        if was_closed:
            await message.answer(
                "[🤖] 🔄 Ваш чат был закрыт. Он открыт заново.\n"
                "✅ Ваше фото отправлено в техподдержку\n"
                "⏳ Ожидайте ответа..."
            )
        await notify_admins_about_message(user_id, message.from_user.full_name)
    except Exception as e:
        print(f"Ошибка в user_photo: {e}")
        await message.answer("❌ Ошибка при обработке фото")


@dp.message(StateFilter(None), F.from_user.id.not_in(ADMIN_IDS), F.document)
async def user_document(message: Message):
    try:
        user_id = message.from_user.id
        chat = storage.add_or_get_chat(user_id, message.from_user.full_name)
        was_closed = chat.status == ChatStatus.CLOSED.value
        if was_closed:
            storage.set_chat_status(user_id, ChatStatus.OPEN.value)
        doc = message.document
        caption = message.caption or ""
        storage.add_message(
            user_id=user_id,
            sender_type="user",
            sender_id=message.from_user.id,
            sender_name=message.from_user.full_name,
            text=caption,
            media_files=[{
                "type": "document",
                "file_id": doc.file_id,
                "file_unique_id": doc.file_unique_id,
                "file_name": doc.file_name or "Документ",
                "caption": caption
            }]
        )
        if was_closed:
            await message.answer(
                "[🤖] 🔄 Ваш чат был закрыт. Он открыт заново.\n"
                "✅ Ваш документ отправлен в техподдержку\n"
                "⏳ Ожидайте ответа..."
            )
        await notify_admins_about_message(user_id, message.from_user.full_name)
    except Exception as e:
        print(f"Ошибка в user_document: {e}")
        await message.answer("❌ Ошибка при обработке документа")


@dp.message(StateFilter(None), F.from_user.id.not_in(ADMIN_IDS))
async def user_message(message: Message):
    try:
        user_id = message.from_user.id
        text = message.text or ""
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
                "[🤖] 🔄 Ваш чат был закрыт. Он открыт заново.\n"
                "✅ Ваше новое сообщение отправлено в техподдержку\n"
                "⏳ Ожидайте ответа..."
            )
        await notify_admins_about_message(user_id, message.from_user.full_name)
    except Exception as e:
        print(f"Ошибка в user_message: {e}")
        await message.answer("❌ Ошибка при обработке сообщения")


def get_chats_keyboard(chats_list: List[tuple], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    if not chats_list:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")]
        ])
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_chats = chats_list[start_idx:end_idx]
    keyboard = []
    for user_id, user_name in page_chats:
        preview = storage.get_chat_preview(user_id, max_length=25)
        btn_text = f"👤 {user_name}\n{preview}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"chat_{user_id}_0")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page_all_{page - 1}"))
    if end_idx < len(chats_list):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page_all_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить сообщение",
                                                                       callback_data="delete_message")]])


@dp.callback_query(F.data == "delete_message")
async def delete_message_handler(query: CallbackQuery):
    await query.message.delete()
    await query.answer()


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
        text = f"📋 Все чаты ({len(chats_list)})\n⏳ Ожидающих ответа: {unread}"
        if not chats_list:
            text = "❌ Нет чатов"
        await query.message.edit_text(
            text,
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
        text = f"⏳ Чаты ожидающие ответа ({len(chats_list)})"
        if not chats_list:
            text = "❌ Нет чатов"
        await query.message.edit_text(
            text,
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
        text = f"✅ Закрытые чаты ({len(chats_list)})"
        if not chats_list:
            text = "❌ Нет чатов"
        await query.message.edit_text(
            text,
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


def build_chat_display_text(chat: VirtualChat, page: int = 0, char_limit: int = 4000) -> tuple[str, int]:
    """
    Формирует текст отображения чата с глобальной нумерацией медиа и пагинацией.
    Разбивает чат на страницы если больше char_limit символов.
    Args:
        chat: объект чата VirtualChat
        page: номер страницы (начиная с 0)
        char_limit: лимит символов на страницу (по умолчанию 4000)
    Returns:
        (текст_страницы, общее_количество_страниц)
    """
    if not chat.messages:
        return "(нет сообщений)", 1
    full_text = ""
    photo_count = 0
    doc_count = 0
    for msg in chat.messages:
        try:
            sender_label = "👤" if msg.sender_type == "user" else "👨‍💻"
            dt = datetime.strptime(msg.timestamp, "%d.%m.%Y %H:%M")
            time = dt.strftime("%d.%m.%Y %H:%M")
            text_content = msg.text if msg.text else ""
            if msg.media_files:
                media_info = ""
                for media in msg.media_files:
                    if media["type"] == "photo":
                        photo_count += 1
                        media_info += f"📷 Изображение №{photo_count}\n"
                    elif media["type"] == "document":
                        doc_count += 1
                        media_info += f"📄 {media.get('file_name', 'Документ')} №{doc_count}\n"
                text_content = (text_content + "\n" if text_content else "") + media_info
            full_text += f"{sender_label} {msg.sender_name} ({time}):\n{text_content}\n\n"
        except Exception as e:
            print(f"Ошибка форматирования сообщения: {e}")
            continue
    header = f"💬 {chat.user_name}\n"
    header += f"Статус: {'🟢 Открыт' if chat.status == ChatStatus.OPEN else '🔴 Закрыт'}\n"
    header += "═" * 32 + "\n\n"
    total_text = header + full_text
    if len(total_text) <= char_limit:
        return truncate_text(total_text), 1
    pages = []
    current_page_text = ""
    for line in full_text.split("\n\n"):
        if line.strip():
            potential_text = current_page_text + line + "\n\n"
            if len(header + potential_text) <= char_limit:
                current_page_text = potential_text
            else:
                if current_page_text:
                    pages.append(header + current_page_text)
                current_page_text = line + "\n\n"
    if current_page_text:
        pages.append(header + current_page_text)
    if not pages:
        pages = [header + "Ошибка при формировании страниц"]
    total_pages = len(pages)
    if page >= total_pages:
        page = total_pages - 1
    page_text = pages[page]
    page_text += f"\n\n📄 Страница {page + 1}/{total_pages}"
    return truncate_text(page_text), total_pages


def build_last_messages_preview(messages: List[ChatMessage]) -> str:
    """Формирует текст с последними 6 сообщениями для предпросмотра"""
    if not messages:
        return "<b>📋 История чата (последние 6 сообщений):</b>\n\n<i>(сообщений нет)</i>"
    text = "<b>📋 История чата (последние 6 сообщений):</b>\n"
    text += "=" * 32 + "\n\n"
    for msg in messages:
        sender_label = "👤 Пользователь" if msg.sender_type == "user" else "🔧 Администратор"
        text += f"<b>{sender_label}</b> [{msg.timestamp}]\n"

        if msg.text:
            text += f"{msg.text}\n"

        if msg.media_files:
            for media in msg.media_files:
                if media['type'] == 'photo':
                    text += "[🖼️ Фото]\n"
                elif media['type'] == 'document':
                    text += f"[📄 {media.get('file_name', 'Документ')}]\n"

        text += "\n"

    text += "=" * 32 + "\n"
    return text


def build_chat_keyboard(user_id: int, chat_page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Формирует клавиатуру для просмотра чата с поддержкой пагинации"""
    chat = storage.chats[user_id]
    image_count = 0
    doc_count = 0
    for msg in chat.messages:
        for media in msg.media_files:
            if media["type"] == "photo":
                image_count += 1
            elif media["type"] == "document":
                doc_count += 1
    keyboard = []
    if total_pages > 1:
        nav_buttons = []
        if chat_page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"chat_page_{user_id}_{chat_page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{chat_page + 1}/{total_pages}", callback_data="noop"))
        if chat_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"chat_page_{user_id}_{chat_page + 1}"))
        keyboard.append(nav_buttons)
    if image_count > 0:
        keyboard.append([InlineKeyboardButton(text=f"📸 Изображения ({image_count})",
                                              callback_data=f"view_images_{user_id}")])
    if doc_count > 0:
        keyboard.append([InlineKeyboardButton(text=f"📄 Документы ({doc_count})",
                                              callback_data=f"view_docs_{user_id}")])
    keyboard.extend([
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}"),
         InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{user_id}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data=f"close_{user_id}"),
         InlineKeyboardButton(text="🔁 Открыть", callback_data=f"open_{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_view_all")]
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.callback_query(F.data.startswith("chat_page_"))
async def change_chat_page(query: CallbackQuery, state: FSMContext):
    """Переключение между страницами чата"""
    try:
        parts = query.data.split("_")
        user_id = int(parts[2])
        new_page = int(parts[3])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        await state.update_data(selected_chat_id=user_id, chat_page=new_page)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=new_page)
        keyboard = build_chat_keyboard(user_id, chat_page=new_page, total_pages=total_pages)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        print(f"Ошибка в change_chat_page: {e}")


@dp.callback_query(F.data == "noop")
async def noop_handler(query: CallbackQuery):
    """Заглушка для кнопки с номером страницы"""
    await query.answer()


@dp.callback_query(F.data.startswith("chat_"))
async def admin_view_chat(query: CallbackQuery, state: FSMContext):
    try:
        parts = query.data.split("_")
        user_id = int(parts[1])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        await state.update_data(selected_chat_id=user_id, chat_page=last_page)
        await state.set_state(SupportStates.admin_viewing_chat)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_view_chat: {e}")


@dp.callback_query(F.data.startswith("view_images_"))
async def view_images_menu(query: CallbackQuery, state: FSMContext):
    try:
        user_id = int(query.data.split("_")[2])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        chat = storage.chats[user_id]
        images = []
        for msg in chat.messages:
            for media in msg.media_files:
                if media["type"] == "photo":
                    images.append(media)
        if not images:
            await query.answer("❌ Нет изображений в чате", show_alert=True)
            return
        await state.update_data(selected_chat_id=user_id, chat_images=images, viewing_images=True)
        await state.set_state(SupportStates.admin_viewing_images)
        keyboard = []
        for i in range(len(images)):
            keyboard.append(
                [InlineKeyboardButton(text=f"📷 Изображение №{i + 1}", callback_data=f"select_image_{user_id}_{i}")])
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chat_{user_id}_0")])
        await query.message.edit_text(
            f"📸 Выберите изображение ({len(images)} всего):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в view_images_menu: {e}")


@dp.callback_query(F.data.startswith("select_image_"))
async def select_image(query: CallbackQuery, state: FSMContext):
    try:
        parts = query.data.split("_")
        user_id = int(parts[2])
        image_index = int(parts[3])
        data = await state.get_data()
        images = data.get("chat_images", [])
        if image_index >= len(images):
            await query.answer("❌ Изображение не найдено", show_alert=True)
            return
        selected_image = images[image_index]
        try:
            await bot.send_photo(
                query.from_user.id,
                selected_image["file_id"],
                caption=selected_image.get("caption", ""),
                reply_markup=get_delete_keyboard()
            )
        except Exception as e:
            print(f"Ошибка отправки изображения: {e}")
        await state.update_data(viewing_images=False)
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        print(f"Ошибка в select_image: {e}")


@dp.callback_query(F.data.startswith("view_docs_"))
async def view_docs_menu(query: CallbackQuery, state: FSMContext):
    try:
        user_id = int(query.data.split("_")[2])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        chat = storage.chats[user_id]
        docs = []
        for msg in chat.messages:
            for media in msg.media_files:
                if media["type"] == "document":
                    docs.append(media)
        if not docs:
            await query.answer("❌ Нет документов в чате", show_alert=True)
            return
        await state.update_data(selected_chat_id=user_id, chat_docs=docs, viewing_docs=True)
        await state.set_state(SupportStates.admin_viewing_images)
        keyboard = []
        for i in range(len(docs)):
            doc_name = docs[i].get("file_name", "Документ")
            keyboard.append(
                [InlineKeyboardButton(text=f"📄 {doc_name}", callback_data=f"select_doc_{user_id}_{i}")])
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chat_{user_id}_0")])
        await query.message.edit_text(
            f"📄 Выберите документ ({len(docs)} всего):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в view_docs_menu: {e}")


@dp.callback_query(F.data.startswith("select_doc_"))
async def select_document(query: CallbackQuery, state: FSMContext):
    try:
        parts = query.data.split("_")
        user_id = int(parts[2])
        doc_index = int(parts[3])
        data = await state.get_data()
        docs = data.get("chat_docs", [])
        if doc_index >= len(docs):
            await query.answer("❌ Документ не найден", show_alert=True)
            return
        selected_doc = docs[doc_index]
        try:
            await bot.send_document(
                query.from_user.id,
                selected_doc["file_id"],
                caption=selected_doc.get("caption", ""),
                reply_markup=get_delete_keyboard()
            )
        except Exception as e:
            print(f"Ошибка отправки документа: {e}")
        await state.update_data(viewing_docs=False)
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        print(f"Ошибка в select_document: {e}")


@dp.callback_query(F.data.startswith("refresh_"))
async def refresh_chat(query: CallbackQuery, state: FSMContext):
    """Обновляет чат и открывает последнюю страницу"""
    try:
        user_id = int(query.data.split("_")[1])
        if user_id not in storage.chats:
            await query.answer("❌ Чат не найден", show_alert=True)
            return
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        await state.update_data(selected_chat_id=user_id, chat_page=last_page)
        await state.set_state(SupportStates.admin_viewing_chat)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
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
                "[🤖] ❌ Ваш чат был закрыт администратором.\n"
                "Если у вас есть еще вопросы, напишите /start чтобы создать новый чат.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю: {e}")
        await query.answer("✅ Чат закрыт")
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        messages_text += "\n\n🔴 Чат закрыт администратором"
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
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
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
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
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"chat_{user_id}_0")]
            ])
        )
        await query.answer()
    except Exception as e:
        print(f"Ошибка в admin_reply_prompt: {e}")


@dp.message(SupportStates.admin_replying, F.photo)
async def admin_send_photo_reply(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data.get("selected_chat_id")
        if not user_id or user_id not in storage.chats:
            await message.answer("❌ Ошибка: чат не найден")
            await state.clear()
            return
        photo = message.photo[-1]
        caption = message.caption or ""
        storage.add_message(
            user_id=user_id,
            sender_type="admin",
            sender_id=message.from_user.id,
            sender_name="Администратор",
            text=caption,
            media_files=[{
                "type": "photo",
                "file_id": photo.file_id,
                "file_unique_id": photo.file_unique_id,
                "caption": caption
            }]
        )
        try:
            await bot.send_photo(
                user_id,
                photo.file_id,
                caption=caption if caption else None
            )
        except Exception as e:
            print(f"Ошибка отправки фото пользователю: {e}")
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await message.answer(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    except Exception as e:
        print(f"Ошибка в admin_send_photo_reply: {e}")
        await message.answer("❌ Произошла ошибка при отправке фото")
        await state.clear()


@dp.message(SupportStates.admin_replying, F.document)
async def admin_send_document_reply(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data.get("selected_chat_id")
        if not user_id or user_id not in storage.chats:
            await message.answer("❌ Ошибка: чат не найден")
            await state.clear()
            return
        doc = message.document
        caption = message.caption or ""
        storage.add_message(
            user_id=user_id,
            sender_type="admin",
            sender_id=message.from_user.id,
            sender_name="Администратор",
            text=caption,
            media_files=[{
                "type": "document",
                "file_id": doc.file_id,
                "file_unique_id": doc.file_unique_id,
                "file_name": doc.file_name or "Документ",
                "caption": caption
            }]
        )
        try:
            await bot.send_document(
                user_id,
                doc.file_id,
                caption=caption if caption else None
            )
        except Exception as e:
            print(f"Ошибка отправки документа пользователю: {e}")
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await message.answer(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    except Exception as e:
        print(f"Ошибка в admin_send_document_reply: {e}")
        await message.answer("❌ Произошла ошибка при отправке документа")
        await state.clear()


@dp.message(SupportStates.admin_replying, F.text)
async def admin_send_text_reply(message: Message, state: FSMContext):
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
            await bot.send_message(
                user_id,
                reply_text,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка отправки пользователю: {e}")
        await state.set_state(SupportStates.admin_viewing_chat)
        chat = storage.chats[user_id]
        messages_text, total_pages = build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = build_chat_display_text(chat, page=last_page)
        keyboard = build_chat_keyboard(user_id, chat_page=last_page, total_pages=total_pages)
        await message.answer(messages_text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    except Exception as e:
        print(f"Ошибка в admin_send_text_reply: {e}")
        await message.answer("❌ Произошла ошибка при отправке ответа")
        await state.clear()


@dp.error()
async def error_handler(exception):
    print(f"❌ Необработанная ошибка: {exception}")


async def cleanup_closed_chats(storage):
    while True:
        now = datetime.now()
        chats_to_delete = []
        for uid, chat in list(storage.chats.items()):
            if chat.status == ChatStatus.CLOSED.value and chat.messages:
                last_msg_time = datetime.strptime(chat.messages[-1].timestamp, "%d.%m.%Y %H:%M")
                if now - last_msg_time > timedelta(weeks=2):
                    chats_to_delete.append(uid)
        for uid in chats_to_delete:
            del storage.chats[uid]
        if chats_to_delete:
            storage.save()
        await asyncio.sleep(3600)


async def auto_close_inactive_chats(storage):
    while True:
        now = datetime.now()
        for chat in storage.chats.values():
            if chat.status == ChatStatus.OPEN.value and chat.messages:
                last_msg_time = datetime.strptime(chat.messages[-1].timestamp, "%d.%m.%Y %H:%M")
                if now - last_msg_time > timedelta(days=2):
                    chat.status = ChatStatus.CLOSED.value
                    storage.save()
        await asyncio.sleep(1800)


async def on_startup():
    asyncio.create_task(cleanup_closed_chats(storage))
    asyncio.create_task(auto_close_inactive_chats(storage))


async def main():
    print("🤖 Бот техподдержки запущен...")
    await on_startup()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
