#!/usr/bin/env python3
"""
Smoke test for GET /api/admin/tenants/{id}/settings endpoint.
Usage: python scripts/verify_tenant_settings.py [tenant_id] [base_url]

Defaults:
  tenant_id = 1
  base_url = http://localhost:8000
"""
import sys
import asyncio
import httpx


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


async def main():
    tenant_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
    
    print(f"=" * 60)
    print(f"Verify Tenant Settings Endpoint")
    print(f"=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Tenant ID: {tenant_id}")
    
    # Get token
    token = await get_admin_token(base_url)
    if not token:
        print("[WARN] Could not get auth token, will try without")
    
    # Test settings endpoint
    settings_result = await test_endpoint(base_url, tenant_id, token)
    
    # Test snapshot endpoint for comparison
    snapshot_result = await test_snapshot(base_url, tenant_id, token)
    
    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Settings endpoint: status={settings_result['status']}, ok={settings_result.get('ok')}")
    print(f"Snapshot endpoint: status={snapshot_result['status']}, ok={snapshot_result.get('ok')}")
    
    # Check expected fields
    if settings_result.get("ok"):
        missing = []
        for field in ["has_tenant_id", "has_settings", "has_whatsapp", "has_amocrm", "has_mappings"]:
            if not settings_result.get(field):
                missing.append(field.replace("has_", ""))
        if missing:
            print(f"[WARN] Missing fields: {missing}")
        else:
            print("[OK] All expected fields present")
    
    # Exit code
    if settings_result.get("ok") and settings_result.get("status") == 200:
        print("\n[PASS] Tenant settings endpoint working correctly")
        sys.exit(0)
    else:
        print(f"\n[FAIL] Tenant settings endpoint NOT working")
        print(f"  Status: {settings_result.get('status')}")
        print(f"  Detail: {settings_result.get('detail')}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
