#!/usr/bin/env python3
"""
Comprehensive test for tenant settings persistence:
1. GET settings - verify structure
2. PATCH settings - update ai_prompt and other fields
3. GET settings - verify changes persisted
4. Check snapshot endpoint consistency

Usage: python scripts/verify_tenant_settings.py [tenant_id] [base_url]

Defaults:
  tenant_id = 1
  base_url = http://localhost:8000
"""
import sys
import asyncio
import httpx
import uuid


async def get_admin_token(base_url: str) -> str | None:
    """Try to get admin token via login (form data for OAuth2PasswordRequestForm)."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Try default admin credentials with form data
        for creds in [
            {"username": "testadmin@gmail.com", "password": "test123456"},
            {"username": "admin@example.com", "password": "admin123"},
            {"username": "admin@admin.com", "password": "admin123"},
        ]:
            try:
                resp = await client.post(f"{base_url}/api/auth/login", data=creds)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("access_token") or data.get("token")
                    if token:
                        print(f"[OK] Got token with {creds['username']}")
                        return token
            except Exception:
                pass
        
        # Try to create and login a new user if needed
        try:
            resp = await client.post(f"{base_url}/api/auth/register", json={
                "email": "verifytest@gmail.com",
                "password": "verify123456",
                "company_name": "Verify Test"
            })
            if resp.status_code in (200, 201):
                # Login the new user
                resp = await client.post(f"{base_url}/api/auth/login", data={
                    "username": "verifytest@gmail.com",
                    "password": "verify123456"
                })
                if resp.status_code == 200:
                    token = resp.json().get("access_token")
                    if token:
                        print(f"[OK] Registered and got token")
                        return token
        except Exception:
            pass
    
    return None


async def test_endpoint(base_url: str, tenant_id: int, token: str | None) -> dict:
    """Test the settings endpoint."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{base_url}/api/admin/tenants/{tenant_id}/settings"
        print(f"\n[TEST] GET {url}")
        print(f"[TEST] Headers: Authorization={'Bearer ***' if token else 'None'}")
        
        try:
            resp = await client.get(url, headers=headers)
            print(f"[RESULT] Status: {resp.status_code}")
            print(f"[RESULT] Content-Type: {resp.headers.get('content-type', 'N/A')}")
            
            try:
                data = resp.json()
                print(f"[RESULT] JSON: {data}")
                return {
                    "status": resp.status_code,
                    "ok": data.get("ok", False),
                    "detail": data.get("detail"),
                    "has_tenant_id": "tenant_id" in data,
                    "has_settings": "settings" in data,
                    "has_whatsapp": "whatsapp" in data,
                    "has_amocrm": "amocrm" in data,
                    "has_mappings": "mappings" in data,
                    "raw": data
                }
            except Exception as e:
                print(f"[RESULT] Not JSON: {resp.text[:500]}")
                return {"status": resp.status_code, "ok": False, "detail": f"Not JSON: {str(e)}"}
                
        except httpx.RequestError as e:
            print(f"[ERROR] Request failed: {e}")
            return {"status": 0, "ok": False, "detail": str(e)}


