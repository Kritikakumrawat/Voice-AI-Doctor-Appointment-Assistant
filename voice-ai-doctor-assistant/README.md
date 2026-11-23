# Voice AI Doctor Appointment Assistant

A voice assistant for a clinic front desk. A caller speaks, the assistant checks real doctor slots,
books or cancels an appointment in a SQLite database, and a React dashboard updates live.

- **Live mode:** Pipecat (SmallWebRTC + Silero VAD) → ElevenLabs STT → **Gemini** (function calling) → ElevenLabs TTS.
- **Demo mode (default):** no API keys. A simple scripted agent replaces the LLM and speech services.
  Bookings, cancellations and availability are still **real database operations**. The UI always says "Demo".

> **Which LLM is used?** Google **Gemini** (default model `gemini-2.5-flash`, set with `LLM_MODEL`),
> called through Pipecat's Google service with `GOOGLE_API_KEY`. Demo mode uses no LLM at all.

## What you can do

| Area | What it does |
|---|---|
| Overview | Mode badge, stack in use, open slots, booked/cancelled counts, upcoming appointments, recent activity |
| Voice call | Phone-style modal: ringing → connected → ended, timer, mute, end call, live transcript, mic-permission and error handling, sounds (can be turned off) |
| Doctors | 7 doctors, search + speciality filter, live open slots for the next days |
| Appointments | Masked phone numbers, filter by status, search, rows highlight when a call changes them |
| Live activity | Real-time feed of calls, tool calls, bookings, cancellations and errors (Server-Sent Events) |

Voice tools (exact names): `check_doctor_availability`, `book_appointment`, `cancel_appointment`.

## Quick start - Windows PowerShell (demo mode, no keys)

Needs Python 3.10+ and Node 20+.

```powershell
# Terminal 1 - backend
cd path\to\voice-ai-doctor-assistant
.\scripts\start-backend.ps1
```
```powershell
# Terminal 2 - frontend
cd path\to\voice-ai-doctor-assistant
.\scripts\start-frontend.ps1
```
Open http://localhost:5173 and press **Try call**.

If PowerShell blocks scripts: `Set-ExecutionPolicy -Scope Process Bypass` then run the script again.

Manual commands (same thing, no script):
```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py                      # http://127.0.0.1:8000  (API docs at /docs)

# new terminal
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

macOS / Linux: `./scripts/start-backend.sh` and `./scripts/start-frontend.sh`.

**One port instead of two:** `cd frontend; npm install; npm run build`, then run the backend.
It serves `frontend/dist` at http://127.0.0.1:8000.

## Live mode (real voice)

1. Get an ElevenLabs API key and a Google AI Studio (Gemini) API key.
2. `cd backend; copy .env.example .env` and set:
   ```
   APP_MODE=live
   ELEVENLABS_API_KEY=...
   GOOGLE_API_KEY=...
   ```
3. Install and start:
   ```powershell
   .\scripts\start-backend.ps1 -Live
   ```
   (or `pip install -r requirements-live.txt` then `python run.py`)
4. Start the frontend, open http://localhost:5173, press **Try call**, allow the microphone, and talk.

If a key or the `pipecat-ai` package is missing, the backend refuses to start and prints exactly what is missing.

| Variable | Default | Purpose |
|---|---|---|
| `APP_MODE` | `mock` | `mock` or `live` |
| `ELEVENLABS_API_KEY` | - | Required in live mode (STT + TTS) |
| `GOOGLE_API_KEY` | - | Required in live mode (Gemini) |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | TTS voice |
| `ELEVENLABS_TTS_MODEL` / `ELEVENLABS_STT_MODEL` | `eleven_flash_v2_5` / `scribe_v2_realtime` | Speech models |
| `LLM_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `TOOL_TIMEOUT_SECS` | `8` | Per-tool timeout (Pipecat's own limit is about 10 s) |
| `DATABASE_PATH` | `backend/data/clinic.db` | SQLite file |
| `CORS_ORIGINS` | localhost:5173/8000 | Allowed browser origins |

Never commit `backend/.env`. Only `.env.example` files are in the repo.

## How the assistant stays safe

- The caller is identified **only** by the phone number they say. No login, OTP or caller ID.
- Phone numbers must have 10-15 digits; a leading country code is kept.
- Before booking or cancelling, the agent reads the number back digit by digit and waits for a clear "yes".
  The tool itself refuses to act until `phone_confirmed=true`, so the model cannot skip this.
- A caller can only cancel appointments that belong to the exact number they gave.
  An unknown ID and someone else's ID give the **same** answer, so nothing leaks.
- The agent only says "booked" or "cancelled" after the database call succeeded.
- No medical advice or triage. Emergencies are sent to emergency services (112 / 108 / 911).
- Logs, events and the dashboard show masked numbers only.

## Tests

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
cd ..\frontend
npm install
npm run typecheck
npm run build
```
Test files: phone parsing, booking rules and races, tool calls, the demo agent, API handlers, and
`test_api_http.py` (real HTTP routes through FastAPI TestClient). See `IMPLEMENTATION_REPORT.md` for what was run and what was not.

## REST API (served under `/api`)

`GET /health`, `/config`, `/overview`, `/events` (SSE) · `GET /doctors`, `/doctors/{id}/availability` ·
`GET /appointments`, `/appointments/lookup?phone=` · `POST /appointments` · `POST /appointments/{id}/cancel` ·
`POST /calls`, `/calls/{id}/say`, `/calls/{id}/end` (demo mode) · `POST|PATCH /offer` (WebRTC signalling, live mode).

Errors always look like `{"error": {"code": "slot_unavailable", "message": "..."}}`.
Codes: `invalid_phone`, `invalid_input`, `validation_error`, `doctor_not_found`, `slot_not_found`,
`slot_unavailable`, `slot_in_past`, `patient_conflict`, `appointment_not_found`, `already_cancelled`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend says `APP_MODE=live but the following are missing` | Fill `backend/.env`, install `requirements-live.txt` |
| Dashboard shows "Live feed reconnecting" | Backend not running on port 8000 |
| Mic blocked | Allow the microphone for localhost in the browser address bar, press Try call again |
| Live call stays on "Connecting" | Check the backend console; the UI gives up after 25 s and shows an error |
| Port already used | Set `PORT=8001` and `VITE_API_BASE=http://127.0.0.1:8001` in `frontend/.env` |
| Want fresh data | Stop the backend and delete `backend/data/clinic.db` |

## Repository layout

```
backend/app/{api,db,services,voice}   FastAPI, SQLite, business rules, voice agent + Pipecat pipeline
backend/tests                         pytest suite
frontend/src                          React + Vite dashboard
scripts/                              one-command start scripts
ARCHITECTURE.md  IMPLEMENTATION_REPORT.md  PIPELINE_DESCRIPTION.md  DEMO_SCRIPT.md
```
