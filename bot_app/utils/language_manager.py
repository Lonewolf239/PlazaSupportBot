import json
import os


class LanguageManager:
    def __init__(self, language_file):
        self.language_file = language_file

    def load_languages(self) -> dict:
        if os.path.exists(self.language_file):
            with open(self.language_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_languages(self, languages: dict) -> None:
        with open(self.language_file, "w", encoding="utf-8") as f:
            json.dump(languages, f, ensure_ascii=False, indent=2)

    def user_exists(self, user_id: int) -> bool:
        languages = self.load_languages()
        return str(user_id) in languages

    def set_user_language(self, user_id: int, language: str) -> None:
        languages = self.load_languages()
        languages[str(user_id)] = language
        self.save_languages(languages)

    def get_user_language(self, user_id: int, default: str = "en") -> str:
        languages = self.load_languages()
        return languages.get(str(user_id), default)