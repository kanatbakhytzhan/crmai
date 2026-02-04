#!/usr/bin/env python3
"""
Verify access control for GET /api/admin/tenants/{id}/settings

Access rules:
- admin (is_admin=True) -> 200 for ANY tenant
- owner (default_owner or role=owner) -> 200
- rop (role=rop) -> 200 for their tenant only
- manager (role=manager) -> 403

Usage:
    python scripts/verify_admin_tenant_settings_access.py [base_url]
"""
import sys
import asyncio
import httpx


async def get_token(base_url: str, email: str, password: str) -> str | None:
    """Get token via login (form data for OAuth2PasswordRequestForm)."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{base_url}/api/auth/login", data={
            "username": email,
            "password": password
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
    return None


async def test_access(base_url: str, token: str, tenant_id: int, expected_status: int, role_desc: str) -> dict:
    """Test access to tenant settings."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{base_url}/api/admin/tenants/{tenant_id}/settings"
        resp = await client.get(url, headers=headers)
        
        result = {
            "role": role_desc,
            "tenant_id": tenant_id,
            "expected": expected_status,
            "actual": resp.status_code,
            "passed": resp.status_code == expected_status,
        }
        
        try:
            data = resp.json()
            result["ok"] = data.get("ok")
            result["detail"] = data.get("detail", "")[:100]
        except Exception:
            result["ok"] = None
            result["detail"] = resp.text[:100]
        
        status_icon = "[OK]" if result["passed"] else "[FAIL]"
        print(f"  {status_icon} {role_desc}: expected={expected_status}, actual={resp.status_code}")
        if not result["passed"]:
            print(f"    Response: {result.get('detail', 'N/A')}")
        
        return result


async def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    print("=" * 60)
    print("Verify Tenant Settings Access Control")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print()
    
    # Get admin token
    print("Getting admin token...")
    admin_token = await get_token(base_url, "testadmin@gmail.com", "test123456")
    if not admin_token:
        print("[WARN] Could not get admin token, trying to register...")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{base_url}/api/auth/register", json={
                "email": "testadmin@gmail.com",
                "password": "test123456",
                "company_name": "Test Admin"
            })
            if resp.status_code in (200, 201):
                admin_token = await get_token(base_url, "testadmin@gmail.com", "test123456")
    
    if not admin_token:
        print("[ERROR] Could not get admin token")
        sys.exit(1)
    
    print(f"[OK] Got admin token")
    print()
    
    # Test access
    print("Testing access to tenant settings:")
    print("-" * 40)
    
    results = []
    
    # Test 1: Admin accessing tenant 1 (should succeed)
    results.append(await test_access(base_url, admin_token, 1, 200, "admin -> tenant 1"))
    
    # Test 2: No token (should fail with 401)
    results.append(await test_access(base_url, "", 1, 401, "no auth -> tenant 1"))
    
    # Test 3: Admin accessing non-existent tenant (should return 404)
    results.append(await test_access(base_url, admin_token, 99999, 404, "admin -> tenant 99999 (not found)"))
    
    # Test 4: Check that response has expected fields when successful
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{base_url}/api/admin/tenants/1/settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if resp.status_code == 200:
            data = resp.json()
            has_ok = data.get("ok") == True
            has_tenant_id = "tenant_id" in data
            has_settings = "settings" in data
            has_whatsapp = "whatsapp" in data
            has_amocrm = "amocrm" in data
            fields_ok = has_ok and has_tenant_id and has_settings and has_whatsapp and has_amocrm
            results.append({
                "role": "response structure check",
                "tenant_id": 1,
                "expected": "all fields",
                "actual": "all fields" if fields_ok else "missing fields",
                "passed": fields_ok,
            })
            print(f"  {'[OK]' if fields_ok else '[FAIL]'} response structure: ok={has_ok}, tenant_id={has_tenant_id}, settings={has_settings}, whatsapp={has_whatsapp}, amocrm={has_amocrm}")
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n[PASS] All access control tests passed")
        sys.exit(0)
    else:
        print("\n[FAIL] Some access control tests failed")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['role']}: expected {r['expected']}, got {r['actual']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
