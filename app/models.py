from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Theme lifecycle, in order. The labels are what the UI shows.
THEME_STATUSES = {
    "ideia": "Ideia",
    "pauta": "Na pauta",
    "agendado": "Agendado",
    "gravado": "Gravado",
    "publicado": "Publicado",
    "descartado": "Descartado",
}


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)  # stored lowercase
    email: Mapped[str | None] = mapped_column(String(200), unique=True)  # stored lowercase
    password_hash: Mapped[str | None] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[str] = mapped_column(Text, default="")  # one URL per line
    status: Mapped[str] = mapped_column(String(20), default="ideia", index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[Member] = relationship()
    votes: Mapped[list["ThemeVote"]] = relationship(cascade="all, delete-orphan")
    comments: Mapped[list["ThemeComment"]] = relationship(
        cascade="all, delete-orphan", order_by="ThemeComment.created_at"
    )

    @property
    def link_list(self) -> list[str]:
        return [l.strip() for l in self.links.splitlines() if l.strip()]


class ThemeVote(Base):
    __tablename__ = "theme_votes"

    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)

    member: Mapped[Member] = relationship()


class ThemeComment(Base):
    __tablename__ = "theme_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    member: Mapped[Member] = relationship()


class Poll(Base):
    """An availability round: everyone marks the slots they can record in."""

    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id", ondelete="SET NULL"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    # Daily window in minutes since midnight, e.g. 19:00 → 1140. end may be 1440.
    day_start: Mapped[int] = mapped_column(Integer)
    day_end: Mapped[int] = mapped_column(Integer)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed: Mapped[bool] = mapped_column(Boolean, default=False)

    theme: Mapped[Theme | None] = relationship()
    created_by: Mapped[Member] = relationship()
    availability: Mapped[list["PollSlot"]] = relationship(cascade="all, delete-orphan")
    responses: Mapped[list["PollResponse"]] = relationship(cascade="all, delete-orphan")


class PollSlot(Base):
    """One member is free at one slot start (local time, America/Sao_Paulo)."""

    __tablename__ = "poll_slots"

    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    slot: Mapped[datetime] = mapped_column(DateTime, primary_key=True)


class PollResponse(Base):
    """Marks that a member answered, so "no slots free" differs from "hasn't answered"."""

    __tablename__ = "poll_responses"

    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"), primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # local time
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    theme_id: Mapped[int | None] = mapped_column(ForeignKey("themes.id", ondelete="SET NULL"))
    poll_id: Mapped[int | None] = mapped_column(ForeignKey("polls.id", ondelete="SET NULL"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    theme: Mapped[Theme | None] = relationship()


class LoginSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    member: Mapped[Member] = relationship()


class PasswordReset(Base):
    __tablename__ = "password_resets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)

    member: Mapped[Member] = relationship()
