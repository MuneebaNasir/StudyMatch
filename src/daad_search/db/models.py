from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    course_name: Mapped[str] = mapped_column(Text)
    course_name_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    university: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_type: Mapped[int] = mapped_column(Integer)
    degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[str | None] = mapped_column(Text, nullable=True)
    beginning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tuition_fees_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_tuition_fees: Mapped[bool] = mapped_column(Boolean, default=True)
    application_deadline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str] = mapped_column(Text)
    raw_sections: Mapped[dict] = mapped_column(JSONB, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_programs_subject", "subject"),
        Index("ix_programs_languages", "languages", postgresql_using="gin"),
        Index("ix_programs_has_tuition_fees", "has_tuition_fees"),
        Index("ix_programs_course_type", "course_type"),
        Index("ix_programs_city", "city"),
    )


class Eligibility(Base):
    __tablename__ = "eligibility"

    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id"), primary_key=True, autoincrement=False
    )
    requires_gre: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requires_gmat: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    min_german_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_english_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_grade_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_grade_scale_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(Text)
    structured_eligibility: Mapped[dict] = mapped_column(JSONB, default=dict)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_eligibility_requires_gre", "requires_gre"),
        Index("ix_eligibility_requires_gmat", "requires_gmat"),
        Index("ix_eligibility_min_german_level", "min_german_level"),
        Index("ix_eligibility_min_english_level", "min_english_level"),
    )
