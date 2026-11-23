# Implementation Report

Date of build: 23 Nov 2026. Assignment deadline: Wed 25 Nov 2026, 11:00 PM IST.

## What was built

- **Backend** (Python, FastAPI, SQLite): doctors, slots, appointments; booking and cancelling with transactions; a partial unique
  index so one slot can never be booked twice; SSE event feed; REST API; demo-call API.
- **Voice tools** (exact names): `check_doctor_availability`, `book_appointment`, `cancel_appointment`, with validated schemas,
  timeouts and stable error codes.
- **Safety rules in code:** phone read-back and `phone_confirmed` gate, 10-15 digit validation, country code kept, owner-only cancel
  (same error for unknown or someone else's ID), success only after DB success, masked numbers in logs/events/UI, emergency redirect,
  no medical advice (system prompt + demo agent).
- **Demo mode** (`APP_MODE=mock`, default): scripted agent, real DB operations, "Demo" label everywhere, no keys.
- **Live mode** (`APP_MODE=live`): Pipecat 1.x pipeline - SmallWebRTC, Silero VAD, ElevenLabs STT, Gemini with function calling, ElevenLabs TTS.
  Fails fast with a clear list of what is missing.
- **Frontend** (React 19 + TypeScript + Vite): Overview, Voice-call modal (ringing/connected/ended, timer, mute, end, transcript,
  error and mic-permission handling), Doctors (search, filter, live slots), Appointments (masked phones, filters, highlight on change),
  Live activity. Bonus: real audio-level waveform in live mode, call sounds with on/off, booking/cancel confirmation card, toasts,
  mobile layout.

## What was actually run (in the build environment)

| Check | Result |
|---|---|
| Backend unit + service tests (`pytest`) | **67 passed**, 1 file skipped (`test_api_http.py`, needs fastapi) |
| Phone parsing, booking races, ownership, tool timeout, demo agent, handler error mapping, SSE replay | covered by those 67 tests |
| Real HTTP + SSE against a Starlette stand-in server that uses the **same handlers, error mapping and SSE generator** as the app | Passed |
| HTTP error paths: invalid phone, slot already taken, same-phone clash, wrong phone cancel, unknown ID cancel, double cancel | Passed, all return the documented error body |
| Frontend bundle (esbuild) | Built without errors, 227 KB JS + 18 KB CSS |
| Browser test (headless Chromium via Playwright) against the stand-in server | Passed with **no console or page errors**: overview, demo call, booking with read-back, confirmation card, cancellation in the same call, end call, appointments table + filter + reveal numbers, doctors search/filter/empty state, activity feed, mobile layout (390 px) |
| End-to-end demo booking and cancellation | Passed (in the browser test above) |
| Secret scan, ZIP content check | See bottom of this file |

## What was NOT run (be honest in your submission)

Network access (pip/npm) was blocked in the build environment, so these packages could not be installed:
`fastapi`, `uvicorn`, `pipecat-ai`, `vite`, `@vitejs/plugin-react`, `typescript` types, `@pipecat-ai/*`. Because of that:

1. **The live voice pipeline has never been executed.** `voice/pipeline.py`, `voice/live_routes.py` (WebRTC signalling) and the
   Pipecat browser client in `useCall.ts` were written from the Pipecat 1.x docs. No call to ElevenLabs or Gemini was made.
   Class names in Pipecat change between 1.x releases; the code tolerates some renames but the pin (`pipecat-ai==1.16.0`) is untested.
2. **`app/main.py` and `app/api/routes.py` (FastAPI wiring) were not executed.** Their logic lives in `ApiHandlers`, which is tested.
   `tests/test_api_http.py` is ready to check the wiring: run `pytest` after `pip install -r requirements-dev.txt`.
3. **`npm install`, `vite build` and `tsc` were not run.** The bundle was built with esbuild instead. A partial `tsc` run (without React
   types) showed no real errors, but a full type check needs `npm install`.
4. **The mic-permission-denied path and real microphone audio meter** were not tested in a browser (no microphone in the test environment).
5. Exact package versions in `requirements*.txt` and `package.json` are unverified.
6. **No video was recorded.** `DEMO_SCRIPT.md` is a script only. `PIPELINE_DESCRIPTION.md` is a draft; rewrite it in your own words.

## First things to do on your machine (live-mode checklist)

1. `pip install -r requirements-dev.txt` then `python -m pytest -q` - expect all tests to pass, including `test_api_http.py`.
2. `npm install && npm run typecheck && npm run build` - fix any version or type message.
3. Demo mode: press Try call, book and cancel once.
4. Live mode: add keys, `.\scripts\start-backend.ps1 -Live`. If the import fails, the error names the Pipecat class; edit the
   `_first(...)` lists in `backend/app/voice/pipeline.py` to the new name.
5. Say a phone number aloud, check the read-back, say yes, and check the Appointments page.

## Known limitations

- Demo agent is rule-based; it understands simple phrases only.
- One clinic timezone, no recurring schedules, no doctor-side screens, no authentication on the dashboard (it is a local demo).
- Phone numbers are shown in full only on the "Show full numbers" button in the dashboard.
- SQLite file is local; seeded demo patients use obviously fake numbers.
