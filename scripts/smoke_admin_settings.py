#!/usr/bin/env python3
"""
Smoke test for admin tenant settings API.

Tests:
1. GET /api/admin/tenants/{id}/settings - should return 200 with settings
2. PATCH /api/admin/tenants/{id}/settings - should persist and return updated settings
3. GET /api/admin/tenants/{id}/amocrm/auth-url with various domain formats
4. GET /api/admin/tenants/{id}/settings/debug - should return access info

Usage:
    python scripts/smoke_admin_settings.py [base_url] [tenant_id]
    
    Defaults:
        base_url = http://localhost:8000
        tenant_id = 1
"""
import sys
import asyncio
import httpx
import json


async def get_token(base_url: str, email: str = "testadmin@gmail.com", password: str = "test123456") -> str | None:
    """Get auth token via login."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{base_url}/api/auth/login", data={
            "username": email,
            "password": password
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
    return None


async def test_get_settings(client: httpx.AsyncClient, base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/settings"""
    print("\n[TEST] GET /api/admin/tenants/{id}/settings")
    try:
        resp = await client.get(f"{base_url}/api/admin/tenants/{tenant_id}/settings", headers=headers)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  ok: {data.get('ok')}")
        if data.get("ok"):
            print(f"  tenant_name: {data.get('tenant_name')}")
            print(f"  settings.whatsapp_source: {data.get('settings', {}).get('whatsapp_source')}")
            print(f"  settings.ai_enabled_global: {data.get('settings', {}).get('ai_enabled_global')}")
        else:
            print(f"  detail: {data.get('detail')}")
        return {"passed": resp.status_code == 200 and data.get("ok"), "data": data}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"passed": False, "error": str(e)}


async def test_patch_settings(client: httpx.AsyncClient, base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test PATCH /api/admin/tenants/{id}/settings"""
    print("\n[TEST] PATCH /api/admin/tenants/{id}/settings")
    try:
        # Update a setting
        resp = await client.patch(
            f"{base_url}/api/admin/tenants/{tenant_id}/settings",
            headers=headers,
            json={"ai_enabled_global": True, "ai_after_lead_submitted_behavior": "polite_close"}
        )
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  ok: {data.get('ok')}")
        if not data.get("ok"):
            print(f"  detail: {data.get('detail')}")
        return {"passed": resp.status_code == 200 and data.get("ok"), "data": data}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"passed": False, "error": str(e)}


async def test_amocrm_auth_url(client: httpx.AsyncClient, base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/amocrm/auth-url with various domain formats"""
    print("\n[TEST] GET /api/admin/tenants/{id}/amocrm/auth-url (domain normalization)")
    
    test_domains = [
        ("company.amocrm.ru", True),
        ("https://company.amocrm.ru", True),
        ("https://company.amocrm.ru/leads/", True),
        ("http://company.amocrm.ru/leads/pipeline/123", True),
        ("company.kommo.com/anything", True),
        ("invalid-domain.com", False),  # Should fail validation
    ]
    
    results = []
    for domain, should_pass_validation in test_domains:
        try:
            resp = await client.get(
                f"{base_url}/api/admin/tenants/{tenant_id}/amocrm/auth-url",
                headers=headers,
                params={"base_domain": domain}
            )
            data = resp.json()
            
            # Check if it passed validation (might still fail due to missing ENV)
            passed_validation = resp.status_code != 422 or "INVALID_DOMAIN_FORMAT" not in data.get("code", "")
            
            status = "[OK]" if passed_validation == should_pass_validation else "[FAIL]"
            print(f"  {status} domain='{domain}' -> status={resp.status_code}, ok={data.get('ok')}")
            if not data.get("ok") and data.get("detail"):
                print(f"       detail: {data.get('detail')[:80]}")
            
            results.append({
                "domain": domain,
                "passed": passed_validation == should_pass_validation,
                "status": resp.status_code
            })
        except Exception as e:
            print(f"  [ERROR] domain='{domain}' -> {e}")
            results.append({"domain": domain, "passed": False, "error": str(e)})
    
    all_passed = all(r["passed"] for r in results)
    return {"passed": all_passed, "results": results}


async def test_debug_endpoint(client: httpx.AsyncClient, base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/settings/debug"""
    print("\n[TEST] GET /api/admin/tenants/{id}/settings/debug")
    try:
        resp = await client.get(f"{base_url}/api/admin/tenants/{tenant_id}/settings/debug", headers=headers)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  ok: {data.get('ok')}")
        if data.get("debug"):
            debug = data["debug"]
            print(f"  current_user.email: {debug.get('current_user', {}).get('email')}")
            print(f"  current_user.is_admin: {debug.get('current_user', {}).get('is_admin')}")
            print(f"  access_decision.allowed: {debug.get('access_decision', {}).get('allowed')}")
            print(f"  access_decision.reason: {debug.get('access_decision', {}).get('reason')}")
        return {"passed": resp.status_code == 200 and data.get("ok"), "data": data}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"passed": False, "error": str(e)}


async def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    tenant_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    print("=" * 60)
    print("Admin Settings API Smoke Test")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Tenant ID: {tenant_id}")
    
    # Get token
    print("\n[AUTH] Getting token...")
    token = await get_token(base_url)
    if not token:
        print("[ERROR] Could not get auth token")
        sys.exit(1)
    print("[OK] Got auth token")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        results = []
        
        # Test 1: GET settings
        results.append(("GET settings", await test_get_settings(client, base_url, tenant_id, headers)))
        
        # Test 2: PATCH settings
        results.append(("PATCH settings", await test_patch_settings(client, base_url, tenant_id, headers)))
        
        # Test 3: AmoCRM auth-url domain normalization
        results.append(("AmoCRM auth-url", await test_amocrm_auth_url(client, base_url, tenant_id, headers)))
        
        # Test 4: Debug endpoint
        results.append(("Debug endpoint", await test_debug_endpoint(client, base_url, tenant_id, headers)))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "[PASS]" if result["passed"] else "[FAIL]"
        print(f"  {status} {name}")
        if result["passed"]:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n[SUCCESS] All smoke tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
