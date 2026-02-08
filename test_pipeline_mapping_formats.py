"""
Test script for AmoCRM Pipeline Mapping API - Backward Compatibility

Tests all three supported payload formats:
1. Current format: {mappings: [...]}
2. Legacy dict format: {mapping: {stage_key: stage_id}, primary_pipeline_id: ...}
3. Legacy array format: {mapping: [{stage_key, stage_id}], primary_pipeline_id: ...}
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
TENANT_ID = 1
TOKEN = None  # Will be set after login

def login():
    """Login and get token"""
    global TOKEN
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "kana@test.com", "password": "123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code == 200:
        TOKEN = response.json()["access_token"]
        print(f"✅ Login successful, token: {TOKEN[:20]}...")
        return True
    else:
        print(f"❌ Login failed: {response.status_code} {response.text}")
        return False

def test_pipeline_mapping(payload, test_name):
    """Test pipeline mapping endpoint with given payload"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.put(
        f"{BASE_URL}/api/admin/tenants/{TENANT_ID}/amocrm/pipeline-mapping",
        json=payload,
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    
    print(f"\nStatus: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        result = response.json()
        if result.get("ok"):
            print(f"✅ SUCCESS: Saved {result.get('count')} mappings")
        else:
            print(f"❌ FAILED: {result.get('detail')}")
    else:
        print(f"❌ FAILED: HTTP {response.status_code}")
    
    return response.status_code == 200

def test_options_cors():
    """Test OPTIONS request for CORS preflight"""
    print(f"\n{'='*60}")
    print(f"TEST: CORS OPTIONS Preflight")
    print(f"{'='*60}")
    
    response = requests.options(
        f"{BASE_URL}/api/admin/tenants/{TENANT_ID}/amocrm/pipeline-mapping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type"
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Headers:")
    for key, value in response.headers.items():
        if "access-control" in key.lower():
            print(f"  {key}: {value}")
    
    has_cors = "Access-Control-Allow-Origin" in response.headers
    print(f"\n{'✅' if has_cors else '❌'} CORS headers present: {has_cors}")
    return has_cors

def run_tests():
    """Run all test cases"""
    print("\n" + "="*60)
    print("AmoCRM Pipeline Mapping API - Backward Compatibility Tests")
    print("="*60)
    
    # Login first
    if not login():
        print("\n❌ Cannot run tests without login")
        return
    
    # Test 1: Current format
    test_pipeline_mapping({
        "mappings": [
            {"stage_key": "NEW", "stage_id": "142", "pipeline_id": "7991706", "is_active": True},
            {"stage_key": "IN_WORK", "stage_id": "143", "pipeline_id": "7991706", "is_active": True},
            {"stage_key": "WON", "stage_id": "142", "is_active": True}
        ]
    }, "Format 1: Current (mappings array)")
    
    # Test 2: Legacy dict format
    test_pipeline_mapping({
        "mapping": {
            "NEW": "142",
            "IN_WORK": "143",
            "CALL_1": "49313134",
            "WON": "142"
        },
        "primary_pipeline_id": "7991706"
    }, "Format 2: Legacy dict (mapping object + primary_pipeline_id)")
    
    # Test 3: Legacy array format (most common from frontend)
    test_pipeline_mapping({
        "mapping": [
            {"stage_key": "NEW", "stage_id": "142"},
            {"stage_key": "IN_WORK", "stage_id": "143"},
            {"stage_key": "CALL_1", "stage_id": "49313134"},
            {"stage_key": "WON", "stage_id": "142"}
        ],
        "primary_pipeline_id": "7991706"
    }, "Format 3: Legacy array (mapping array + primary_pipeline_id)")
    
    # Test 4: Empty string normalization
    test_pipeline_mapping({
        "mapping": [
            {"stage_key": "NEW", "stage_id": ""},  # Empty string -> null
            {"stage_key": "IN_WORK", "stage_id": "143"}
        ],
        "primary_pipeline_id": ""  # Empty string -> null
    }, "Format 4: Empty string normalization")
    
    # Test 5: Number to string conversion
    test_pipeline_mapping({
        "mappings": [
            {"stage_key": "NEW", "stage_id": 142, "pipeline_id": 7991706}  # Numbers
        ]
    }, "Format 5: Number to string conversion")
    
    # Test 6: Partial mapping (no stage_id)
    test_pipeline_mapping({
        "mappings": [
            {"stage_key": "CUSTOM_1"},  # No stage_id - should save as null
            {"stage_key": "CUSTOM_2", "stage_id": "123"}
        ]
    }, "Format 6: Partial mapping (missing stage_id)")
    
    # Test 7: CORS OPTIONS
    test_options_cors()
    
    print("\n" + "="*60)
    print("Tests completed!")
    print("="*60)

if __name__ == "__main__":
    run_tests()
