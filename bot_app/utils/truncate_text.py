MAX_MESSAGE_LENGTH = 4096


def truncate_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Обрезает текст до максимальной длины"""
    if not text:
        return ""
    return text[:max_length]
