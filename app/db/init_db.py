import os
import sys

# Ensure root directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
from sqlalchemy.orm import Session

from app.db.database import Base, engine, SessionLocal
from app.db.models import Hospital, Medicine


DATASET_PATH = "data/medical_supply_20_medicines.csv"


def init_and_seed_db():
    """Initializes tables and seeds initial data from medical_supply_20_medicines.csv."""
    Base.metadata.create_all(bind=engine)

    if not os.path.exists(DATASET_PATH):
        print("Dataset CSV not found, skipping seeding.")
        return

    db: Session = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Hospital).first() is not None:
            print("Database already initialized and seeded.")
            return

        df = pd.read_csv(DATASET_PATH)

        # Seed Unique Hospitals
        hospitals_seen = set()
        for h_id in df["hospital_id"].unique():
            h_str = str(h_id)
            if h_str not in hospitals_seen:
                hospitals_seen.add(h_str)
                h = Hospital(
                    id=h_str,
                    name=f"Metro General Hospital ({h_str})",
                    location="Metropolitan Health District",
                    patient_capacity=500,
                )
                db.add(h)

        # Seed Unique Medicines
        meds_seen = set()
        for _, row in df[["medicine_id", "medicine_name"]].drop_duplicates().iterrows():
            m_id = str(row["medicine_id"])
            if m_id not in meds_seen:
                meds_seen.add(m_id)
                m = Medicine(
                    id=m_id,
                    name=str(row["medicine_name"]),
                    category="Critical Pharmaceutical",
                )
                db.add(m)

        db.commit()
        print("Hospitals and medicines successfully seeded!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_and_seed_db()
