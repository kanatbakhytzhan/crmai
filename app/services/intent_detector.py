"""
Intent Detection for Lead Categorization

Detects user intents from messages:
- wants_call: user requests a phone call
- has_photo: user sent/mentioned house photo
- price_request: user asks about price
"""
import re

# Russian patterns for "wants call"
WANTS_CALL_RU = [
    r"позвони",
    r"звонок",
    r"наберите",
    r"созвон",
    r"перезвон",
    r"свяжитесь",
    r"связаться",
    r"звоните",
    r"позвоните",
    r"можно звонить",
    r"когда звонить",
    r"телефон",
    r"номер.*звонить",
    r"на какой.*звонить",
]

# Kazakh patterns for "wants call" (without special chars)
WANTS_CALL_KZ = [
    r"qoñырau",  # call (mix of Latin/Cyrillic)
    r"qoңырау",
    r"telefon",
    r"habarlas",  # contact
    r"хабарлас", 
    r"байланыс",  # connection
    r"qоңырау шал",  # make a call
    r"телефон",
]

# Price request patterns
PRICE_REQUEST_RU = [
    r"(сколько|какая|какую|цена|стоимость|стоит|цену|стоимость|расценки)",
]

PRICE_REQUEST_KZ = [
    r"(qansha|канша|баға|баѓа|qұny|құны)",
]


def detect_wants_call(text: str, language: str = 'ru') -> bool:
    """
    Detect if user wants a phone call
    
    Args:
        text: User message
        language: 'ru' or 'kz'
        
    Returns:
        True if call intent detected
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Choose patterns based on language
    patterns = WANTS_CALL_RU if language == 'ru' else WANTS_CALL_KZ
    
    # Also check Russian patterns for KZ (many write mixed)
    if language == 'kz':
        patterns = patterns + WANTS_CALL_RU
    
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def detect_price_request(text: str, language: str = 'ru') -> bool:
    """
    Detect if user asks about price
    
    Args:
        text: User message
        language: 'ru' or 'kz'
        
    Returns:
        True if price request detected
    """
    if not text:
        return False
    
    text_lower = text.lower()
    patterns = PRICE_REQUEST_RU if language == 'ru' else PRICE_REQUEST_KZ
    
    # Check both languages for KZ
    if language == 'kz':
        patterns = patterns + PRICE_REQUEST_RU
    
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def extract_intents(text: str, language: str = 'ru') -> dict:
    """
    Extract all intents from message
    
    Returns:
        {
            "wants_call": bool,
            "price_request": bool
        }
    """
    return {
        "wants_call": detect_wants_call(text, language),
        "price_request": detect_price_request(text, language),
    }


# Test cases
if __name__ == "__main__":
    test_cases = [
        ("позвоните мне пожалуйста", "ru", True, False),
        ("можно узнать цену", "ru", False, True),
        ("когда можно звонить", "ru", True, False),
        ("qoñырау shaliñiz", "kz", True, False),
        ("qansha turady", "kz", False, True),
        ("телефон", "kz", True, False),
        ("привет", "ru", False, False),
    ]
    
    print("Intent Detection Test Results:")
    print("=" * 60)
    for text, lang, expected_call, expected_price in test_cases:
        result = extract_intents(text, lang)
        call_match = "✅" if result["wants_call"] == expected_call else "❌"
        price_match = "✅" if result["price_request"] == expected_price else "❌"
        print(f"{call_match}{price_match} '{text}' ({lang})")
        print(f"   wants_call: {result['wants_call']} (expected: {expected_call})")
        print(f"   price_request: {result['price_request']} (expected: {expected_price})")
