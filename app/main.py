"""
Patient Registration REST API.

Envelope convention: every response body is {"data": ..., "error": ...}
where exactly one of the two is null, per spec.
"""
import logging
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app import crud
from app.schemas import PatientCreate, PatientUpdate, PatientOut
from app.vapi_tools import router as vapi_router
from app.static_dashboard import DASHBOARD_HTML

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("patient_api")

app = FastAPI(title="Patient Registration API", version="1.0.0")
app.include_router(vapi_router)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized / verified.")


def envelope(data=None, error=None):
    return {"data": data, "error": error}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("422 validation error on %s: %s", request.url.path, exc.errors())
    # Convert errors to plain strings to avoid serialization issues with ValueError objects
    error_details = []
    for err in exc.errors():
        error_details.append({
            "loc": err.get("loc", []),
            "msg": str(err.get("msg", "Unknown error")),
            "type": err.get("type", "unknown"),
        })
    return JSONResponse(
        status_code=422,
        content=envelope(error={"message": "Validation failed", "details": error_details}),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(error={"message": exc.detail}),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=envelope(error={"message": "Internal server error"}),
    )


@app.get("/health")
def health():
    logger.info("Health check endpoint called")
    return envelope(data={"status": "ok"})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Bonus: lightweight read-only view of registered patients."""
    return DASHBOARD_HTML


@app.get("/patients")
def list_patients(
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(
        db, last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number
    )
    return envelope(data=[PatientOut.model_validate(p).model_dump() for p in patients])


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=PatientOut.model_validate(patient).model_dump())


@app.post("/patients", status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    patient = crud.create_patient(db, payload)
    logger.info(
        "Created patient %s (%s %s)",
        patient.patient_id, patient.first_name, patient.last_name,
    )
    return envelope(data=PatientOut.model_validate(patient).model_dump())


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = crud.update_patient(db, patient, payload)
    logger.info("Updated patient %s", patient_id)
    return envelope(data=PatientOut.model_validate(patient).model_dump())


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    crud.soft_delete_patient(db, patient)
    logger.info("Soft-deleted patient %s", patient_id)
    return envelope(data={"patient_id": patient_id, "deleted": True})
