class Messages:
    TEXT = {
        "HELLO": {
            "ru": "👋 Привет! Выберите язык:",
            "en": "👋 Hello! Choose language:"
        },
        "MAIN": {
            "ru": "👋 Добро пожаловать в техподдержку!\n\nНапишите вашу проблему, и мы вам поможем.",
            "en": "👋 Welcome to technical support!\n\nWrite your problem, and we will help you."
        },
        "LANGUAGE": {
            "ru": "🌐 Выберите язык",
            "en": "🌐 Choose language"
        },
        "CHAT_CLOSED": {
            "ru": "🔄 Ваш чат был закрыт. Он открыт заново.\n"
                  "✅ Ваше сообщение отправлено в техподдержку\n"
                  "⏳ Ожидайте ответа...",
            "en": "🔄 Your chat_utils was closed. It has been reopened.\n"
                  "✅ Your message has been sent to technical support\n"
                  "⏳ Wait for a response..."
        },
        "CHAT_CLOSED_BY_ADMIN": {
            "ru": "❌ Ваш чат был закрыт администратором.\n"
                  "Если у вас есть еще вопросы, напишите /start чтобы создать новый чат.",
            "en": "❌ Your chat_utils has been closed by the administrator.\n"
                  "If you have any more questions, type /start to create a new chat_utils."
        },
        "HELP": {
            "ru": "💬 <b>СПРАВКА ПО ЧАТУ</b>\n\n"
                  "<b>📝 Как пользоваться:</b>\n"
                  "      Отправляйте сообщения в этот чат\n"
                  "      📸 Прикрепляйте фото и документы\n"
                  "      💬 Получайте ответы от администратора\n\n"
                  "<b>⏱️ Важно:</b>\n"
                  "      Закрытый чат: администратор завершил общение\n"
                  "      Неиспользуемый чат закроется автоматически\n\n"
                  "<i><b>Просто пишите, и вам помогут!</b></i>",
            "en": "💬 <b>CHAT HELP</b>\n\n"
                  "<b>📝 How to use:</b>\n"
                  "      Send messages to this chat_utils\n"
                  "      📸 Attach photos and documents\n"
                  "      💬 Get answers from the administrator\n\n"
                  "<b>⏱️ Important:</b>\n"
                  "      Closed chat_utils: administrator finished the conversation\n"
                  "      Unused chat_utils will close automatically\n\n"
                  "<i><b>Just write, and we will help you!</b></i>"
        },
        "HELP_BUTTON": {"ru": "❓ Помощь", "en": "❓ Help"}
    }

    @staticmethod
    def get_messages(tag, language: str = "en", add_bot: bool = True):
        bot_icons = {"ru": "ℹ️ <b>[БОТ]</b>\n\n", "en": "ℹ️ <b>[BOT]</b>\n\n"}
        bot = ""
        if add_bot:
            bot = bot_icons[language]
        return bot + Messages.TEXT.get(tag, {}).get(language,
                                                    Messages.TEXT.get(tag, {}).get("en", "⚠️ Message not found"))
