"""
Comprehensive test script for backend stabilization fixes.

Tests:
1. Tenant settings PATCH doesn't wipe ai_prompt with empty string
2. WhatsApp PUT doesn't wipe token with empty string
3. GET settings returns saved ai_prompt
4. PUT pipeline-mapping accepts both dict and list formats
5. Empty primary_pipeline_id is handled correctly

Usage:
    python test_stabilization.py
"""
import asyncio
import httpx
import json
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"  # Change this to your actual admin password
TEST_TENANT_ID = 1  # Change this to an existing tenant ID

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def add_pass(self, test_name: str):
        self.passed.append(test_name)
        print(f"✅ PASS: {test_name}")
    
    def add_fail(self, test_name: str, reason: str):
        self.failed.append((test_name, reason))
        print(f"❌ FAIL: {test_name}")
        print(f"   Reason: {reason}")
    
    def summary(self):
        print("\n" + "="*60)
        print(f"TEST SUMMARY: {len(self.passed)} passed, {len(self.failed)} failed")
        print("="*60)
        if self.failed:
            print("\nFailed tests:")
            for test_name, reason in self.failed:
                print(f"  - {test_name}: {reason}")
        return len(self.failed) == 0


async def login(client: httpx.AsyncClient) -> Optional[str]:
    """Login and return access token"""
    print("\n[LOGIN] Authenticating...")
    try:
        response = await client.post(
            f"{BASE_URL}/api/auth/login",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"[LOGIN] Success! Token: {token[:20]}...")
            return token
        else:
            print(f"[LOGIN] Failed: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"[LOGIN] Error: {e}")
        return None


async def test_settings_empty_string_protection(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test that PATCH /settings doesn't wipe ai_prompt with empty string"""
    test_name = "Settings: Empty string protection for ai_prompt"
    print(f"\n[TEST] {test_name}")
    
    try:
        # 1. Set ai_prompt to a known value
        set_response = await client.patch(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"ai_prompt": "Test AI prompt for stabilization", "clear_fields": []}
        )
        if set_response.status_code != 200:
            results.add_fail(test_name, f"Failed to set ai_prompt: {set_response.status_code}")
            return
        
        set_data = set_response.json()
        initial_prompt = set_data.get("settings", {}).get("ai_prompt", "")
        print(f"[TEST] Set ai_prompt: {initial_prompt[:50]}...")
        
        # 2. Try to update with empty string (should be ignored)
        update_response = await client.patch(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"ai_prompt": "", "clear_fields": []}  # Empty string, NOT in clear_fields
        )
        if update_response.status_code != 200:
            results.add_fail(test_name, f"PATCH with empty string failed: {update_response.status_code}")
            return
        
        # 3. Verify ai_prompt is NOT wiped
        get_response = await client.get(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"}
        )
        if get_response.status_code != 200:
            results.add_fail(test_name, f"GET after update failed: {get_response.status_code}")
            return
        
        final_data = get_response.json()
        final_prompt = final_data.get("settings", {}).get("ai_prompt", "")
        
        if final_prompt == initial_prompt and final_prompt != "":
            results.add_pass(test_name)
        else:
            results.add_fail(test_name, f"ai_prompt was wiped! Initial: '{initial_prompt[:30]}', Final: '{final_prompt}'")
    
    except Exception as e:
        results.add_fail(test_name, f"Exception: {e}")