async def test_snapshot(base_url: str, tenant_id: int, token: str | None) -> dict:
    """Test the snapshot endpoint for comparison."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{base_url}/api/admin/diagnostics/tenant/{tenant_id}/snapshot"
        print(f"\n[TEST] GET {url} (snapshot for comparison)")
        
        try:
            resp = await client.get(url, headers=headers)
            print(f"[RESULT] Snapshot status: {resp.status_code}")
            
            try:
                data = resp.json()
                print(f"[RESULT] Snapshot ok={data.get('ok')}")
                return {"status": resp.status_code, "ok": data.get("ok", False), "data": data}
            except Exception:
                return {"status": resp.status_code, "ok": False}
                
        except Exception as e:
            return {"status": 0, "ok": False, "detail": str(e)}


async def test_patch_settings(base_url: str, tenant_id: int, token: str | None) -> dict:
    """Test PATCH settings with unique values and verify persistence."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # Generate unique test values
    test_id = str(uuid.uuid4())[:8]
    test_prompt = f"Test AI prompt #{test_id} - This is a test prompt for verification."
    test_behavior = "polite_close"
    
    async with httpx.AsyncClient(timeout=15) as client:
        url = f"{base_url}/api/admin/tenants/{tenant_id}/settings"
        
        # Step 1: PATCH with test values
        print(f"\n[TEST] PATCH {url}")
        print(f"[TEST] Payload: ai_prompt='{test_prompt[:50]}...', ai_after_lead_submitted_behavior='{test_behavior}'")
        
        patch_data = {
            "ai_prompt": test_prompt,
            "ai_after_lead_submitted_behavior": test_behavior,
        }
        
        try:
            resp = await client.patch(url, json=patch_data, headers=headers)
            print(f"[RESULT] PATCH Status: {resp.status_code}")
            
            if resp.status_code != 200:
                try:
                    error_data = resp.json()
                    print(f"[RESULT] PATCH Error: {error_data}")
                    return {"status": resp.status_code, "ok": False, "detail": error_data.get("detail", "Unknown error")}
                except Exception:
                    return {"status": resp.status_code, "ok": False, "detail": resp.text[:200]}
            
            patch_result = resp.json()
            print(f"[RESULT] PATCH Response ok={patch_result.get('ok')}")
            
        except httpx.RequestError as e:
            print(f"[ERROR] PATCH failed: {e}")
            return {"status": 0, "ok": False, "detail": str(e)}
        
        # Step 2: GET to verify persistence
        print(f"\n[TEST] GET {url} (verify persistence)")
        
        try:
            resp = await client.get(url, headers=headers)
            print(f"[RESULT] GET Status: {resp.status_code}")
            
            if resp.status_code != 200:
                return {"status": resp.status_code, "ok": False, "detail": "GET after PATCH failed"}
            
            get_result = resp.json()
            
            # Verify values persisted
            settings = get_result.get("settings", {})
            actual_prompt = settings.get("ai_prompt", "")
            actual_behavior = settings.get("ai_after_lead_submitted_behavior", "")
            
            prompt_match = actual_prompt == test_prompt
            behavior_match = actual_behavior == test_behavior
            
            print(f"[RESULT] ai_prompt matches: {prompt_match}")
            print(f"[RESULT] ai_after_lead_submitted_behavior matches: {behavior_match}")
            
            if not prompt_match:
                print(f"[WARN] Expected prompt: '{test_prompt[:50]}...'")
                print(f"[WARN] Actual prompt: '{actual_prompt[:50] if actual_prompt else '(empty)'}...'")
            
            return {
                "status": resp.status_code,
                "ok": prompt_match and behavior_match,
                "prompt_match": prompt_match,
                "behavior_match": behavior_match,
                "expected_prompt": test_prompt,
                "actual_prompt": actual_prompt,
            }
            
        except httpx.RequestError as e:
            print(f"[ERROR] GET after PATCH failed: {e}")
            return {"status": 0, "ok": False, "detail": str(e)}


