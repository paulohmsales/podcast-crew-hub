from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Episode lifecycle, in order: the board's columns. The labels are what the UI shows.
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
    email: Mapped[str | None] = mapped_column(String(200), unique=True)  # stored lowercase; the login
    # None until the first login: whatever password is typed then becomes theirs.
    password_hash: Mapped[str | None] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    tutorial_seen_at: Mapped[datetime | None] = mapped_column(DateTime)  # None: show the tour on next visit
    photo: Mapped[str | None] = mapped_column(String(80))  # file name under DATA_DIR/fotos
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Segment(Base):
    """A recurring segment ("quadro") an episode can include."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


theme_segments = Table(
    "theme_segments",
    Base.metadata,
    Column("theme_id", ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True),
    Column("segment_id", ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True),
)

theme_participants = Table(
    "theme_participants",
    Base.metadata,
    Column("theme_id", ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", ForeignKey("members.id", ondelete="CASCADE"), primary_key=True),
)


class Game(Base):
    """A board game from Ludopedia, cached locally (id is Ludopedia's id_jogo)."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200))
    original_name: Mapped[str] = mapped_column(String(200), default="")
    thumb: Mapped[str] = mapped_column(String(500), default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    year: Mapped[int | None] = mapped_column(Integer)
    players_min: Mapped[int | None] = mapped_column(Integer)
    players_max: Mapped[int | None] = mapped_column(Integer)
    minutes: Mapped[int | None] = mapped_column(Integer)
    min_age: Mapped[int | None] = mapped_column(Integer)
    mechanics: Mapped[str] = mapped_column(Text, default="")  # names joined by "|"
    categories: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)  # full details loaded at

    @property
    def mechanic_list(self) -> list[str]:
        return [m for m in self.mechanics.split("|") if m]

    @property
    def category_list(self) -> list[str]:
        return [c for c in self.categories.split("|") if c]

    @property
    def players(self) -> str:
        lo, hi = self.players_min, self.players_max
        if not lo and not hi:
            return ""
        return f"{lo}" if lo == hi or not hi else f"{lo or 1}–{hi}"


theme_games = Table(
    "theme_games",
    Base.metadata,
    Column("theme_id", ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True),
    Column("game_id", ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
)


class Theme(Base):
    """An episode, from first idea to published (shown as "Episódio" in the UI)."""

    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[str] = mapped_column(Text, default="")  # one URL per line
    status: Mapped[str] = mapped_column(String(20), default="ideia", index=True)
    number: Mapped[int | None] = mapped_column(Integer)  # episode number once it has one
    episode_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    published_on: Mapped[date | None] = mapped_column(Date)
    feed_guid: Mapped[str | None] = mapped_column(String(300), unique=True)  # set when imported from RSS
    # The episode script ("roteiro"), edited together; version bumps on every save.
    script: Mapped[str] = mapped_column(Text, default="", server_default="")
    script_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    script_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    script_updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[Member] = relationship(foreign_keys=[created_by_id])
    script_updated_by: Mapped[Member | None] = relationship(foreign_keys=[script_updated_by_id])
    segments: Mapped[list[Segment]] = relationship(secondary=theme_segments, order_by=Segment.position)
    participants: Mapped[list[Member]] = relationship(secondary=theme_participants, order_by=Member.name)
    games: Mapped[list[Game]] = relationship(secondary=theme_games, order_by=Game.name, backref="episodes")
    votes: Mapped[list["ThemeVote"]] = relationship(cascade="all, delete-orphan")
    comments: Mapped[list["ThemeComment"]] = relationship(
        cascade="all, delete-orphan", order_by="ThemeComment.created_at"
    )

    @property
    def link_list(self) -> list[str]:
        return [l.strip() for l in self.links.splitlines() if l.strip()]


class ThemeEvent(Base):
    """One line of an episode's history ("Histórico")."""

    __tablename__ = "theme_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)  # already worded for display, e.g. "moveu para Gravado"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    member: Mapped[Member | None] = relationship()


class ScriptRevision(Base):
    """A saved copy of the script, to see and restore older versions."""

    __tablename__ = "script_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    member: Mapped[Member | None] = relationship()


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