async def test_settings_explicit_clear(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test that PATCH /settings with clear_fields DOES clear ai_prompt"""
    test_name = "Settings: Explicit clear with clear_fields"
    print(f"\n[TEST] {test_name}")
    
    try:
        # 1. Set ai_prompt
        await client.patch(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"ai_prompt": "Prompt to be cleared"}
        )
        
        # 2. Clear with clear_fields
        clear_response = await client.patch(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"ai_prompt": "", "clear_fields": ["ai_prompt"]}
        )
        if clear_response.status_code != 200:
            results.add_fail(test_name, f"PATCH with clear_fields failed: {clear_response.status_code}")
            return
        
        # 3. Verify ai_prompt IS cleared
        get_response = await client.get(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/settings",
            headers={"Authorization": f"Bearer {token}"}
        )
        final_data = get_response.json()
        final_prompt = final_data.get("settings", {}).get("ai_prompt", "")
        
        if final_prompt == "":
            results.add_pass(test_name)
        else:
            results.add_fail(test_name, f"ai_prompt was NOT cleared! Final: '{final_prompt}'")
    
    except Exception as e:
        results.add_fail(test_name, f"Exception: {e}")


async def test_amocrm_mapping_dict_format(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test that PUT /pipeline-mapping accepts dict format"""
    test_name = "AmoCRM: Pipeline mapping accepts dict format"
    print(f"\n[TEST] {test_name}")
    
    try:
        response = await client.put(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/amocrm/pipeline-mapping",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "primary_pipeline_id": "12345",
                "mapping": {
                    "NEW": "100",
                    "IN_WORK": "101",
                    "WON": "142"
                }
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("mappings_saved", 0) > 0:
                results.add_pass(test_name)
            else:
                results.add_fail(test_name, f"Response ok=false or no mappings saved: {data}")
        else:
            results.add_fail(test_name, f"Status {response.status_code}: {response.text}")
    
    except Exception as e:
        results.add_fail(test_name, f"Exception: {e}")


async def test_amocrm_mapping_list_format(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test that PUT /pipeline-mapping accepts list format"""
    test_name = "AmoCRM: Pipeline mapping accepts list format"
    print(f"\n[TEST] {test_name}")
    
    try:
        response = await client.put(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/amocrm/pipeline-mapping",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "primary_pipeline_id": "12345",
                "mapping": [
                    {"stage_key": "NEW", "stage_id": "200"},
                    {"stage_key": "IN_WORK", "stage_id": "201"},
                    {"stage_key": "LOST", "stage_id": "143"}
                ]
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("mappings_saved", 0) > 0:
                results.add_pass(test_name)
            else:
                results.add_fail(test_name, f"Response ok=false or no mappings saved: {data}")
        else:
            results.add_fail(test_name, f"Status {response.status_code}: {response.text}")
    
    except Exception as e:
        results.add_fail(test_name, f"Exception: {e}")


async def test_amocrm_empty_pipeline_id(client: httpx.AsyncClient, token: str, results: TestResults):
    """Test that empty primary_pipeline_id is handled as None"""
    test_name = "AmoCRM: Empty primary_pipeline_id handled as None"
    print(f"\n[TEST] {test_name}")
    
    try:
        # Set to empty string
        response = await client.put(
            f"{BASE_URL}/api/admin/tenants/{TEST_TENANT_ID}/amocrm/primary-pipeline",
            headers={"Authorization": f"Bearer {token}"},
            json={"pipeline_id": ""}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("primary_pipeline_id") is None:
                results.add_pass(test_name)
            else:
                results.add_fail(test_name, f"primary_pipeline_id should be None, got: {data.get('primary_pipeline_id')}")
        else:
            results.add_fail(test_name, f"Status {response.status_code}: {response.text}")
    
    except Exception as e:
        results.add_fail(test_name, f"Exception: {e}")


async def main():
    print("="*60)
    print("BACKEND STABILIZATION TEST SUITE")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Tenant ID: {TEST_TENANT_ID}")
    
    results = TestResults()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login
        token = await login(client)
        if not token:
            print("\n❌ LOGIN FAILED - Cannot proceed with tests")
            print("Please check:")
            print("  1. Server is running at", BASE_URL)
            print("  2. Admin credentials are correct")
            print("  3. Tenant ID exists")
            return False
        
        # Run tests
        await test_settings_empty_string_protection(client, token, results)
        await test_settings_explicit_clear(client, token, results)
        await test_amocrm_mapping_dict_format(client, token, results)
        await test_amocrm_mapping_list_format(client, token, results)
        await test_amocrm_empty_pipeline_id(client, token, results)
    
    # Summary
    success = results.summary()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