async def test_pipelines_discovery(base_url: str, tenant_id: int, token: str | None) -> dict:
    """Test AmoCRM pipelines discovery endpoint (if connected)."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    async with httpx.AsyncClient(timeout=15) as client:
        url = f"{base_url}/api/admin/tenants/{tenant_id}/amocrm/pipelines"
        print(f"\n[TEST] GET {url} (AmoCRM pipelines)")
        
        try:
            resp = await client.get(url, headers=headers)
            print(f"[RESULT] Pipelines Status: {resp.status_code}")
            
            data = resp.json()
            if resp.status_code == 400 and data.get("code") == "NOT_CONNECTED":
                print(f"[INFO] AmoCRM not connected - skipping")
                return {"status": resp.status_code, "ok": True, "skipped": True, "reason": "not connected"}
            
            if resp.status_code == 200 and data.get("ok"):
                pipelines = data.get("pipelines", [])
                print(f"[RESULT] Found {len(pipelines)} pipelines")
                for p in pipelines[:3]:  # Show first 3
                    print(f"  - {p.get('id')}: {p.get('name')} (is_main={p.get('is_main')})")
                return {"status": resp.status_code, "ok": True, "count": len(pipelines)}
            
            return {"status": resp.status_code, "ok": False, "detail": data.get("detail")}
            
        except Exception as e:
            return {"status": 0, "ok": False, "detail": str(e)}


async def main():
    tenant_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    
    print(f"=" * 60)
    print(f"Tenant Settings Persistence Test")
    print(f"=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Tenant ID: {tenant_id}")
    
    # Get token
    token = await get_admin_token(base_url)
    if not token:
        print("[WARN] Could not get auth token, will try without")
    
    results = {}
    
    # Test 1: GET settings endpoint (structure)
    settings_result = await test_endpoint(base_url, tenant_id, token)
    results["get_settings"] = settings_result
    
    # Test 2: PATCH + GET (persistence)
    if settings_result.get("status") == 200:
        patch_result = await test_patch_settings(base_url, tenant_id, token)
        results["patch_persistence"] = patch_result
    else:
        print("\n[SKIP] Skipping PATCH test - GET failed")
        results["patch_persistence"] = {"ok": False, "skipped": True}
    
    # Test 3: Snapshot endpoint for comparison
    snapshot_result = await test_snapshot(base_url, tenant_id, token)
    results["snapshot"] = snapshot_result
    
    # Test 4: AmoCRM pipelines discovery
    pipelines_result = await test_pipelines_discovery(base_url, tenant_id, token)
    results["pipelines"] = pipelines_result
    
    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    
    all_pass = True
    
    # GET Settings
    get_ok = results["get_settings"].get("ok") and results["get_settings"].get("status") == 200
    print(f"[{'OK' if get_ok else 'FAIL'}] GET /settings: status={results['get_settings'].get('status')}")
    if get_ok:
        missing = []
        for field in ["has_tenant_id", "has_settings", "has_whatsapp", "has_amocrm", "has_mappings"]:
            if not results["get_settings"].get(field):
                missing.append(field.replace("has_", ""))
        if missing:
            print(f"      [WARN] Missing fields: {missing}")
    all_pass = all_pass and get_ok
    
    # PATCH Persistence
    patch_ok = results["patch_persistence"].get("ok")
    if results["patch_persistence"].get("skipped"):
        print(f"[SKIP] PATCH persistence: skipped")
    else:
        print(f"[{'OK' if patch_ok else 'FAIL'}] PATCH persistence:")
        print(f"      ai_prompt: {'matches' if results['patch_persistence'].get('prompt_match') else 'MISMATCH'}")
        print(f"      behavior:  {'matches' if results['patch_persistence'].get('behavior_match') else 'MISMATCH'}")
        all_pass = all_pass and patch_ok
    
    # Snapshot
    snapshot_ok = results["snapshot"].get("ok")
    print(f"[{'OK' if snapshot_ok else 'FAIL'}] Snapshot: status={results['snapshot'].get('status')}")
    all_pass = all_pass and snapshot_ok
    
    # Pipelines
    if results["pipelines"].get("skipped"):
        print(f"[INFO] Pipelines: AmoCRM not connected (ok)")
    else:
        pipelines_ok = results["pipelines"].get("ok")
        print(f"[{'OK' if pipelines_ok else 'FAIL'}] Pipelines: {results['pipelines'].get('count', 0)} found")
    
    print(f"{'=' * 60}")
    
    # Exit code
    if all_pass:
        print("\n[PASS] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAIL] Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
