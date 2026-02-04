#!/usr/bin/env python3
"""
Verify ChatFlow binding persistence and message sending.

Tests:
1. GET tenant settings - verify whatsapp section has all fields
2. PUT whatsapp binding - set chatflow_token, chatflow_instance_id, phone_number
3. GET whatsapp binding - verify persisted
4. GET /diagnostics/tenant/{id}/snapshot - verify chatflow_credentials_ok
5. (Optional) POST whatsapp/test - send test message

Usage:
  python scripts/verify_chatflow_binding.py [tenant_id] [base_url]
  
  # With test message:
  python scripts/verify_chatflow_binding.py 2 http://localhost:8000 --test-phone=+77001234567
"""
import sys
import asyncio
import argparse
import uuid
import httpx


async def get_token(base_url: str) -> str | None:
    """Get admin token via login."""
    async with httpx.AsyncClient(timeout=10) as client:
        for creds in [
            {"username": "testadmin@gmail.com", "password": "test123456"},
            {"username": "admin@example.com", "password": "admin123"},
        ]:
            try:
                resp = await client.post(f"{base_url}/api/auth/login", data=creds)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("access_token")
                    if token:
                        print(f"[OK] Logged in as {creds['username']}")
                        return token
            except Exception:
                pass
    return None


async def test_tenant_settings(base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/settings"""
    url = f"{base_url}/api/admin/tenants/{tenant_id}/settings"
    print(f"\n[TEST 1] GET {url}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"  [FAIL] Expected 200, got {resp.status_code}")
        return {"ok": False, "error": f"Status {resp.status_code}"}
    
    data = resp.json()
    
    # Check whatsapp section exists
    whatsapp = data.get("whatsapp", {})
    required_fields = ["binding_exists", "is_active", "phone_number", "chatflow_instance_id", "chatflow_token_masked"]
    missing = [f for f in required_fields if f not in whatsapp]
    
    if missing:
        print(f"  [WARN] Missing fields in whatsapp: {missing}")
    else:
        print(f"  [OK] All required whatsapp fields present")
    
    print(f"  binding_exists: {whatsapp.get('binding_exists')}")
    print(f"  is_active: {whatsapp.get('is_active')}")
    print(f"  phone_number: {whatsapp.get('phone_number')}")
    print(f"  chatflow_instance_id: {whatsapp.get('chatflow_instance_id')}")
    print(f"  chatflow_token_masked: {whatsapp.get('chatflow_token_masked')}")
    
    return {"ok": True, "data": data}


async def test_whatsapp_put(base_url: str, tenant_id: int, headers: dict, test_values: dict) -> dict:
    """Test PUT /api/admin/tenants/{id}/whatsapp"""
    url = f"{base_url}/api/admin/tenants/{tenant_id}/whatsapp"
    print(f"\n[TEST 2] PUT {url}")
    print(f"  Payload: token_len={len(test_values.get('chatflow_token', ''))}, instance_id={test_values.get('chatflow_instance_id', '')[:20]}...")
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(url, json=test_values, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code not in (200, 201):
        try:
            error = resp.json()
            print(f"  [FAIL] {error}")
        except Exception:
            print(f"  [FAIL] {resp.text[:200]}")
        return {"ok": False, "error": f"Status {resp.status_code}"}
    
    data = resp.json()
    print(f"  [OK] WhatsApp binding saved: {data.get('ok')}")
    
    return {"ok": True, "data": data}


async def test_whatsapp_get(base_url: str, tenant_id: int, headers: dict, expected_values: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/whatsapp - verify persistence"""
    url = f"{base_url}/api/admin/tenants/{tenant_id}/whatsapp"
    print(f"\n[TEST 3] GET {url} (verify persistence)")
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"  [FAIL] Expected 200, got {resp.status_code}")
        return {"ok": False, "error": f"Status {resp.status_code}"}
    
    data = resp.json()
    whatsapp_list = data.get("whatsapp", [])
    
    if not whatsapp_list:
        print(f"  [FAIL] No WhatsApp accounts returned")
        return {"ok": False, "error": "Empty list"}
    
    wa = whatsapp_list[0]
    
    # Verify values match
    token_match = (wa.get("chatflow_token") or "") == expected_values.get("chatflow_token", "")
    instance_match = (wa.get("chatflow_instance_id") or "") == expected_values.get("chatflow_instance_id", "")
    phone_match = (wa.get("phone_number") or "") == expected_values.get("phone_number", "")
    active_match = wa.get("active") == expected_values.get("is_active", True)
    
    print(f"  chatflow_token matches: {token_match}")
    print(f"  chatflow_instance_id matches: {instance_match}")
    print(f"  phone_number matches: {phone_match}")
    print(f"  is_active matches: {active_match}")
    
    all_match = token_match and instance_match and phone_match and active_match
    
    if all_match:
        print(f"  [OK] All values persisted correctly")
    else:
        print(f"  [FAIL] Some values did not persist")
    
    return {"ok": all_match, "data": data, "matches": {
        "token": token_match,
        "instance_id": instance_match,
        "phone": phone_match,
        "active": active_match,
    }}


