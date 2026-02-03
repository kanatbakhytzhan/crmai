"""
Нормализация телефона для импорта лидов (AmoCRM CSV/JSON).
Принимает 8xxxxxxxxxx, +7xxxxxxxxxx, 7xxxxxxxxxx → возвращает 7xxxxxxxxxx (без +).
"""
import re


def normalize_phone(raw: str) -> str | None:
    """
    Нормализовать номер: убрать всё кроме цифр, привести к формату 7xxxxxxxxxx (Казахстан/РФ).
    Если пустая строка или меньше 10 цифр — вернуть None.
    """
    if not raw or not isinstance(raw, str):
        return None
    digits = re.sub(r"\D", "", str(raw).strip())
    if len(digits) < 10:
        return None
    if digits.startswith("8") and len(digits) >= 11:
        digits = "7" + digits[1:]
    elif digits.startswith("7") and len(digits) >= 11:
        digits = digits[:11]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        digits = "7" + digits[-10:]
    return digits[:11] if len(digits) >= 11 else ("7" + digits[-10:] if len(digits) >= 10 else None)
