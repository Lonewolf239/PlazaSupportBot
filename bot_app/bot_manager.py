import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .chat_utils import ChatMessage, ChatStorage, VirtualChat, ChatStatus
from .utils import *
from .config import *


class SupportStates(StatesGroup):
    admin_browsing = State()
    admin_viewing_chat = State()
    admin_replying = State()
    admin_viewing_images = State()


# noinspection PyAsyncCall
class BotManager:
    def __init__(self, token: str, logger: logging.Logger):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.logger = logger
        self.language_manager = LanguageManager(LANGUAGES_FILE)
        self.storage = ChatStorage(STORAGE_FILE, self.logger)
        self._register_handlers()

    def _register_handlers(self):
        self.dp.message.register(self.start, Command("start"))
        self.dp.message.register(self.change_language, Command("change_language"))
        self.dp.callback_query.register(self.admin_help, F.data == "help")
        self.dp.callback_query.register(self.user_help, F.data == "user_help")
        self.dp.callback_query.register(self.set_language, F.data.in_(["lang_ru", "lang_en"]))
        self.dp.message.register(self.user_photo, StateFilter(None), F.from_user.id.not_in(ADMIN_IDS), F.photo)
        self.dp.message.register(self.user_document, StateFilter(None), F.from_user.id.not_in(ADMIN_IDS), F.document)
        self.dp.message.register(self.user_message, StateFilter(None), F.from_user.id.not_in(ADMIN_IDS))
        self.dp.callback_query.register(self.delete_message_handler, F.data == "delete_message")
        self.dp.callback_query.register(self.admin_menu, F.data == "admin_menu")
        self.dp.callback_query.register(self.admin_view_all, F.data == "admin_view_all")
        self.dp.callback_query.register(self.admin_view_waiting, F.data == "admin_view_waiting")
        self.dp.callback_query.register(self.admin_view_closed, F.data == "admin_view_closed")
        self.dp.callback_query.register(self.admin_change_page, F.data.startswith("page_all_"))
        self.dp.callback_query.register(self.change_chat_page, F.data.startswith("chat_page_"))
        self.dp.callback_query.register(self.admin_view_chat, F.data.startswith("chat_"))
        self.dp.callback_query.register(self.show_media_menu, F.data.startswith("show_media_"))
        self.dp.callback_query.register(self.select_media, F.data.startswith("select_media_"))
        self.dp.callback_query.register(self.refresh_chat, F.data.startswith("refresh_"))
        self.dp.callback_query.register(self.toggle_chat_status, F.data.startswith("toggle_chat_"))
        self.dp.callback_query.register(self.admin_reply_prompt, F.data.startswith("reply_"))
        self.dp.message.register(self.admin_send_photo_reply, SupportStates.admin_replying, F.photo)
        self.dp.message.register(self.admin_send_document_reply, SupportStates.admin_replying, F.document)
        self.dp.message.register(self.admin_send_text_reply, SupportStates.admin_replying, F.text)
        self.dp.error.register(self.error_handler)

    async def admin_send_reply(self, message: Message, state: FSMContext, media_type: str = None):
        error_message = "❌ Произошла ошибка при отправке ответа"
        try:
            data = await state.get_data()
            user_id = data.get("selected_chat_id")

            if not user_id or user_id not in self.storage.chats:
                await message.answer("❌ Ошибка: чат не найден")
                await state.clear()
                return

            media_files = []
            text = message.text or message.caption or ""

            if media_type == "photo":
                photo = message.photo[-1]
                text = text
                media_files = [{
                    "type": "photo",
                    "file_id": photo.file_id,
                    "file_unique_id": photo.file_unique_id,
                    "caption": text
                }]
                error_message = "❌ Произошла ошибка при отправке фото"
                try:
                    await self.bot.send_photo(
                        user_id,
                        photo.file_id,
                        caption=text if text else None
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки фото пользователю: {e}")

            elif media_type == "document":
                doc = message.document
                text = text
                media_files = [{
                    "type": "document",
                    "file_id": doc.file_id,
                    "file_unique_id": doc.file_unique_id,
                    "file_name": doc.file_name or "Документ",
                    "caption": text
                }]
                error_message = "❌ Произошла ошибка при отправке документа"
                try:
                    await self.bot.send_document(
                        user_id,
                        doc.file_id,
                        caption=text if text else None
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки документа пользователю: {e}")

            else:
                error_message = "❌ Произошла ошибка при отправке ответа"
                try:
                    await self.bot.send_message(
                        user_id,
                        text,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки пользователю: {e}")

            await state.clear()

        except Exception as e:
            self.logger.error(f"Ошибка при обработке ответа администратора: {e}")
            await message.answer(error_message if media_type else "❌ Произошла ошибка при отправке ответа")
            await state.clear()
            return

        await self.storage.add_message(
            user_id=user_id,
            sender_type="admin",
            sender_id=message.chat.id,
            sender_name="Администратор",
            text=text,
            media_files=media_files if media_files else None
        )

        await state.set_state(SupportStates.admin_viewing_chat)
        chat = self.storage.chats[user_id]
        messages_text, total_pages = self.build_chat_display_text(chat, page=0)
        last_page = total_pages - 1
        messages_text, total_pages = self.build_chat_display_text(chat, page=last_page)
        keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value, chat_page=last_page,
                                 total_pages=total_pages)
        await message.answer(messages_text, reply_markup=keyboard, parse_mode="HTML")

    async def process_user_message(self, message: Message, media_type: str = None):
        error_message = "❌ Ошибка при обработке сообщения"
        try:
            user_id = message.chat.id
            chat = self.storage.add_or_get_chat(user_id, message.from_user.full_name)
            was_closed = chat.status == ChatStatus.CLOSED.value
            is_first_message = len(chat.messages) == 0

            if was_closed:
                await self.storage.set_chat_status(user_id, ChatStatus.OPEN.value)

            media_files = []
            text = message.text or message.caption or ""

            if media_type == "photo":
                photo = message.photo[-1]
                media_files = [{
                    "type": "photo",
                    "file_id": photo.file_id,
                    "file_unique_id": photo.file_unique_id,
                    "caption": text
                }]
                error_message = "❌ Ошибка при обработке фото"

            elif media_type == "document":
                doc = message.document
                media_files = [{
                    "type": "document",
                    "file_id": doc.file_id,
                    "file_unique_id": doc.file_unique_id,
                    "file_name": doc.file_name or "Документ",
                    "caption": text
                }]
                error_message = "❌ Ошибка при обработке документа"

            if was_closed:
                await message.answer(
                    Messages.get_messages("CHAT_CLOSED", self.language_manager.get_user_language(user_id)))

        except Exception as e:
            self.logger.error(f"Ошибка при обработке сообщения: {e}")
            await message.answer(error_message)
            return

        await self.storage.add_message(
            user_id=user_id,
            sender_type="user",
            sender_id=message.chat.id,
            sender_name=message.from_user.full_name,
            text=text,
            media_files=media_files if media_files else None
        )

        if was_closed or is_first_message:
            await self.notify_admins_about_message(user_id, message.from_user.full_name)

    async def main_menu(self, message: Message):
        user_id = message.chat.id
        if user_id in ADMIN_IDS:
            await message.answer(
                "👨‍💻 Панель администратора",
                reply_markup=Keyboard.admin_menu(),
                parse_mode="HTML"
            )
        else:
            help_text = Messages.get_messages("HELP_BUTTON", self.language_manager.get_user_language(message.chat.id),
                                              False)
            await message.answer(
                Messages.get_messages("MAIN", self.language_manager.get_user_language(user_id)),
                reply_markup=Keyboard.user_help(help_text),
                parse_mode="HTML"
            )

    async def notify_admins_about_message(self, user_id: int, user_name: str):
        for admin_id in ADMIN_IDS:
            try:
                chat_preview = self.storage.get_chat_preview(user_id, max_length=30)
                await self.bot.send_message(
                    admin_id,
                    f"📩 Новое сообщение от пользователя:\n"
                    f"👤 {user_name}\n"
                    f"{chat_preview}",
                    reply_markup=Keyboard.open_chat(user_id),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

    def build_chat_display_text(self, chat: VirtualChat, page: int = 0,
                                char_limit: int = PAGE_CHAR_LIMIT) -> tuple[str, int]:
        if not chat.messages:
            return "(нет сообщений)", 1

        full_text = ""
        photo_count = 0

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
                            media_info += f"📷 Изображение №{photo_count}"
                        elif media["type"] == "document":
                            media_info += f"📄 {media.get('file_name', 'Документ')}"
                    text_content = (text_content + "\n" if text_content else "") + media_info

                full_text += f"{sender_label} {msg.sender_name} ({time}):\n{text_content}\n\n"

            except Exception as e:
                self.logger.error(f"Ошибка форматирования сообщения: {e}")
                continue

        header = f"💬 {chat.user_name}\n"
        header += f"Статус: {'🟢 Открыт' if chat.status == ChatStatus.OPEN else '🔴 Закрыт'}\n"
        header += "═" * 24 + "\n\n"

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

        closed_message = "\n\n🔴 Чат закрыт администратором"
        if chat.status == ChatStatus.OPEN:
            closed_message = ""

        if current_page_text:
            pages.append(header + current_page_text)

        if not pages:
            pages = [header + "Ошибка при формировании страниц"]

        total_pages = len(pages)
        if page >= total_pages:
            page = total_pages - 1

        page_text = pages[page]
        return truncate_text(page_text) + closed_message, total_pages

    @staticmethod
    def build_last_messages_preview(messages: List[ChatMessage]) -> str:
        if not messages:
            return f"📋 История чата (последние {LAST_MESSAGES_COUNT} сообщений):\n\n(сообщений нет)"

        text = f"📋 История чата (последние {LAST_MESSAGES_COUNT} сообщений):\n"
        text += "=" * 24 + "\n\n"

        for msg in messages:
            sender_label = "👤 Пользователь" if msg.sender_type == "user" else "👨‍💻 Администратор"
            text += f"{sender_label} [{msg.timestamp}]\n"

            if msg.text:
                text += f"{msg.text}\n"

            if msg.media_files:
                for media in msg.media_files:
                    if media['type'] == 'photo':
                        text += "📷 Изображение\n"
                    elif media['type'] == 'document':
                        text += f"📄 {media.get('file_name', 'Документ')}\n"

            text += "\n"

        text += "=" * 24 + "\n"
        return text

    async def cleanup_closed_chats(self):
        while True:
            now = datetime.now()
            chats_to_delete = []

            for uid, chat in list(self.storage.chats.items()):
                if chat.status == ChatStatus.CLOSED.value and chat.messages:
                    last_msg_time = datetime.strptime(chat.messages[-1].timestamp, "%d.%m.%Y %H:%M")
                    if now - last_msg_time > timedelta(weeks=2):
                        chats_to_delete.append(uid)

            for uid in chats_to_delete:
                del self.storage.chats[uid]

            if chats_to_delete:
                await self.storage.save()

            await asyncio.sleep(3600)

    async def auto_close_inactive_chats(self):
        while True:
            now = datetime.now()
            for chat in self.storage.chats.values():
                if chat.status == ChatStatus.OPEN.value and chat.messages:
                    last_msg_time = datetime.strptime(chat.messages[-1].timestamp, "%d.%m.%Y %H:%M")
                    if now - last_msg_time > timedelta(days=2):
                        chat.status = ChatStatus.CLOSED.value
                        await self.storage.save()

            await asyncio.sleep(1800)

    async def on_startup(self):
        asyncio.create_task(self.cleanup_closed_chats())
        asyncio.create_task(self.auto_close_inactive_chats())

    async def start(self, message: Message):
        try:
            user_id = message.chat.id
            if not self.language_manager.user_exists(user_id):
                await message.answer(
                    Messages.get_messages("HELLO", self.language_manager.get_user_language(message.chat.id)),
                    reply_markup=Keyboard.language(),
                    parse_mode="HTML"
                )
            else:
                chat = self.storage.add_or_get_chat(user_id, message.from_user.full_name)
                was_closed = chat.status == ChatStatus.CLOSED.value
                await self.storage.set_chat_status(user_id, ChatStatus.OPEN.value)
                await self.main_menu(message)
                if was_closed:
                    await self.notify_admins_about_message(user_id, message.from_user.full_name)
        except Exception as e:
            self.logger.error(f"Ошибка в start: {e}")

    async def change_language(self, message: Message):
        await message.answer(
            Messages.get_messages("LANGUAGE", self.language_manager.get_user_language(message.chat.id)),
            reply_markup=Keyboard.language(),
            parse_mode="HTML"
        )

    @staticmethod
    async def admin_help(callback_data: CallbackQuery):
        help_text = """
👨‍💻 СПРАВКА ПО БОТУ

📋 Основные функции:
Просмотр всех чатов (фильтры: все/ожидающие/закрытые)
Чтение истории с пагинацией
📸 Просмотр фото/📄 документов
💬 Отправка ответов (текст/фото/документы)
Управление статусом (закрыть/открыть)
Обновление чатов в реальном времени

🤖 Автоматика:
Автозакрытие неактивных за 2 дня
Удаление закрытых за 2 недели
Уведомления о новых сообщениях

💾 Данные:W
Полная история чатов (JSON)
Все медиафайлы сохраняются
Информация не теряется при перезагрузке

Все функции доступны через кнопки в панели.
"""
        await callback_data.message.answer(help_text, reply_markup=Keyboard.delete(), parse_mode="HTML")
        await callback_data.answer()

    async def user_help(self, callback_data: CallbackQuery):
        help_text = Messages.get_messages("HELP",
                                          self.language_manager.get_user_language(callback_data.message.chat.id))
        await callback_data.message.answer(help_text, reply_markup=Keyboard.delete(), parse_mode="HTML")
        await callback_data.answer()

    async def set_language(self, callback: CallbackQuery):
        language = callback.data.split("_")[1]
        self.language_manager.set_user_language(callback.from_user.id, language)
        await callback.message.delete()
        await self.main_menu(callback.message)

    async def user_photo(self, message: Message):
        await self.process_user_message(message, media_type="photo")

    async def user_document(self, message: Message):
        await self.process_user_message(message, media_type="document")

    async def user_message(self, message: Message):
        await self.process_user_message(message)

    @staticmethod
    async def delete_message_handler(query: CallbackQuery):
        await query.message.delete()

    async def admin_menu(self, query: CallbackQuery, state: FSMContext):
        try:
            await state.clear()
            await query.message.edit_text(
                "👨‍💻 Панель администратора",
                reply_markup=Keyboard.admin_menu(),
                parse_mode="HTML"
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_menu: {e}")

    async def admin_view_all(self, query: CallbackQuery, state: FSMContext):
        try:
            await state.set_state(SupportStates.admin_browsing)
            chats_list = self.storage.get_all_chats_list()
            keyboard = Keyboard.chats(self.storage, chats_list, page=0)
            unread = self.storage.get_unread_count()
            text = f"📋 Все чаты ({len(chats_list)})\n⏳ Ожидающих ответа: {unread}"
            if not chats_list:
                text = "❌ Нет чатов"
            await query.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_view_all: {e}")

    async def admin_view_waiting(self, query: CallbackQuery, state: FSMContext):
        try:
            await state.set_state(SupportStates.admin_browsing)
            chats_list = self.storage.get_all_chats_list(filter_status=ChatStatus.OPEN.value)
            keyboard = Keyboard.chats(self.storage, chats_list, page=0)
            text = f"⏳ Чаты ожидающие ответа ({len(chats_list)})"
            if not chats_list:
                text = "❌ Нет чатов"
            await query.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_view_waiting: {e}")

    async def admin_view_closed(self, query: CallbackQuery, state: FSMContext):
        try:
            await state.set_state(SupportStates.admin_browsing)
            chats_list = self.storage.get_all_chats_list(filter_status=ChatStatus.CLOSED.value)
            keyboard = Keyboard.chats(self.storage, chats_list, page=0)
            text = f"✅ Закрытые чаты ({len(chats_list)})"
            if not chats_list:
                text = "❌ Нет чатов"
            await query.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_view_closed: {e}")

    async def admin_change_page(self, query: CallbackQuery):
        try:
            page = int(query.data.split("_")[2])
            chats_list = self.storage.get_all_chats_list()
            keyboard = Keyboard.chats(self.storage, chats_list, page=page)
            await query.message.edit_reply_markup(reply_markup=keyboard)
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_change_page: {e}")

    async def change_chat_page(self, query: CallbackQuery, state: FSMContext):
        try:
            parts = query.data.split("_")
            user_id = int(parts[2])
            new_page = int(parts[3])

            if user_id not in self.storage.chats:
                await query.answer("❌ Чат не найден", show_alert=True)
                return

            await state.update_data(selected_chat_id=user_id, chat_page=new_page)
            chat = self.storage.chats[user_id]
            messages_text, total_pages = self.build_chat_display_text(chat, page=new_page)
            keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value,
                                     chat_page=new_page, total_pages=total_pages)
            await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в change_chat_page: {e}")

    async def admin_view_chat(self, query: CallbackQuery, state: FSMContext):
        try:
            parts = query.data.split("_")
            user_id = int(parts[1])

            if user_id not in self.storage.chats:
                await query.answer("❌ Чат не найден", show_alert=True)
                return

            chat = self.storage.chats[user_id]
            messages_text, total_pages = self.build_chat_display_text(chat, page=0)
            last_page = total_pages - 1
            messages_text, total_pages = self.build_chat_display_text(chat, page=last_page)

            await state.update_data(selected_chat_id=user_id, chat_page=last_page)
            await state.set_state(SupportStates.admin_viewing_chat)

            keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value,
                                     chat_page=last_page, total_pages=total_pages)
            await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_view_chat: {e}")

    async def show_media_menu(self, query: CallbackQuery, state: FSMContext):
        try:
            user_id = int(query.data.split("_")[2])

            if user_id not in self.storage.chats:
                await query.answer("❌ Чат не найден", show_alert=True)
                return

            chat = self.storage.chats[user_id]
            images, docs = [], []

            for msg in chat.messages:
                for media in msg.media_files:
                    if media["type"] == "photo":
                        images.append(media)
                    elif media["type"] == "document":
                        docs.append(media)

            if not images and not docs:
                await query.answer("❌ Нет медиафайлов в чате", show_alert=True)
                return

            await state.update_data(
                selected_chat_id=user_id,
                chat_images=images,
                chat_docs=docs,
                viewing_media=True,
            )
            await state.set_state(SupportStates.admin_viewing_images)

            keyboard, msg_lines = [], []

            for i, image in enumerate(images):
                keyboard.append(
                    [InlineKeyboardButton(text=f"📷 Изображение №{i + 1}",
                                          callback_data=f"select_media_{user_id}_photo_{i}")]
                )

            for i, doc in enumerate(docs):
                doc_name = doc.get("file_name", "Документ")
                keyboard.append(
                    [InlineKeyboardButton(text=f"📄 {doc_name}", callback_data=f"select_media_{user_id}_document_{i}")]
                )

            keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chat_{user_id}_0")])

            await query.message.edit_text(
                f"🗂 Выберите медиафайл ({len(images) + len(docs)} всего):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в show_media_menu: {e}")

    async def select_media(self, query: CallbackQuery, state: FSMContext):
        try:
            parts = query.data.split("_")
            user_id = int(parts[2])
            media_type = parts[3]
            media_index = int(parts[4])

            data = await state.get_data()
            media_list = data.get("chat_images" if media_type == "photo" else "chat_docs", [])

            if media_index >= len(media_list):
                await query.answer(f"❌ {'Изображение' if media_type == 'photo' else 'Документ'} не найдено",
                                   show_alert=True)
                return

            selected_media = media_list[media_index]

            try:
                if media_type == "photo":
                    await self.bot.send_photo(
                        query.from_user.id,
                        selected_media["file_id"],
                        caption=selected_media.get("caption", ""),
                        reply_markup=Keyboard.delete()
                    )
                else:
                    await self.bot.send_document(
                        query.from_user.id,
                        selected_media["file_id"],
                        caption=selected_media.get("caption", ""),
                        reply_markup=Keyboard.delete()
                    )
            except Exception as e:
                self.logger.error(f"Ошибка отправки медиа: {e}")

            await state.update_data(viewing_media=False)
            await state.set_state(SupportStates.admin_viewing_chat)

            chat = self.storage.chats[user_id]
            messages_text, total_pages = self.build_chat_display_text(chat, page=0)
            last_page = total_pages - 1
            messages_text, total_pages = self.build_chat_display_text(chat, page=last_page)
            keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value,
                                     chat_page=last_page, total_pages=total_pages)
            await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в select_media: {e}")

    async def refresh_chat(self, query: CallbackQuery, state: FSMContext):
        try:
            user_id = int(query.data.split("_")[1])

            if user_id not in self.storage.chats:
                await query.answer("❌ Чат не найден", show_alert=True)
                return

            chat = self.storage.chats[user_id]
            messages_text, total_pages = self.build_chat_display_text(chat, page=0)
            last_page = total_pages - 1
            messages_text, total_pages = self.build_chat_display_text(chat, page=last_page)

            await state.update_data(selected_chat_id=user_id, chat_page=last_page)
            await state.set_state(SupportStates.admin_viewing_chat)

            keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value,
                                     chat_page=last_page, total_pages=total_pages)
            await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer("🔄 Чат обновлен")
        except Exception as e:
            self.logger.error(f"Ошибка в refresh_chat: {e}")

    async def toggle_chat_status(self, query: CallbackQuery):
        try:
            user_id = int(query.data.split("_")[2])

            if user_id not in self.storage.chats:
                await query.answer("❌ Чат не найден", show_alert=True)
                return

            chat = self.storage.chats[user_id]

            if chat.status == ChatStatus.OPEN.value:
                await self.storage.set_chat_status(user_id, ChatStatus.CLOSED.value)
                notification_message = Messages.get_messages("CHAT_CLOSED_BY_ADMIN",
                                                             self.language_manager.get_user_language(user_id))
                await query.answer("✅ Чат закрыт")
            else:
                await self.storage.set_chat_status(user_id, ChatStatus.OPEN.value)
                notification_message = None
                await query.answer("✅ Чат открыт")

            if notification_message:
                try:
                    await self.bot.send_message(
                        user_id,
                        notification_message,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Ошибка отправки уведомления пользователю: {e}")

            chat = self.storage.chats[user_id]
            messages_text, total_pages = self.build_chat_display_text(chat, page=0)
            last_page = total_pages - 1
            messages_text, total_pages = self.build_chat_display_text(chat, page=last_page)
            keyboard = Keyboard.chat(self.storage, user_id, ChatStatus.OPEN.value,
                                     chat_page=last_page, total_pages=total_pages)
            await query.message.edit_text(messages_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            self.logger.error(f"Ошибка в toggle_chat_status: {e}")

    async def admin_reply_prompt(self, query: CallbackQuery, state: FSMContext):
        try:
            user_id = int(query.data.split("_")[1])
            await state.update_data(selected_chat_id=user_id)
            await state.set_state(SupportStates.admin_replying)

            messages = self.storage.get_last_messages(user_id)
            text = self.build_last_messages_preview(messages)

            await query.message.edit_text(
                f"{text}\n\n✍️ Напишите ответ пользователю:",
                reply_markup=Keyboard.cancel_reply(user_id),
                parse_mode="HTML"
            )
            await query.answer()
        except Exception as e:
            self.logger.error(f"Ошибка в admin_reply_prompt: {e}")

    async def admin_send_photo_reply(self, message: Message, state: FSMContext):
        await self.admin_send_reply(message, state, media_type="photo")

    async def admin_send_document_reply(self, message: Message, state: FSMContext):
        await self.admin_send_reply(message, state, media_type="document")

    async def admin_send_text_reply(self, message: Message, state: FSMContext):
        await self.admin_send_reply(message, state)

    async def error_handler(self, exception):
        self.logger.error(f"❌ Необработанная ошибка: {exception}")

    async def start_polling(self):
        await self.on_startup()
        await self.dp.start_polling(self.bot)
