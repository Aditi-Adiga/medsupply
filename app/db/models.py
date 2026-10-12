from datetime import date

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

# Register operational records with the same metadata and database.
from app.db import operations  # noqa: F401


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    location: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    patient_capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    hospital_id: Mapped[str] = mapped_column(
        ForeignKey("hospitals.id"),
        nullable=False,
    )

    medicine_id: Mapped[str] = mapped_column(
        ForeignKey("medicines.id"),
        nullable=False,
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class Consumption(Base):
    __tablename__ = "consumption"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    hospital_id: Mapped[str] = mapped_column(
        ForeignKey("hospitals.id"),
        nullable=False,
    )

    medicine_id: Mapped[str] = mapped_column(
        ForeignKey("medicines.id"),
        nullable=False,
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    units_consumed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class HospitalActivity(Base):
    __tablename__ = "hospital_activity"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    hospital_id: Mapped[str] = mapped_column(
        ForeignKey("hospitals.id"),
        nullable=False,
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    patient_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    emergency_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    medicine_id: Mapped[str] = mapped_column(
        ForeignKey("medicines.id"),
        nullable=False,
    )

    lead_time_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
