#!/bin/bash
# Starts a fake Groq+Gemini server and the API on a temp SQLite database (AUTH_DISABLED, local storage), runs the
# end-to-end checks, restarts to test persistence, then kills the fake AI server to test graceful degradation.
# Proves plumbing only; real-provider checks are in docs/LIVE_TESTS.md.
cd "$(dirname "$0")/.."
export RG_DATA_DIR=$(mktemp -d) RG_SIM_THRESHOLD=${RG_SIM_THRESHOLD:-0.35}
export AUTH_DISABLED=true STORAGE_BACKEND=local ENV=dev
export GROQ_API_KEY=test GEMINI_API_KEY=test AI_TIMEOUT=5 AI_MAX_RETRIES=0
export GROQ_BASE_URL=http://127.0.0.1:8765/openai/v1/chat/completions GEMINI_BASE_URL=http://127.0.0.1:8765/v1beta
export EMBED_PROVIDER=gemini
export GROQ_RPM=0 GROQ_RPD=0 GROQ_TPM=0 GROQ_TPD=0 GEMINI_RPM=0 GEMINI_RPD=0 GEMINI_TPM=0 GEMINI_TPD=0
python3 -W ignore -m tests.fake_ai_server 8765 >/tmp/fake.log 2>&1 & FAKE=$!
start_api() { python3 -W ignore -m uvicorn app.main:app --port 8000 >/tmp/api.log 2>&1 & API=$!; sleep 3; }
start_api
python3 tests/e2e.py main; R1=$?
kill $API; wait $API 2>/dev/null; start_api            # restart: data must survive
python3 tests/e2e.py persist; R2=$?
kill $FAKE; wait $FAKE 2>/dev/null; sleep 1            # AI providers go away
python3 tests/e2e.py outage; R3=$?
kill $API; wait $API 2>/dev/null
echo "exit codes: main=$R1 persist=$R2 outage=$R3"
