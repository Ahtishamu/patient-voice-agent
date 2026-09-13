# Voice AI Patient Registration System

A voice agent that answers a real phone number, conversationally collects
standard U.S. patient demographics, confirms them back to the caller,
persists them, and exposes the data through a REST API.

> **Live status:** The backend is deployed on Railway, the Vapi assistant is
> connected to the webhook, and a mock phone call successfully persisted
> patient data.

**Live demo**

- Phone: **+1 (385) 406-9109**
- API: https://web-production-899e5.up.railway.app
- Health check: https://web-production-899e5.up.railway.app/health
- Dashboard: https://web-production-899e5.up.railway.app/dashboard

---

## Architecture

```
 Phone Call            Voice AI Agent                  Backend (this repo)
 (Caller) ───dials───▶  Vapi phone number               FastAPI (Python)
                        + Deepgram STT + GPT-4o          │
                        + Vapi built-in voice              ├── /patients   (REST CRUD)
                             │                             ├── /vapi/webhook (tool calls)
                             │  tool calls (HTTPS)          ├── /dashboard  (bonus UI)
                             └────────────────────────────▶│
                                                            ▼
                                                     SQLite (patients.db)
                                                     -- swappable for Postgres
                                                        via DATABASE_URL
```

**Separation of concerns:**
- **Telephony / STT / TTS** — delegated entirely to Vapi (using a Vapi-provided
  phone number, Deepgram transcription, and Vapi's built-in voice). Vapi owns
  the telephony, speech, turn-taking, and interruption-handling layers.
- **LLM / conversation logic** — a single system prompt (`vapi/system_prompt.md`)
  configured on the Vapi assistant, plus three tool definitions
  (`lookup_patient_by_phone`, `create_patient`, `update_patient`) that the
  LLM calls when it needs to touch the database. The LLM never talks to the
  database directly — only through these tools, which run the same
  validation as the REST API.
- **Data layer** — `app/models.py` (schema) + `app/crud.py` (queries),
  independent of both the API layer and the voice-agent layer. Both
  `app/main.py` (REST) and `app/vapi_tools.py` (voice) call into `crud.py`
  rather than duplicating query logic.
- **API layer** — `app/main.py`, a thin FastAPI layer that validates input
  (via Pydantic, independently of whatever the voice agent already
  validated), maps errors to HTTP status codes, and wraps every response in
  the required `{"data": ..., "error": ...}` envelope.

---

## Tech stack & why

| Layer | Choice | Why |
|---|---|---|
| Telephony + Voice AI | **Vapi** | Provides the phone number, natural-sounding voice interaction, speech processing, turn-taking, interruption handling, and tool-calling infrastructure. |
| LLM | **GPT-4o** (via Vapi) | Strong at natural conversation repair (corrections like "actually, it's spelled D-A-V-I-S") and reliable structured tool-calling for the three functions below. Swappable for Claude or Gemini in the Vapi config with no backend changes. |
| Backend | **Python + FastAPI** | Async, automatic request validation via Pydantic, automatic OpenAPI docs at `/docs`, and a focused CRUD API. |
| Database | **SQLite** (file-based) | Zero setup and zero external dependency for the demo. The ORM can be switched to Postgres through `DATABASE_URL` when durable multi-instance storage is needed. |
| ORM | **SQLAlchemy 2.0** | Enforces column types/constraints at the schema level and keeps the data layer decoupled from both API and voice-agent code. |
| Hosting | **Railway** | Runs the Docker container and provides the public HTTPS URL required by Vapi's webhook. |

---

## Data model

Implemented in `app/models.py`, matching the spec's required/optional field
list exactly, including `patient_id` (UUID), `created_at`/`updated_at`
(auto-managed), and soft-delete via `deleted_at` (nullable — `DELETE`
requests set this rather than removing the row).

Server-side validation (`app/schemas.py`, enforced regardless of what the
voice agent already checked):
- Names: 1–50 chars, letters plus hyphen/apostrophe
- DOB: must parse as a real date and not be in the future
- Sex: one of `Male / Female / Other / Decline to Answer`
- Phone numbers: normalized to 10 digits (accepts common formatting, strips
  a leading US country code `1`)
- State: must be a real 2-letter US state/DC abbreviation
- Zip: 5-digit or ZIP+4
- Email: standard email format, optional

---

## REST API

All responses use the envelope `{"data": ..., "error": null}` (or
`{"data": null, "error": {...}}` on failure), per spec.

| Method | Endpoint | Notes |
|---|---|---|
| `GET` | `/patients` | Filters: `?last_name=`, `?date_of_birth=`, `?phone_number=` |
| `GET` | `/patients/:id` | 404 if not found or soft-deleted |
| `POST` | `/patients` | 201 on success, 422 with field-level errors on invalid input |
| `PUT` | `/patients/:id` | Partial update — only send fields you're changing |
| `DELETE` | `/patients/:id` | Soft-delete (`deleted_at` timestamp, no hard delete) |
| `GET` | `/health` | Liveness check |
| `GET` | `/dashboard` | Bonus: read-only HTML table of registered patients |
| `POST` | `/vapi/webhook` | Tool-call endpoint the voice agent invokes — not meant to be called directly by humans |

Interactive docs are auto-generated by FastAPI at `/docs` once running.

---

## Voice agent design

- **System prompt:** `vapi/system_prompt.md` — documents the full
  conversational flow, confirmation step, correction handling, and
  validation behavior the agent follows. This is the actual prompt used on
  the live assistant.
- **Assistant config:** `vapi/assistant_config.json` — importable Vapi
  assistant definition including the three tool schemas.
- **Tools exposed to the LLM:**
  1. `lookup_patient_by_phone` — called as soon as a phone number is
     collected, to detect returning callers (bonus duplicate-detection
     requirement). If found, the agent offers to update instead of create.
  2. `create_patient` — called once all required fields are collected *and
     confirmed back to the caller*.
  3. `update_patient` — called instead of #2 when the caller is a returning
     caller who opted to update their existing record.
- **Optional fields are opt-in**, not asked by default, per the spec's
  conversational note (insurance, emergency contact, preferred language,
  email).
- **Field-level re-prompting:** if a tool call fails validation (e.g. a
  malformed DOB slipped through), `app/vapi_tools.py` catches the Pydantic
  error and returns a plain-language message naming the specific field, so
  the agent re-asks just that field instead of restarting the whole call.

---

## Edge cases & resilience

| Scenario | Handling |
|---|---|
| Invalid DOB / phone / state spoken | Caught twice: the prompt asks the LLM to sanity-check live, and `app/schemas.py` independently rejects it server-side; the tool-call handler translates the rejection into a specific re-prompt rather than a silent failure. |
| Caller corrects a field mid-call | Prompt explicitly instructs the agent to update only that field and re-confirm just that value, not restart the flow. |
| Caller wants to start over | Prompt instructs the agent to discard in-call state and restart collection on request. |
| Call drops / caller goes silent | `silenceTimeoutSeconds` + `maxDurationSeconds` in `assistant_config.json` end the call gracefully rather than hanging open indefinitely. |
| Database write fails | `_run_tool` in `app/vapi_tools.py` never raises to the caller — it returns a structured `{"success": false, "message": ...}` that the prompt tells the agent to relay as an apology + one retry offer, so the caller never gets silence. |
| Duplicate caller (same phone number) | `lookup_patient_by_phone` tool + prompt step 3 — offers to update instead of creating a duplicate record (bonus requirement). |
| Malformed webhook payload from the voice platform | `_extract_tool_calls` in `app/vapi_tools.py` defensively handles both the older `functionCall` shape and the newer `toolCallList` shape. |
| Unhandled server exceptions | Global exception handler in `app/main.py` returns a clean `500` in the standard envelope instead of leaking a stack trace. |

---

## Setup — running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # defaults are fine for local SQLite

# optional: pre-populate the local SQLite database with two demo patients
python seed.py

uvicorn app.main:app --reload
```

- API: http://localhost:8000 (interactive docs at `/docs`)
- Dashboard: http://localhost:8000/dashboard

Run tests:
```bash
pytest -v
```

Try it:
```bash
curl -X POST http://localhost:8000/patients \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Jane","last_name":"Doe","date_of_birth":"1990-03-03","sex":"Female","phone_number":"5551234567","address_line_1":"123 Main St","city":"Austin","state":"TX","zip_code":"78701"}'

curl http://localhost:8000/patients
```

---

## Deployment and live configuration

The backend is hosted on Railway at:

```text
https://web-production-899e5.up.railway.app
```

The Vapi assistant is connected to:

```text
https://web-production-899e5.up.railway.app/vapi/webhook
```

The live Vapi phone number is **+1 (385) 406-9109**. The assistant uses
Vapi's built-in `Elliot` voice, GPT-4o, and Deepgram `nova-2` transcription;
ElevenLabs is not required.

The live flow has been tested with a phone call: the assistant collected
patient details, called the webhook, and the resulting patient record was
saved. To verify records through the API:

```bash
curl https://web-production-899e5.up.railway.app/patients
```

`seed.py` initializes the local SQLite database only. To add demo records to
the deployed service, use the `POST /patients` endpoint or run the seed data
through an authenticated deployment shell.

For future assistant deployments, set `VAPI_API_KEY` and
`DEPLOYED_BASE_URL` as environment variables and run
`scripts/create_vapi_assistant.py`. Never commit the Vapi API key to the
repository.

---

## Known limitations / trade-offs

- **SQLite storage on Railway** — appropriate for this single-instance demo,
  but Railway container storage is not guaranteed to survive a replacement
  container or a fresh deployment. Use Railway Postgres or a persistent volume
  when durable production storage is required.
- **No auth on the REST API** — acceptable for a take-home per the FAQ ("do
  not store real patient data"); a real system would put this behind
  API-key or OAuth auth and probably a VPN for the `/vapi/webhook` route.
- **No real transcript storage** — call transcripts aren't persisted
  (bonus item), though conversation-relevant events (created/updated
  patient records) are logged to stdout per the observability requirement.
- **Single-language backend validation** — the voice agent can converse in
  Spanish (bonus, via prompt instruction), but field values are stored in
  English/Latin-alphabet form regardless of spoken language.
- **Zip code accuracy** — if a caller says they don't know their zip code,
  the agent may offer a plausible one for their stated city as a starting
  point and ask the caller to confirm/correct it, rather than leaving the
  required field empty. In testing this produced a confirmed-but-unverified
  value (the caller just agreed to the agent's guess). A stricter version
  should instead ask the caller to check their phone/mail for the exact
  zip, or accept a lower-confidence placeholder that's flagged for
  follow-up rather than treated as confirmed data.
- **Non-idempotent voice-triggered writes** — a slow backend response or an
  LLM double-invocation of `create_patient` could historically produce two
  records from one call. `app/vapi_tools.py` now guards against this by
  treating `create_patient` as an upsert keyed on phone number (a second
  call with the same phone number updates the existing record instead of
  duplicating it), but this is a backend-side safety net, not a guarantee
  the LLM only ever intends to call it once.
- **Webhook payload shape assumption** — `_extract_tool_calls` in
  `app/vapi_tools.py` was written defensively against two known historical
  Vapi payload shapes, reasoned through without a live account to verify
  against at build time. Confirmed working against a real Vapi call during
  testing.

## Next steps (if given more time)

- Add API-key auth to `/vapi/webhook` and the REST API.
- Add appointment scheduling as a fourth tool (bonus item), backed by a
  simple `appointments` table.
- Persist a call transcript/summary linked to `patient_id` for auditability.
- Add rate limiting and structured (JSON) logs for production observability.
- Add a CI workflow that runs `pytest` on every push.