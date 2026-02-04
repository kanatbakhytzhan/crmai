
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Mock env vars for Pydantic Settings
os.environ["OPENAI_API_KEY"] = "sk-mock"
os.environ["TELEGRAM_BOT_TOKEN"] = "123:mock"
os.environ["TELEGRAM_CHAT_ID"] = "123"

from app.services.amocrm_service import AmoCRMService

class TestAmoCRMService(unittest.IsolatedAsyncioTestCase):
    async def test_apply_rules_measurement(self):
        """Test checking 'замер' rule."""
        db = AsyncMock()
        service = AmoCRMService(db)
        service._get_mapped_status = AsyncMock(return_value=123)
        service._update_lead_status = AsyncMock()
        
        tenant_id = 1
        lead_id = 100
        text = "Хочу записаться на замер завтра в 15:00"
        
        await service._apply_rules(None, tenant_id, lead_id, text)
        
        service._get_mapped_status.assert_called_with(tenant_id, "measurement_scheduled")
        service._update_lead_status.assert_called_with(None, lead_id, 123)

    async def test_apply_rules_lost(self):
        """Test checking 'отказ' rule."""
        db = AsyncMock()
        service = AmoCRMService(db)
        service._get_mapped_status = AsyncMock(return_value=456)
        service._update_lead_status = AsyncMock()
        
        tenant_id = 1
        lead_id = 100
        text = "Мне это не интересно вообще, отказ"
        
        await service._apply_rules(None, tenant_id, lead_id, text)
        
        service._get_mapped_status.assert_called_with(tenant_id, "lost")
        service._update_lead_status.assert_called_with(None, lead_id, 456)

    async def test_apply_rules_no_match(self):
        """Test when no rule matches."""
        db = AsyncMock()
        service = AmoCRMService(db)
        service._get_mapped_status = AsyncMock()
        service._update_lead_status = AsyncMock()
        
        tenant_id = 1
        lead_id = 100
        text = "Просто привет"
        
        await service._apply_rules(None, tenant_id, lead_id, text)
        
        service._get_mapped_status.assert_not_called()
        service._update_lead_status.assert_not_called()

if __name__ == "__main__":
    unittest.main()
