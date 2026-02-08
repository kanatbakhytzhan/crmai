"""
Lead Categorization Service

Automatic categorization logic for leads based on conversation state and extracted data.

Categories:
- no_reply: No response from client yet
- wants_call: Client requested a phone call
- partial_data: Some required fields collected
- full_data: All required fields collected
- measurement_assigned: Measurement scheduled
- measurement_done: Measurement completed
- rejected: Lead rejected/lost
- won: Deal won
"""
from typing import Optional
import logging

log = logging.getLogger(__name__)

# Required fields for "full_data" category
REQUIRED_FIELDS_FOR_FULL_DATA = [
    "name",
    "city",
    "phone",
    "house_length",
    "house_width",
]

# Optional but desired fields
DESIRED_FIELDS = [
    "house_height",
    "foundation_cover",
    "doors_count",
    "windows_count",
]


def categorize_lead(lead, extracted_fields: dict | None = None) -> str:
    """
    Determine lead category based on current state and extracted data
    
    Args:
        lead: Lead model instance
        extracted_fields: Dict with extracted conversation data
        
    Returns:
        Category string (no_reply, wants_call, partial_data, full_data, etc.)
    """
    if not extracted_fields:
        extracted_fields = lead.extracted_fields if hasattr(lead, 'extracted_fields') else {}
    
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}
    
    # Priority 1: Explicit statuses (manual override)
    if hasattr(lead, 'category') and lead.category in ('measurement_assigned', 'measurement_done', 'rejected', 'won'):
        return lead.category
    
    # Priority 2: Wants call (high intent)
    if extracted_fields.get("wants_call") == "yes":
        return "wants_call"
    
    # Priority 3: Check data completeness
    required_present = [
        field for field in REQUIRED_FIELDS_FOR_FULL_DATA
        if extracted_fields.get(field) and str(extracted_fields.get(field)).strip()
    ]
    
    if len(required_present) == len(REQUIRED_FIELDS_FOR_FULL_DATA):
        # All required fields present
        return "full_data"
    
    if len(required_present) > 0:
        # Some required fields present
        return "partial_data"
    
    # Priority 4: Default - no reply yet
    return "no_reply"


def calculate_lead_score(lead, extracted_fields: dict | None = None) -> str:
    """
    Calculate lead temperature: hot, warm, cold
    
    Args:
        lead: Lead model instance
        extracted_fields: Dict with extracted conversation data
        
    Returns:
        Score string (hot, warm, cold)
    """
    if not extracted_fields:
        extracted_fields = lead.extracted_fields if hasattr(lead, 'extracted_fields') else {}
    
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}
    
    category = getattr(lead, 'category', None) or categorize_lead(lead, extracted_fields)
    
    # Hot: wants call OR full data
    if category in ('wants_call', 'full_data'):
        return 'hot'
    
    # Warm: partial data + recent activity
    if category == 'partial_data':
        return 'warm'
    
    # Cold: no reply or rejected
    return 'cold'


async def update_lead_category(db, lead, new_category: str, extracted_fields: Optional[dict] = None):
    """
    Update lead category and trigger side effects (AmoCRM sync, etc.)
    
    Args:
        db: Database session
        lead: Lead instance
        new_category: New category value
        extracted_fields: Optional extracted fields to save
    """
    old_category = getattr(lead, 'category', None)
    
    # Update category
    lead.category = new_category
    
    # Update extracted_fields if provided
    if extracted_fields is not None:
        # Merge with existing
        current = lead.extracted_fields if hasattr(lead, 'extracted_fields') and lead.extracted_fields else {}
        if isinstance(current, dict) and isinstance(extracted_fields, dict):
            current.update(extracted_fields)
            lead.extracted_fields = current
        else:
            lead.extracted_fields = extracted_fields
    
    # Recalculate score
    new_score = calculate_lead_score(lead, lead.extracted_fields if hasattr(lead, 'extracted_fields') else {})
    lead.lead_score = new_score
    
    await db.commit()
    await db.refresh(lead)
    
    log.info(f"[CATEGORIZATION] Lead {lead.id}: {old_category} → {new_category} (score={new_score})")
    
    # TODO: Trigger AmoCRM sync if category changed
    # Will be implemented in Phase D
    
    return lead


# Test function
def test_categorization():
    """Unit test for categorization logic"""
    class MockLead:
        def __init__(self):
            self.id = 1
            self.category = None
            self.extracted_fields = {}
    
    # Test 1: No data → no_reply
    lead = MockLead()
    result = categorize_lead(lead, {})
    assert result == "no_reply", f"Expected no_reply, got {result}"
    print("✅ Test 1: Empty fields → no_reply")
    
    # Test 2: Wants call → wants_call
    lead = MockLead()
    result = categorize_lead(lead, {"wants_call": "yes"})
    assert result == "wants_call", f"Expected wants_call, got {result}"
    print("✅ Test 2: wants_call=yes → wants_call")
    
    # Test 3: Partial data → partial_data
    lead = MockLead()
    result = categorize_lead(lead, {"name": "Ivan", "city": "Almaty"})
    assert result == "partial_data", f"Expected partial_data, got {result}"
    print("✅ Test 3: Partial fields → partial_data")
    
    # Test 4: Full data → full_data
    lead = MockLead()
    result = categorize_lead(lead, {
        "name": "Ivan",
        "city": "Almaty",
        "phone": "+77001234567",
        "house_length": "10",
        "house_width": "8",
    })
    assert result == "full_data", f"Expected full_data, got {result}"
    print("✅ Test 4: All required fields → full_data")
    
    # Test 5: Score calculation
    lead = MockLead()
    lead.category = "wants_call"
    score = calculate_lead_score(lead, {})
    assert score == "hot", f"Expected hot, got {score}"
    print("✅ Test 5: wants_call → score=hot")
    
    lead.category = "partial_data"
    score = calculate_lead_score(lead, {})
    assert score == "warm", f"Expected warm, got {score}"
    print("✅ Test 6: partial_data → score=warm")
    
    lead.category = "no_reply"
    score = calculate_lead_score(lead, {})
    assert score == "cold", f"Expected cold, got {score}"
    print("✅ Test 7: no_reply → score=cold")
    
    print("\n✅ All categorization tests passed!")


if __name__ == "__main__":
    test_categorization()
