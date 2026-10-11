#!/usr/bin/env bash
# =============================================================================
# scripts/demo.sh
# 2-to-3 minute video walkthrough of MoveInSync Safety & Compliance Engine (SPEC 19)
# =============================================================================

set -e

BASE="${BASE:-http://127.0.0.1:8000}"

echo "======================================================================"
echo " MoveInSync Trip Safety & Compliance Engine: Demo Walkthrough"
echo " Target API: $BASE"
echo "======================================================================"

# Helper function to login and extract JWT access token
login() {
    curl -s -X POST "$BASE/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$1\",\"password\":\"$2\"}" \
        | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

echo ""
echo "[*] Authenticating demo actors..."
ADMIN=$(login admin 'Admin@123')
DRIVER=$(login driver1 'Driver@123')
PRIYA=$(login priya 'Emp@123')
echo "    -> Logged in as Admin, Driver1, and Priya (Employee)."

echo ""
echo "----------------------------------------------------------------------"
echo " 1. Night Safety Violation (Trip 1): expect 1 x NIGHT_SAFETY (HIGH)"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/1/audit" \
    -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 2. Re-Audit Idempotency (Trip 1): new=0, duplicates>0, total unchanged"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/1/audit" \
    -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 3. Route Deviation (Trip 2): 800m+ for 4 min, blip ignored"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/2/audit" \
    -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 4. Over-Speed Detection (Trip 3): MEDIUM + CRITICAL, spike ignored"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/3/audit" \
    -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 5. Wrong OTP on Trip 4 -> 409, Drop FROZEN, OTP_MISMATCH raised"
echo "----------------------------------------------------------------------"
DROP_STOP_ID=$(curl -s "$BASE/trips/4" -H "Authorization: Bearer $ADMIN" | python -c "import sys, json; stops=[s for s in json.load(sys.stdin).get('stops', []) if s.get('type')=='DROP']; print(stops[0]['id'] if stops else 15)")
echo "Submitting wrong OTP for Trip 4, Stop $DROP_STOP_ID:"
curl -s -X POST "$BASE/trips/4/stops/$DROP_STOP_ID/otp" \
    -H "Authorization: Bearer $DRIVER" \
    -H 'Content-Type: application/json' \
    -d '{"otp":"000000"}' | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 6. SOS from Priya on Trip 1 -> Immediate CRITICAL Alert"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/1/sos" \
    -H "Authorization: Bearer $PRIYA" \
    -H 'Content-Type: application/json' \
    -d '{"lat":28.5355,"lng":77.34}' | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 7. Escalation + Critical Violations, Prometheus Metrics & Audit Chain"
echo "----------------------------------------------------------------------"
echo "[Violations: CRITICAL]"
curl -s "$BASE/violations?severity=CRITICAL" -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "[Prometheus Metrics]"
curl -s "$BASE/metrics" | grep -E 'violations_total|sos_total|otp_attempts_total|audit_duplicates' || true

echo ""
echo "[Audit Chain Verification]"
curl -s "$BASE/audit/verify" -H "Authorization: Bearer $ADMIN" | python -m json.tool

echo ""
echo "----------------------------------------------------------------------"
echo " 8. RBAC Proof: Employee tries to trigger audit -> 403 Forbidden"
echo "----------------------------------------------------------------------"
curl -s -X POST "$BASE/trips/1/audit" \
    -H "Authorization: Bearer $PRIYA" | python -m json.tool

echo ""
echo "======================================================================"
echo " Demo script completed successfully!"
echo "======================================================================"
