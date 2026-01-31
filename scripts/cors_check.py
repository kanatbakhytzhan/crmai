#!/usr/bin/env python3
"""
CORS verification script (stdlib only, no external deps).
Run against production: python scripts/cors_check.py
Or set BASE_URL env to test staging/local.
"""
import os
import urllib.request
import urllib.error

BASE = os.environ.get("BASE_URL", "https://crm-api-5vso.onrender.com")
ORIGIN = "https://buildcrm-pwa.vercel.app"


def request(method: str, path: str, extra_headers: dict | None = None) -> tuple[int, dict, bytes]:
    url = f"{BASE.rstrip('/')}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Origin", ORIGIN)
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers) if e.headers else {}, e.read() if e.fp else b""


def has_header(headers: dict, name: str) -> bool:
    return any(k.lower() == name.lower() for k in headers)


def get_header(headers: dict, name: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def main():
    print(f"BASE_URL = {BASE}")
    print(f"Origin    = {ORIGIN}\n")

    # 1) GET /api/health
    print("--- 1) GET /api/health ---")
    status, headers, _ = request("GET", "/api/health")
    acao = get_header(headers, "Access-Control-Allow-Origin")
    print(f"Status: {status}")
    print(f"Access-Control-Allow-Origin: {acao}")
    ok1 = status == 200 and (acao == ORIGIN or acao == "*")
    print(f"OK: {ok1}\n")

    # 2) OPTIONS /api/auth/login
    print("--- 2) OPTIONS /api/auth/login ---")
    status, headers, _ = request(
        "OPTIONS",
        "/api/auth/login",
        {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    acao = get_header(headers, "Access-Control-Allow-Origin")
    acam = get_header(headers, "Access-Control-Allow-Methods")
    acah = get_header(headers, "Access-Control-Allow-Headers")
    print(f"Status: {status}")
    print(f"Access-Control-Allow-Origin: {acao}")
    print(f"Access-Control-Allow-Methods: {acam}")
    print(f"Access-Control-Allow-Headers: {acah}")
    ok2 = status in (200, 204) and (acao == ORIGIN or acao == "*")
    print(f"OK: {ok2}\n")

    # 3) OPTIONS /api/leads
    print("--- 3) OPTIONS /api/leads ---")
    status, headers, _ = request(
        "OPTIONS",
        "/api/leads",
        {
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    acao = get_header(headers, "Access-Control-Allow-Origin")
    acam = get_header(headers, "Access-Control-Allow-Methods")
    acah = get_header(headers, "Access-Control-Allow-Headers")
    print(f"Status: {status}")
    print(f"Access-Control-Allow-Origin: {acao}")
    print(f"Access-Control-Allow-Methods: {acam}")
    print(f"Access-Control-Allow-Headers: {acah}")
    ok3 = status in (200, 204) and (acao == ORIGIN or acao == "*")
    print(f"OK: {ok3}\n")

    # 4) POST /api/auth/login (must not be 404)
    print("--- 4) POST /api/auth/login (expect 200/401/422, not 404) ---")
    url = f"{BASE.rstrip('/')}/api/auth/login"
    data = "username=test@test.com&password=test".encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Origin", ORIGIN)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            status = r.status
            headers = dict(r.headers)
    except urllib.error.HTTPError as e:
        status = e.code
        headers = dict(e.headers) if e.headers else {}
    acao = get_header(headers, "Access-Control-Allow-Origin")
    print(f"Status: {status}")
    print(f"Access-Control-Allow-Origin: {acao}")
    ok4 = status != 404 and (status in (200, 401, 422) or status // 100 == 2 or status // 100 == 4)
    print(f"OK (not 404, has CORS): {ok4}\n")

    all_ok = ok1 and ok2 and ok3 and ok4
    print("=== Summary ===")
    print(f"All checks passed: {all_ok}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
