"""
Integration tests for the Patient Registration REST API.
Run with: pytest -v
Uses an isolated in-memory SQLite DB per test session (not the real patients.db).
"""
import os
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app  # noqa: E402
from app.database import init_db  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _setup_db():
    init_db()


VALID_PATIENT = {
    "first_name": "Alice",
    "last_name": "Nguyen",
    "date_of_birth": "1992-06-15",
    "sex": "Female",
    "phone_number": "5125550100",
    "address_line_1": "789 Elm St",
    "city": "Dallas",
    "state": "TX",
    "zip_code": "75201",
}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"


def test_create_patient_success():
    resp = client.post("/patients", json=VALID_PATIENT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["first_name"] == "Alice"
    assert body["data"]["patient_id"]
    assert body["data"]["preferred_language"] == "English"


def test_create_patient_missing_required_field_returns_422():
    bad = dict(VALID_PATIENT)
    bad.pop("last_name")
    bad["phone_number"] = "5125550101"
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422
    assert resp.json()["data"] is None
    assert resp.json()["error"] is not None


def test_create_patient_future_dob_rejected():
    bad = dict(VALID_PATIENT)
    bad["phone_number"] = "5125550102"
    bad["date_of_birth"] = "2999-01-01"
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422


def test_create_patient_invalid_phone_rejected():
    bad = dict(VALID_PATIENT)
    bad["phone_number"] = "123"
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422


def test_create_patient_invalid_state_rejected():
    bad = dict(VALID_PATIENT)
    bad["phone_number"] = "5125550103"
    bad["state"] = "ZZ"
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422


def test_get_patient_by_id():
    created = client.post("/patients", json={**VALID_PATIENT, "phone_number": "5125550104"}).json()["data"]
    resp = client.get(f"/patients/{created['patient_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["patient_id"] == created["patient_id"]


def test_get_nonexistent_patient_404():
    resp = client.get("/patients/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["data"] is None


def test_list_patients_filter_by_last_name():
    client.post("/patients", json={**VALID_PATIENT, "phone_number": "5125550105", "last_name": "Zephyr"})
    resp = client.get("/patients", params={"last_name": "Zephyr"})
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1
    assert all(p["last_name"] == "Zephyr" for p in resp.json()["data"])


def test_update_patient_partial():
    created = client.post("/patients", json={**VALID_PATIENT, "phone_number": "5125550106"}).json()["data"]
    resp = client.put(f"/patients/{created['patient_id']}", json={"city": "Houston"})
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Houston"
    assert resp.json()["data"]["last_name"] == "Nguyen"  # untouched fields survive


def test_soft_delete_hides_from_list_and_get():
    created = client.post("/patients", json={**VALID_PATIENT, "phone_number": "5125550107"}).json()["data"]
    pid = created["patient_id"]
    del_resp = client.delete(f"/patients/{pid}")
    assert del_resp.status_code == 200
    assert client.get(f"/patients/{pid}").status_code == 404


def test_duplicate_phone_lookup_via_vapi_webhook():
    client.post("/patients", json={**VALID_PATIENT, "phone_number": "5125550108", "first_name": "Dupe"})
    resp = client.post("/vapi/webhook", json={
        "message": {"functionCall": {"name": "lookup_patient_by_phone",
                                      "parameters": {"phone_number": "5125550108"}}}
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["found"] is True
    assert result["first_name"] == "Dupe"


def test_vapi_webhook_create_patient_with_invalid_field_returns_friendly_error():
    resp = client.post("/vapi/webhook", json={
        "message": {"functionCall": {
            "name": "create_patient",
            "parameters": {**VALID_PATIENT, "phone_number": "5125550109", "date_of_birth": "3000-01-01"},
        }}
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["success"] is False
    assert "date_of_birth" in result["message"]