async def test_snapshot(base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/diagnostics/tenant/{id}/snapshot"""
    url = f"{base_url}/api/admin/diagnostics/tenant/{tenant_id}/snapshot"
    print(f"\n[TEST 4] GET {url} (diagnostics)")
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"  [FAIL] Expected 200")
        return {"ok": False}
    
    data = resp.json()
    whatsapp = data.get("whatsapp", {})
    
    print(f"  chatflow_credentials_ok: {whatsapp.get('chatflow_credentials_ok')}")
    print(f"  chatflow_ready: {whatsapp.get('chatflow_ready')}")
    print(f"  chatflow_token_present: {whatsapp.get('chatflow_token_present')}")
    print(f"  chatflow_instance_present: {whatsapp.get('chatflow_instance_present')}")
    
    return {"ok": True, "data": data}


async def test_health(base_url: str, tenant_id: int, headers: dict) -> dict:
    """Test GET /api/admin/tenants/{id}/whatsapp/health"""
    url = f"{base_url}/api/admin/tenants/{tenant_id}/whatsapp/health"
    print(f"\n[TEST 5] GET {url} (health check)")
    
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"  [FAIL] Expected 200")
        return {"ok": False}
    
    data = resp.json()
    print(f"  credentials_configured: {data.get('credentials_configured')}")
    print(f"  health_check: {data.get('health_check')}")
    
    return {"ok": True, "data": data}


async def test_send(base_url: str, tenant_id: int, headers: dict, to_phone: str) -> dict:
    """Test POST /api/admin/tenants/{id}/whatsapp/test"""
    url = f"{base_url}/api/admin/tenants/{tenant_id}/whatsapp/test"
    print(f"\n[TEST 6] POST {url} (send test message)")
    
    body = {
        "to_phone": to_phone,
        "message": f"Test message from BuildCRM verification script #{uuid.uuid4().hex[:8]}"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body, headers=headers)
    
    print(f"  Status: {resp.status_code}")
    
    data = resp.json()
    
    if resp.status_code == 200 and data.get("ok"):
        print(f"  [OK] Message sent successfully")
        print(f"  provider_response: {data.get('provider_response')}")
    else:
        print(f"  [FAIL] Send failed: {data.get('error') or data.get('detail')}")
    
    return {"ok": data.get("ok", False), "data": data}


async def main():
    parser = argparse.ArgumentParser(description="Verify ChatFlow binding")
    parser.add_argument("tenant_id", type=int, nargs="?", default=1, help="Tenant ID")
    parser.add_argument("base_url", type=str, nargs="?", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--test-phone", type=str, help="Phone number to send test message (optional)")
    parser.add_argument("--token", type=str, help="Test ChatFlow token (optional)")
    parser.add_argument("--instance-id", type=str, help="Test ChatFlow instance_id (optional)")
    args = parser.parse_args()
    
    tenant_id = args.tenant_id
    base_url = args.base_url.rstrip("/")
    
    print("=" * 60)
    print("ChatFlow Binding Verification")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Tenant ID: {tenant_id}")
    
    # Get token
    token = await get_token(base_url)
    if not token:
        print("[FAIL] Could not authenticate")
        sys.exit(1)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    results = {}
    
    # Test 1: Get current settings
    results["settings"] = await test_tenant_settings(base_url, tenant_id, headers)
    
    # Test 2: PUT WhatsApp binding with test values
    test_values = {
        "chatflow_token": args.token or f"test_token_{uuid.uuid4().hex[:16]}",
        "chatflow_instance_id": args.instance_id or f"test_instance_{uuid.uuid4().hex[:8]}",
        "phone_number": "+77001234567",
        "is_active": True,
    }
    results["put"] = await test_whatsapp_put(base_url, tenant_id, headers, test_values)
    
    # Test 3: GET WhatsApp to verify persistence
    if results["put"].get("ok"):
        results["get"] = await test_whatsapp_get(base_url, tenant_id, headers, test_values)
    
    # Test 4: Snapshot
    results["snapshot"] = await test_snapshot(base_url, tenant_id, headers)
    
    # Test 5: Health check
    results["health"] = await test_health(base_url, tenant_id, headers)
    
    # Test 6: Send test message (optional)
    if args.test_phone:
        results["send"] = await test_send(base_url, tenant_id, headers, args.test_phone)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_pass = True
    for name, result in results.items():
        ok = result.get("ok", False)
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {name}")
        if not ok:
            all_pass = False
    
    print("=" * 60)
    
    if all_pass:
        print("\n[PASS] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAIL] Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
