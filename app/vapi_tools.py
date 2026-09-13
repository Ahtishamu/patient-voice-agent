"""
Vapi tool-call webhook.

The voice agent (configured in vapi/assistant_config.json) is given three
"tools" it can call mid-conversation: lookup_patient_by_phone, create_patient,
and update_patient. Vapi calls this single webhook URL for all of them and
tells us which tool via the payload.

IMPORTANT / KNOWN LIMITATION: Vapi's exact webhook envelope has changed
across API versions (older "function-call" shape vs. newer "tool-calls" /
toolCallList shape). This handler accepts both shapes defensively so it
keeps working either way, but you should confirm the exact shape against
the Vapi dashboard/docs for the assistant you create, since this could not
be verified against a live account while building this offline. If the
shape differs, the fix is isolated to `_extract_tool_calls` below.
"""
import logging
from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import crud
from app.schemas import PatientCreate, PatientUpdate, PatientOut

logger = logging.getLogger("vapi_tools")
router = APIRouter()


def _extract_tool_calls(body: dict):
    """Normalize different Vapi webhook payload shapes into a common list of
    {"id": str, "name": str, "arguments": dict} dicts."""
    message = body.get("message", body)
    calls = []

    # Newer shape: message.toolCallList / message.toolCalls
    for key in ("toolCallList", "toolCalls"):
        for tc in message.get(key, []) or []:
            fn = tc.get("function", tc)
            calls.append({
                "id": tc.get("id") or tc.get("toolCallId"),
                "name": fn.get("name"),
                "arguments": fn.get("arguments", {}),
            })

    # Older shape: message.functionCall
    fc = message.get("functionCall")
    if fc:
        calls.append({
            "id": message.get("id"),
            "name": fc.get("name"),
            "arguments": fc.get("parameters", fc.get("arguments", {})),
        })

    return calls


def _run_tool(db: Session, name: str, args: dict) -> dict:
    """Executes one tool call against the shared CRUD layer and returns a
    small JSON-serializable result. Never raises -- validation/lookup
    failures come back as a structured {"success": False, "message": ...}
    so the LLM can relay a graceful message to the caller instead of the
    call silently failing."""
    try:
        if name == "lookup_patient_by_phone":
            phone = args.get("phone_number", "")
            patient = crud.get_patient_by_phone(db, _digits(phone))
            if not patient:
                return {"found": False}
            return {
                "found": True,
                "patient_id": patient.patient_id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
            }

        if name == "create_patient":
            payload = PatientCreate(**args)
            # Idempotency guard: if a record with this exact phone number
            # already exists -- whether because the LLM called this tool
            # twice in one conversation, or Vapi retried the webhook after a
            # slow response -- merge into the existing record instead of
            # creating a duplicate. This makes duplicate detection a backend
            # guarantee rather than something that only works if the LLM
            # remembers to call lookup_patient_by_phone first.
            existing = crud.get_patient_by_phone(db, payload.phone_number)
            if existing:
                update_payload = PatientUpdate(**payload.model_dump())
                patient = crud.update_patient(db, existing, update_payload)
                logger.info(
                    "[voice] create_patient called for existing phone %s -- "
                    "merged into %s instead of duplicating",
                    payload.phone_number, patient.patient_id,
                )
                return {
                    "success": True,
                    "patient_id": patient.patient_id,
                    "deduplicated": True,
                    "data": PatientOut.model_validate(patient).model_dump(mode="json"),
                }

            patient = crud.create_patient(db, payload)
            logger.info(
                "[voice] Created patient %s (%s %s) via call",
                patient.patient_id, patient.first_name, patient.last_name,
            )
            return {
                "success": True,
                "patient_id": patient.patient_id,
                "data": PatientOut.model_validate(patient).model_dump(mode="json"),
            }

        if name == "update_patient":
            patient_id = args.pop("patient_id", None)
            patient = crud.get_patient(db, patient_id) if patient_id else None

            if not patient:
                # UUIDs are easy for a voice pipeline to mangle -- one
                # dropped/altered character and a real patient_id no longer
                # matches anything, even though the record genuinely exists.
                # Fall back to looking up by phone number (if the caller's
                # phone is present in this update's fields) before giving up.
                fallback_phone = args.get("phone_number")
                if fallback_phone:
                    patient = crud.get_patient_by_phone(db, _digits(fallback_phone))
                    if patient:
                        logger.info(
                            "[voice] update_patient got unmatched patient_id "
                            "%r -- recovered via phone-number fallback to %s",
                            patient_id, patient.patient_id,
                        )

            if not patient:
                return {
                    "success": False,
                    "message": (
                        "No matching patient found to update. Ask the caller to "
                        "confirm their phone number so we can look them up that way."
                    ),
                }

            payload = PatientUpdate(**args)
            patient = crud.update_patient(db, patient, payload)
            logger.info("[voice] Updated patient %s via call", patient.patient_id)
            return {
                "success": True,
                "patient_id": patient.patient_id,
                "data": PatientOut.model_validate(patient).model_dump(mode="json"),
            }

        return {"success": False, "message": f"Unknown tool '{name}'"}

    except ValidationError as e:
        # Surface the *first* field error in plain language so the agent can
        # re-prompt specifically for that field, per the error-handling
        # requirement (e.g. invalid DOB, malformed phone number).
        first = e.errors()[0]
        field = first.get("loc", ["field"])[-1]
        return {"success": False, "message": f"Invalid {field}: {first.get('msg')}"}
    except Exception as e:  # pragma: no cover - defensive catch-all
        logger.exception("Tool '%s' failed", name)
        return {"success": False, "message": "Internal error saving the record. Please try again."}


def _digits(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())[-10:]


@router.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    body = await request.json()
    calls = _extract_tool_calls(body)

    db: Session = SessionLocal()
    try:
        results = []
        for call in calls:
            result = _run_tool(db, call["name"], dict(call["arguments"] or {}))
            results.append({"toolCallId": call["id"], "result": result})
    finally:
        db.close()

    # Return both response shapes so this works whether Vapi expects
    # "results" (newer) or a single "result" (older, single-call) --
    # extra keys are ignored by clients that don't look for them.
    single = results[0]["result"] if len(results) == 1 else None
    return {"results": results, "result": single}