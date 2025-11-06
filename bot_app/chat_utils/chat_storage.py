import asyncio
from datetime import datetime
import json
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional
import os
import aiofiles
from bot_app.utils import truncate_text

MAX_NAME_LENGTH = 100
CHAT_PREVIEW_LENGTH = 50
LAST_MESSAGES_COUNT = 6


class ChatStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


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

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "created_at": self.created_at,
            "messages": [msg.to_dict() for msg in self.messages],
            "status": self.status
        }

    @staticmethod
    def from_dict(data):
        messages = [ChatMessage.from_dict(msg) for msg in data.get("messages", [])]
        return VirtualChat(
            user_id=data["user_id"],
            user_name=data["user_name"],
            created_at=data["created_at"],
            messages=messages,
            status=data.get("status", ChatStatus.OPEN.value)
        )


class ChatStorage:
    def __init__(self, filename: str, logger: logging.Logger):
        self.filename = filename
        self.chats: Dict[int, VirtualChat] = {}
        self._lock = asyncio.Lock()
        self._logger = logger
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
                self._logger.error(f"Ошибка загрузки: {e}")
                self.chats = {}

    async def save(self):  # ← async метод
        async with self._lock:
            try:
                async with aiofiles.open(self.filename, "w", encoding="utf-8") as f:
                    data = {str(user_id): chat.to_dict() for user_id, chat in self.chats.items()}
                    await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            except Exception as e:
                self._logger.error(f"Ошибка сохранения: {e}")

    def add_or_get_chat(self, user_id: int, user_name: str) -> VirtualChat:
        if user_id not in self.chats:
            self.chats[user_id] = VirtualChat(
                user_id=user_id,
                user_name=user_name or "Неизвестный пользователь",
                created_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
                messages=[]
            )
        return self.chats[user_id]

    async def add_message(self, user_id: int, sender_type: str, sender_id: int, sender_name: str, text: str,
                    media_files: List[Dict] = None):
        """Безопасно добавляет сообщение"""
        if user_id in self.chats:
            safe_text = truncate_text(text or "")
            safe_name = (sender_name or "Пользователь")[:MAX_NAME_LENGTH]
            msg = ChatMessage(
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=safe_name,
                text=safe_text,
                timestamp=datetime.now().strftime("%d.%m.%Y %H:%M"),
                media_files=media_files or []
            )
            self.chats[user_id].messages.append(msg)
            await self.save()

    def get_chat_preview(self, user_id: int, max_length: int = CHAT_PREVIEW_LENGTH) -> str:
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

    async def set_chat_status(self, user_id: int, status: str):
        if user_id in self.chats:
            self.chats[user_id].status = status
            await self.save()

    def get_unread_count(self) -> int:
        """Чаты, ждущие ответа"""
        return sum(1 for chat in self.chats.values()
                   if chat.status == ChatStatus.OPEN.value)

    def get_last_messages(self, user_id: int, count: int = LAST_MESSAGES_COUNT) -> List[ChatMessage]:
        """Получить последние N сообщений"""
        if user_id not in self.chats:
            return []
        messages = self.chats[user_id].messages
        return messages[-count:] if len(messages) > count else messages
