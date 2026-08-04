from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    course_name: Mapped[str] = mapped_column(Text)
    course_name_short: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    university: Mapped[str] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    course_type: Mapped[int] = mapped_column(Integer)
    degree: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    beginning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tuition_fees_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_tuition_fees: Mapped[bool] = mapped_column(Boolean, default=True)
    application_deadline_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
