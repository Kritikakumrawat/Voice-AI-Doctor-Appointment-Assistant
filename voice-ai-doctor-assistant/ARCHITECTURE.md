# Architecture

```
                         ┌────────────────────────── browser ──────────────────────────┐
                         │  React dashboard (Vite)                                     │
                         │  Overview · Voice call · Doctors · Appointments · Activity  │
                         └──────┬───────────────┬──────────────────────┬───────────────┘
                     REST /api  │   SSE /api/events   │   WebRTC (live only): mic ⇄ audio
                                ▼               ▼                      ▼
┌───────────────────────────────────── FastAPI backend ─────────────────────────────────────┐
│  routes.py → ApiHandlers      EventBus (pub/sub)       /api/offer (SmallWebRTC signalling)│
│        │                           ▲                              │                       │
│        ▼                           │ events                       ▼                       │
│  ClinicService ◄──── ToolExecutor ─┴──── Pipecat pipeline (live) / MockAgent (demo)       │
│        │                                                                                  │
│        ▼                                                                                  │
│  SQLite: doctors · slots · appointments  (partial unique index = no double booking)       │
└───────────────────────────────────────────────────────────────────────────────────────────┘

Live pipeline:
 mic → WebRTC → Silero VAD → ElevenLabs STT → user aggregator → Gemini (3 tools) → ElevenLabs TTS → WebRTC → speaker
```

## Key decisions

**One set of business rules.** `ClinicService` is the only code that changes the database. The REST API,
the demo agent and the Gemini tools all call it. A rule fixed once is fixed everywhere.

**Framework-independent core.** `ClinicService`, `ToolExecutor`, `MockAgent` and `ApiHandlers` do not import FastAPI or
Pipecat. FastAPI routes are thin wrappers. Pipecat is imported only inside the live pipeline, so demo mode needs no
voice packages and no keys.

**Safe by construction, not by prompt.**
- `book_appointment` and `cancel_appointment` take `phone_confirmed`. With `false`, the tool returns the read-back text and
  changes nothing. The LLM cannot book without the caller saying yes.
- Booking runs in `BEGIN IMMEDIATE`; a partial unique index on active appointments per slot stops double booking even
  under a race.
- Cancel checks the phone owner. Unknown ID and wrong owner return the same error.
- Tool results carry a `status`; the prompt tells the model to claim success only on `booked` / `cancelled`.

**Real-time dashboard.** Every change publishes an event on the `EventBus`. One SSE connection per browser tab streams
events; `Last-Event-ID` replays missed ones after a reconnect, and the UI re-fetches data after reconnecting.

**Mock mode is honest.** The UI shows "Demo mode · simulated agent". The transport is typed text (and optional browser speech
recognition), the call is never described as a live call, and the meter does not pretend to hear audio.

**Failure handling.** Tool timeout (8 s default) returns a spoken-friendly error. Pipeline errors are published as events and shown
in the call screen. The frontend gives up on a stuck WebRTC connection after 25 s. Mic permission denial has its own message.

## Data model

- `doctors(id, name, speciality, fee, ...)`
- `slots(id, doctor_id, date, start_time, end_time)`
- `appointments(id, slot_id, doctor_id, phone, patient_name, status, created_at, cancelled_at)`
  with `UNIQUE (slot_id) WHERE status = 'booked'`

Phones are stored normalised (digits, optional leading `+`). Matching is exact; if one side has no `+`, the last 10 digits are compared.

## Backend modules

| Module | Role |
|---|---|
| `config.py` | Reads env, validates, fails fast in live mode |
| `db/` | Schema, transactions, idempotent seed |
| `services/phone.py` | Spoken digits → number, validation, read-back, masking |
| `services/clinic.py` | Availability, booking, cancelling, overview |
| `services/events.py` | EventBus + SSE formatting |
| `services/calls.py` | Call sessions and transcripts |
| `voice/tools.py` | The 3 tool schemas, validation, timeout, error mapping |
| `voice/prompts.py` | System prompt and greeting |
| `voice/mock_agent.py` | Rule-based demo agent |
| `voice/pipeline.py`, `live_routes.py` | Pipecat pipeline and WebRTC signalling (live) |

## Frontend modules

`useEventBus` (one SSE), `useDashboard` (data + highlight), `useCall` (call state machine: idle → connecting → connected → ended/error),
`PhoneCall` (modal), `Waveform` (canvas, driven by a real `AnalyserNode` in live mode), `sound.ts` (WebAudio tones, user toggle).
