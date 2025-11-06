class Messages:
    TEXT = {
        "MAIN": {
            "ru": "[🤖] 👋 Добро пожаловать в техподдержку!\n\nНапишите вашу проблему, и мы вам поможем.",
            "en": "[🤖] 👋 Welcome to technical support!\n\nWrite your problem, and we will help you."
        },
        "CHAT_CLOSED": {
            "ru": "[🤖] 🔄 Ваш чат был закрыт. Он открыт заново.\n"
                  "✅ Ваше сообщение отправлено в техподдержку\n"
                  "⏳ Ожидайте ответа...",
            "en": "[🤖] 🔄 Your chat was closed. It has been reopened.\n"
                  "✅ Your message has been sent to technical support\n"
                  "⏳ Wait for a response..."
        },
        "CHAT_CLOSED_BY_ADMIN": {
            "ru": "[🤖] ❌ Ваш чат был закрыт администратором.\n"
                  "Если у вас есть еще вопросы, напишите /start чтобы создать новый чат.",
            "en": "[🤖] ❌ Your chat has been closed by the administrator.\n"
                  "If you have any more questions, type /start to create a new chat."
        }
    }

    @staticmethod
    def get_messages(tag, language="en"):
        return Messages.TEXT.get(tag, {}).get(language,
                                              Messages.TEXT.get(tag, {}).get("en", "⚠️ Message not found"))
