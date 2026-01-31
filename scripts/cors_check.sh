#!/bin/sh
# CORS verification (curl). Usage: ./scripts/cors_check.sh
# Or: BASE_URL=https://crm-api-5vso.onrender.com ./scripts/cors_check.sh
BASE="${BASE_URL:-https://crm-api-5vso.onrender.com}"
ORIGIN="https://buildcrm-pwa.vercel.app"

echo "--- 1) GET /api/health ---"
curl -i -s "${BASE}/api/health" -H "Origin: ${ORIGIN}" | head -20

echo "\n--- 2) OPTIONS /api/auth/login ---"
curl -i -s -X OPTIONS "${BASE}/api/auth/login" \
  -H "Origin: ${ORIGIN}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" | head -20

echo "\n--- 3) OPTIONS /api/leads ---"
curl -i -s -X OPTIONS "${BASE}/api/leads" \
  -H "Origin: ${ORIGIN}" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" | head -20

echo "\n--- 4) POST /api/auth/login (expect 200/401, not 404) ---"
curl -i -s -X POST "${BASE}/api/auth/login" \
  -H "Origin: ${ORIGIN}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=x&password=y" | head -25
