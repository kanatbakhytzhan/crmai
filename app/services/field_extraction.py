"""
Field Extraction Service - Extract structured data from WhatsApp conversation

Incrementally updates extracted_fields based on user messages and AI analysis.
Detects: city, house dimensions, doors/windows count, foundation preference, call time, etc.
"""
import logging
import re
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Lead

log = logging.getLogger(__name__)


def extract_city_from_text(text: str, language: str = "ru") -> Optional[str]:
    """
    Extract city name from text using patterns.
    
    Examples:
    - "я из Алматы" → "Алматы"
    - "в Астане живу" → "Астана"
    - "Almaty kalasyndamyn" → "Almaty"
    """
    text_lower = text.lower()
    
    # Common Kazakhstan cities (русский и латиnica for Kazakh)
    cities = [
        "алматы", "almaty", "астана", "astana", "караганда", "karaganda",
        "шымкент", "shymkent", "актобе", "aktobe", "тараз", "taraz",
        "павлодар", "pavlodar", "усть-каменогорск", "ust-kamenogorsk",
        "семей", "semey", "атырау", "atyrau", "костанай", "kostanay",
        "кызылорда", "kyzylorda", "уральск", "uralsk", "петропавловск", "petropavlovsk"
    ]
    
    for city in cities:
        if city in text_lower:
            # Capitalize first letter
            return city.capitalize()
    
    # Pattern: "город X", "в X", "из X"
    patterns = [
        r"(?:город|калa)\s+([А-ЯЁA-Z][а-яёa-z]+)",
        r"(?:в|из|from)\s+([А-ЯЁA-Z][а-яёa-z]{3,})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
    
    return None


def extract_dimensions_from_text(text: str) -> Dict[str, Optional[float]]:
    """
    Extract house dimensions (length, width, height) from text.
    
    Examples:
    - "10 на 12 метров" → {length: 10, width: 12}
    - "высота 3.5м, 8x6" → {length: 8, width: 6, height: 3.5}
    - "12*10*3" → {length: 12, width: 10, height: 3}
    """
    result = {"length": None, "width": None, "height": None}
    
    # Pattern 1: "NxM" or "N*M" or "N на M"
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:x|×|х|\*|на)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if match:
        result["length"] = float(match.group(1))
        result["width"] = float(match.group(2))
    
    # Pattern 2: "NxMxH" (length x width x height)
    match3 = re.search(r'(\d+(?:\.\d+)?)\s*(?:x|×|х|\*)\s*(\d+(?:\.\d+)?)\s*(?:x|×|х|\*)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if match3:
        result["length"] = float(match3.group(1))
        result["width"] = float(match3.group(2))
        result["height"] = float(match3.group(3))
    
    # Pattern 3: "высота N" or "height N"
    height_match = re.search(r'(?:высот[аы]|height|biyiktig[iы])\s*:?\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if height_match and result["height"] is None:
        result["height"] = float(height_match.group(1))
    
    return result


def extract_counts_from_text(text: str) -> Dict[str, Optional[int]]:
    """
    Extract doors and windows count.
    
    Examples:
    - "3 двери и 5 окон" → {doors: 3, windows: 5}
    - "2 doors, 4 windows" → {doors: 2, windows: 4}
    """
    result = {"doors_count": None, "windows_count": None}
    
    # Doors
    doors_pattern = r'(\d+)\s*(?:дверей|дверь|дверы|есик|door[s]?|esik)'
    match = re.search(doors_pattern, text, re.IGNORECASE)
    if match:
        result["doors_count"] = int(match.group(1))
    
    # Windows
    windows_pattern = r'(\d+)\s*(?:окон|окно|окна|терезе|window[s]?|tereze)'
    match = re.search(windows_pattern, text, re.IGNORECASE)
    if match:
        result["windows_count"] = int(match.group(1))
    
    return result


def detect_wants_call(text: str, language: str = "ru") -> bool:
    """
    Detect if user wants a callback.
    
    Triggers:
    - "позвоните мне", "хочу звонок", "перезвоните"
    - "qongyraw shal", "telefon qongyrawyny", "zhalatyn"
    - "call me", "callback"
    """
    text_lower = text.lower()
    
    triggers_ru = ["позвони", "перезвони", "хочу звонок", "звонок", "свяжитесь", "связаться"]
    triggers_kz = ["qongiraw", "qongıraw", "telefon", "baylanys", "zhalat"]
    triggers_en = ["call", "callback", "phone"]
    
    for trigger in triggers_ru + triggers_kz + triggers_en:
        if trigger in text_lower:
            return True
    
    return False


def detect_call_time(text: str) -> Optional[str]:
    """
    Extract preferred call time.
    
    Examples:
    - "позвоните после 18:00" → "after 18:00"
    - "утром можно" → "morning"
    - "в 14 часов" → "14:00"
    """
    text_lower = text.lower()
    
    # Time patterns
    time_match = re.search(r'(\d{1,2}):(\d{2})', text)
    if time_match:
        return f"{time_match.group(1)}:{time_match.group(2)}"
    
    # Hour only
    hour_match = re.search(r'(?:в|at|saat)\s*(\d{1,2})\s*(?:час|hour|sagat)', text_lower)
    if hour_match:
        return f"{hour_match.group(1)}:00"
    
    # Time of day
    if any(word in text_lower for word in ["утр", "morning", "таң"]):
        return "morning"
    if any(word in text_lower for word in ["день", "afternoon", "kün"]):
        return "afternoon"
    if any(word in text_lower for word in ["вечер", "evening", "kesh"]):
        return "evening"
    if any(word in text_lower for word in ["после", "after"]):
        after_match = re.search(r'после\s*(\d{1,2})', text_lower)
        if after_match:
            return f"after {after_match.group(1)}:00"
    
    return None


async def update_extracted_fields(
    db: AsyncSession,
    lead: Lead,
    user_text: str,
    language: str = "ru"
) -> Dict[str, Any]:
    """
    Update lead.extracted_fields incrementally based on new user message.
    
    Returns updated extracted_fields dict.
    Merges with existing fields (doesn't overwrite non-None values).
    """
    # Get current fields or initialize
    current_fields = lead.extracted_fields or {}
    
    # Extract from new message
    city = extract_city_from_text(user_text, language)
    if city and not current_fields.get("city"):
        current_fields["city"] = city
        log.info(f"[EXTRACT] Lead {lead.id}: city={city}")
    
    dimensions = extract_dimensions_from_text(user_text)
    if dimensions["length"] and not current_fields.get("house_length"):
        current_fields["house_length"] = dimensions["length"]
        log.info(f"[EXTRACT] Lead {lead.id}: house_length={dimensions['length']}")
    if dimensions["width"] and not current_fields.get("house_width"):
        current_fields["house_width"] = dimensions["width"]
        log.info(f"[EXTRACT] Lead {lead.id}: house_width={dimensions['width']}")
    if dimensions["height"] and not current_fields.get("house_height"):
        current_fields["house_height"] = dimensions["height"]
        log.info(f"[EXTRACT] Lead {lead.id}: house_height={dimensions['height']}")
    
    counts = extract_counts_from_text(user_text)
    if counts["doors_count"] and not current_fields.get("doors_count"):
        current_fields["doors_count"] = counts["doors_count"]
        log.info(f"[EXTRACT] Lead {lead.id}: doors_count={counts['doors_count']}")
    if counts["windows_count"] and not current_fields.get("windows_count"):
        current_fields["windows_count"] = counts["windows_count"]
        log.info(f"[EXTRACT] Lead {lead.id}: windows_count={counts['windows_count']}")
    
    # Detect wants_call (always update, can change over time)
    wants_call = detect_wants_call(user_text, language)
    if wants_call:
        current_fields["wants_call"] = True
        call_time = detect_call_time(user_text)
        if call_time:
            current_fields["preferred_call_time"] = call_time
        log.info(f"[EXTRACT] Lead {lead.id}: wants_call=True")
    
    # Update lead
    lead.extracted_fields = current_fields
    await db.flush()
    
    return current_fields


def calculate_data_completeness(extracted_fields: Dict[str, Any]) -> float:
    """
    Calculate how complete the extracted data is (0.0 to 1.0).
    
    Required fields:
    - city (weight: 0.2)
    - house dimensions (length OR width, weight: 0.3)
    - doors/windows (at least one, weight: 0.3)
    - additional details (foundation, wants_call, etc., weight: 0.2)
    """
    score = 0.0
    
    if extracted_fields.get("city"):
        score += 0.2
    
    if extracted_fields.get("house_length") or extracted_fields.get("house_width"):
        score += 0.3
    
    if extracted_fields.get("doors_count") or extracted_fields.get("windows_count"):
        score += 0.3
    
    # Additional details
    extra_count = 0
    if extracted_fields.get("house_height"):
        extra_count += 1
    if extracted_fields.get("foundation_cover"):
        extra_count += 1
    if extracted_fields.get("wants_call"):
        extra_count += 1
    if extracted_fields.get("preferred_call_time"):
        extra_count += 1
    
    score += min(0.2, extra_count * 0.05)
    
    return round(score, 2)
