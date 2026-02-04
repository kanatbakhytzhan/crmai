
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Mock env vars
os.environ["OPENAI_API_KEY"] = "sk-mock"
os.environ["TELEGRAM_BOT_TOKEN"] = "123:mock"
os.environ["TELEGRAM_CHAT_ID"] = "123"

from app.api.endpoints import admin_tenants
from app.schemas import tenant as tenant_schemas

class TestAmoCRMEndpoints(unittest.IsolatedAsyncioTestCase):
    async def test_get_pipelines(self):
        # Mock dependencies
        db = AsyncMock()
        mock_service = list_pipelines = AsyncMock()
        
        # Setup expected data
        mock_pipelines = [{
            "id": 123, "name": "Pipeline 1", "is_main": True,
            "_embedded": {"statuses": [{"id": 1, "name": "S1"}]}
        }]
        
        with patch("app.services.amocrm_service.AmoCRMService") as mock_cls:
            service_instance = mock_cls.return_value
            service_instance.get_account_info = AsyncMock(return_value={"connected": True})
            service_instance.list_pipelines = AsyncMock(return_value=mock_pipelines)
            
            # Call endpoint function directly
            result = await admin_tenants.get_amocrm_pipelines(1, db)
            
            self.assertTrue(result["ok"])
            self.assertEqual(len(result["pipelines"]), 1)
            self.assertEqual(result["pipelines"][0]["id"], 123)
            self.assertEqual(result["pipelines"][0]["statuses"][0]["name"], "S1")

    async def test_set_primary_pipeline(self):
        db = AsyncMock()
        tenant = MagicMock()
        tenant.default_pipeline_id = None
        
        with patch("app.api.endpoints.admin_tenants.crud.get_tenant_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = tenant
            
            body = tenant_schemas.AmoPrimaryPipelineUpdate(pipeline_id="999")
            result = await admin_tenants.set_amocrm_primary_pipeline(1, body, db)
            
            self.assertTrue(result["ok"])
            self.assertEqual(tenant.default_pipeline_id, "999")
            db.commit.assert_awaited_once()

    async def test_save_mapping(self):
        db = AsyncMock()
        tenant = MagicMock()
        
        with patch("app.api.endpoints.admin_tenants.crud.get_tenant_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = tenant
            
            body = tenant_schemas.AmoPipelineMappingUpdate(
                primary_pipeline_id="888",
                mapping={"NEW": "100", "WON": "200"}
            )
            
            # Mock db.execute for existing check
            # We want to match logic: first loop executes select check
            # Let's mock execute result to return None (no existing)
            mock_result = MagicMock()
            mock_result.scalars().first.return_value = None
            db.execute.return_value = mock_result
            
            result = await admin_tenants.save_amocrm_pipeline_mapping(1, body, db)
            
            self.assertTrue(result["ok"])
            self.assertEqual(tenant.default_pipeline_id, "888")
            # We expect db.add to be called twice
            self.assertEqual(db.add.call_count, 2)
            db.commit.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
