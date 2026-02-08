"""
Language Detection for Kazakh and Russian

Detects Kazakh language even when written WITHOUT special characters
(ә, ұ, ү, і, ө, ғ, қ, ң, һ) - common in WhatsApp/SMS.

Examples:
- "salam kerek" → 'kz' (Kazakh in Latin)
- "салем керек" → 'kz' (Kazakh in Cyrillic without special chars)
- "привет нужно" → 'ru' (Russian)
- "hello need" → 'unknown'
"""

# Kazakh words commonly written in LATIN without special chars
KZ_WORDS_LATIN = {
    # Greetings & common
    "salam", "salem", "sәlem",
    "qalaysyz", "kalaysyz", "qalaisyndar",
    "rahmet", "raqmetmin", "raqmet",
    
    # Need/want
    "kerek", "qazhetti", "keregi",
    "kalai", "qalai", "qандай", "qanday",
    
    # Questions
    "ne", "nimә", "qansha", "kansha",
    "qai", "qanday", "qashanda", "qashan",
    
    # Time
    "bugin", "bүgín", "bugün", 
    "erteñ", "ertең", "erten",
    "keше", "keshegi",
    
    #Personal
    "magan", "maңгa", "manga",
    "sizge", "sen", "sİz",
    
    # Misc
    "biraq", "өite", "zhaqsy", "jaqsy",
    "iye", "жоq", "zhoq", "jok", "bar"
}

# Kazakh words in CYRILLIC but without special chars ә, ұ, ү, і, ө, ғ, қ, ң, һ
KZ_WORDS_CYRILLIC = {
    # People write Kazakh using only Russian keyboard
    "салем", "керек", "калай", "маған", "сізге",
    "бугін", "ертең", "канша", "кайдан", 
    "жақсы", "жок", "бар", "біреу", "неше",
    "керегі", "керем", "белсе", "балам",
    "рахмет", "кеш", "ойбай", "таңғы", "түнгі"
}

# Russian distinctive words (not in Kazakh)
RU_DISTINCTIVE_WORDS = {
    "привет", "здравствуйте", "нужно", "нужен", "нужна",
    "хочу", "хотел", "хотела", "можно", "можете",
    "спасибо", "пожалуйста", "конечно",
    "скажите", "узнать", "что", "как", "где", "когда",
    "сколько", "почему", "зачем", "который",
    "этот", "тот", "здесь", "там", "теперь", "потом",
    "очень", "просто", "только", "всё", "все"
}


def detect_language(text: str) -> str:
    """
    Detect language: 'ru' | 'kz' | 'unknown'
    
    Args:
        text: User message text
        
    Returns:
        - 'kz' if Kazakh detected (Latin or Cyrillic without special chars)
        - 'ru' if Russian detected
        - 'unknown' if cannot determine (fallback to RU in caller

)
    """
    if not text or not isinstance(text, str):
        return 'unknown'
    
    text_lower = text.lower()
    words = text_lower.split()
    
    if not words:
        return 'unknown'
    
    # Count matches
    kz_latin_matches = sum(1 for word in words if word in KZ_WORDS_LATIN)
    kz_cyrillic_matches = sum(1 for word in words if word in KZ_WORDS_CYRILLIC)
    ru_matches = sum(1 for word in words if word in RU_DISTINCTIVE_WORDS)
    
    total_kz_matches = kz_latin_matches + kz_cyrillic_matches
    
    # Decision logic
    if total_kz_matches > 0 and total_kz_matches >= ru_matches:
        return 'kz'
    
    if ru_matches > 0:
        return 'ru'
    
    # If very short (1-2 words) and no matches, check for Kazakh-specific patterns
    if len(words) <= 2:
        # Check for "q", "ñ", "ş" (Latin Kazakh)
        if any(char in text_lower for char in ['q', 'ñ', 'ş', 'ә', 'ұ', 'і', 'ө']):
            return 'kz'
    
    # Default: uncertain (caller should use Russian as fallback)
    return 'unknown'


def extract_language_from_message(text: str) -> str:
    """
    Extract language, with RU as fallback for 'unknown'
    
    Returns: 'ru' | 'kz'
    """
    detected = detect_language(text)
    return detected if detected in ('ru', 'kz') else 'ru'


# Test cases (run with: python -m app.services.language_detector)
if __name__ == "__main__":
    test_cases = [
        ("salam kerek", "kz"),
        ("салем керек маған", "kz"),
        ("привет нужно узнать", "ru"),
        ("qansha turady", "kz"),
        ("канша турады", "kz"),
        ("здравствуйте, можно узнать цену", "ru"),
        ("рахмет", "kz"),
        ("спасибо", "ru"),
        ("bugin bar ma", "kz"),
        ("сегодня есть", "ru"),
        ("позвоните пожалуйста", "ru"),
        ("qoñyrau shaliñiz", "kz"),
        ("hello", "unknown"),  # fallback to ru
        ("123", "unknown"),
    ]
    
    print("Language Detection Test Results:")
    print("=" * 50)
    for text, expected in test_cases:
        detected = detect_language(text)
        status = "✅" if detected == expected else "❌"
        print(f"{status} '{text}' → {detected} (expected: {expected})")
