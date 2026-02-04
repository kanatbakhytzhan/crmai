#!/usr/bin/env python3
"""
Quick test for ai_prompt persistence.
Tests PATCH and GET to verify ai_prompt is saved and returned correctly.
"""
import requests
import sys

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "testadmin@gmail.com"
TEST_PASSWORD = "test123456"


def main():
    tenant_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    # Login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if login_resp.status_code != 200:
        print(f"[FAIL] Login failed: {login_resp.status_code}")
        return 1
    
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[OK] Logged in as {TEST_EMAIL}\n")
    
    # Test 1: PATCH ai_prompt
    test_prompt = "This is a test AI prompt for verification - 12345!"
    patch_resp = requests.patch(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}/settings",
        headers=headers,
        json={"ai_prompt": test_prompt}
    )
    print(f"[TEST 1] PATCH /settings with ai_prompt")
    print(f"  Status: {patch_resp.status_code}")
    
    if patch_resp.status_code != 200:
        print(f"  [FAIL] PATCH failed: {patch_resp.text}")
        return 1
    
    patch_data = patch_resp.json()
    patch_ai_prompt = patch_data.get("settings", {}).get("ai_prompt", "")
    patch_ai_prompt_len = patch_data.get("settings", {}).get("ai_prompt_len", 0)
    print(f"  ai_prompt returned: '{patch_ai_prompt[:50]}...' (len={patch_ai_prompt_len})")
    
    if patch_ai_prompt != test_prompt:
        print(f"  [FAIL] PATCH response ai_prompt doesn't match!")
        return 1
    print(f"  [OK] PATCH response correct\n")
    
    # Test 2: GET settings to verify persistence
    get_resp = requests.get(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}/settings",
        headers=headers
    )
    print(f"[TEST 2] GET /settings (verify persistence)")
    print(f"  Status: {get_resp.status_code}")
    
    if get_resp.status_code != 200:
        print(f"  [FAIL] GET failed: {get_resp.text}")
        return 1
    
    get_data = get_resp.json()
    get_ai_prompt = get_data.get("settings", {}).get("ai_prompt", "")
    get_ai_prompt_len = get_data.get("settings", {}).get("ai_prompt_len", 0)
    print(f"  ai_prompt: '{get_ai_prompt}'")
    print(f"  ai_prompt_len: {get_ai_prompt_len}")
    
    if get_ai_prompt != test_prompt:
        print(f"  [FAIL] GET ai_prompt doesn't match! Expected: '{test_prompt}'")
        return 1
    
    if get_ai_prompt_len != len(test_prompt):
        print(f"  [FAIL] GET ai_prompt_len doesn't match! Expected: {len(test_prompt)}")
        return 1
    
    print(f"  [OK] ai_prompt persisted correctly\n")
    
    # Test 3: PATCH without ai_prompt (should NOT wipe it)
    print(f"[TEST 3] PATCH /settings without ai_prompt (merge test)")
    patch2_resp = requests.patch(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}/settings",
        headers=headers,
        json={"whatsapp_source": "chatflow"}  # Only update whatsapp_source
    )
    print(f"  Status: {patch2_resp.status_code}")
    
    if patch2_resp.status_code != 200:
        print(f"  [FAIL] PATCH failed: {patch2_resp.text}")
        return 1
    
    # Verify ai_prompt wasn't wiped
    get2_resp = requests.get(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}/settings",
        headers=headers
    )
    get2_data = get2_resp.json()
    get2_ai_prompt = get2_data.get("settings", {}).get("ai_prompt", "")
    
    if get2_ai_prompt != test_prompt:
        print(f"  [FAIL] ai_prompt was wiped! Got: '{get2_ai_prompt}'")
        return 1
    
    print(f"  [OK] ai_prompt preserved (merge semantics working)\n")
    
    # Test 4: Snapshot should also show ai_prompt
    print(f"[TEST 4] GET /diagnostics/tenant/{tenant_id}/snapshot")
    snap_resp = requests.get(
        f"{BASE_URL}/api/admin/diagnostics/tenant/{tenant_id}/snapshot",
        headers=headers
    )
    print(f"  Status: {snap_resp.status_code}")
    
    if snap_resp.status_code != 200:
        print(f"  [FAIL] Snapshot failed: {snap_resp.text}")
        return 1
    
    snap_data = snap_resp.json()
    snap_ai_prompt_len = snap_data.get("settings", {}).get("ai_prompt_len", 0)
    snap_ai_prompt_is_set = snap_data.get("settings", {}).get("ai_prompt_is_set", False)
    print(f"  ai_prompt_len: {snap_ai_prompt_len}")
    print(f"  ai_prompt_is_set: {snap_ai_prompt_is_set}")
    
    if snap_ai_prompt_len != len(test_prompt):
        print(f"  [FAIL] Snapshot ai_prompt_len doesn't match!")
        return 1
    
    if not snap_ai_prompt_is_set:
        print(f"  [FAIL] Snapshot ai_prompt_is_set should be True!")
        return 1
    
    print(f"  [OK] Snapshot correct\n")
    
    print("=" * 60)
    print("[PASS] All ai_prompt persistence tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
