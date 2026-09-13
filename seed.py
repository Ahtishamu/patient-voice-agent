"""Seed the database with 2 demo patients. Run: python seed.py"""
from datetime import date
from app.database import SessionLocal, init_db
from app import crud
from app.schemas import PatientCreate

SEED_PATIENTS = [
    PatientCreate(
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1990, 3, 3),
        sex="Female",
        phone_number="5551234567",
        email="jane.doe@example.com",
        address_line_1="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        preferred_language="English",
    ),
    PatientCreate(
        first_name="Miguel",
        last_name="Alvarez",
        date_of_birth=date(1985, 11, 21),
        sex="Male",
        phone_number="5559876543",
        address_line_1="456 Oak Ave",
        address_line_2="Apt 2B",
        city="Phoenix",
        state="AZ",
        zip_code="85001",
        insurance_provider="Blue Cross Blue Shield",
        insurance_member_id="BCBS998877",
        preferred_language="Spanish",
    ),
]


def main():
    init_db()
    db = SessionLocal()
    try:
        for p in SEED_PATIENTS:
            existing = crud.get_patient_by_phone(db, p.phone_number)
            if existing:
                print(f"Skipping {p.first_name} {p.last_name} (already exists)")
                continue
            created = crud.create_patient(db, p)
            print(f"Seeded {created.first_name} {created.last_name} -> {created.patient_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
