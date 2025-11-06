from typing import List, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class Keyboard:
    @staticmethod
    def chat(storage, user_id: int, open_status: str, chat_page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
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
            nav_buttons.append(InlineKeyboardButton(text=f"{chat_page + 1}/{total_pages}",
                                                    callback_data=f"chat_page_{user_id}_{total_pages - 1}"))
            if chat_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"chat_page_{user_id}_{chat_page + 1}"))
            keyboard.append(nav_buttons)
        media_count = image_count + doc_count
        if media_count > 0:
            keyboard.append([
                InlineKeyboardButton(text=f"🗂 Медиафайлы ({media_count})",callback_data=f"show_media_{user_id}")
            ])
        status_button_text = "🔴 Закрыть" if chat.status == open_status else "🟢 Открыть"
        keyboard.extend([
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{user_id}"),
            InlineKeyboardButton(text=status_button_text, callback_data=f"toggle_chat_{user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_view_all")]
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)


    @staticmethod
    def chats(storage, chats_list: List[tuple], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
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


    @staticmethod
    def language() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇺🇸", callback_data="lang_en"),
            ]
        ])


    @staticmethod
    def delete() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑", callback_data="delete_message")]])


    @staticmethod
    def open_chat(user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть чат", callback_data=f"chat_{user_id}")]])


    @staticmethod
    def cancel_reply(user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"chat_{user_id}_0")]])


    @staticmethod
    def admin_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все чаты", callback_data="admin_view_all")],
            [InlineKeyboardButton(text="⏳ Ожидающие ответа", callback_data="admin_view_waiting")],
            [InlineKeyboardButton(text="✅ Закрытые", callback_data="admin_view_closed")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]])


    @staticmethod
    def user_help(help_text) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=help_text,
                                                                           callback_data="user_help")]])
