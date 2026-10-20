"""Slot grid and ranking for availability polls. All times are naive local
times in America/Sao_Paulo; Brazil has had no DST since 2019."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.models import Member, Poll, Recording

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MAX_DAYS = 21


def parse_hhmm(value: str) -> int:
    """'19:30' → 1170; '24:00' is allowed as an end of day."""
    h, m = value.strip().split(":")
    minutes = int(h) * 60 + int(m)
    if not 0 <= minutes <= 24 * 60:
        raise ValueError(value)
    return minutes


def fmt_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def poll_days(poll: Poll) -> list[date]:
    return [poll.start_date + timedelta(days=i) for i in range((poll.end_date - poll.start_date).days + 1)]


def poll_times(poll: Poll) -> list[int]:
    return list(range(poll.day_start, poll.day_end, poll.slot_minutes))


def slot_at(day: date, minutes: int) -> datetime:
    return datetime.combine(day, time()) + timedelta(minutes=minutes)


def all_slots(poll: Poll) -> list[datetime]:
    return [slot_at(d, m) for d in poll_days(poll) for m in poll_times(poll)]


def fmt_day(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day:02d}/{d.month:02d}"


def fmt_slot(dt: datetime) -> str:
    return f"{fmt_day(dt.date())} às {dt:%H:%M}"


@dataclass
class Window:
    """A run of consecutive slots in one day where the same people are free."""

    start: datetime
    end: datetime
    members: list[Member] = field(default_factory=list)

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    @property
    def label(self) -> str:
        return f"{fmt_day(self.start.date())}, {self.start:%H:%M}–{self.end:%H:%M}"


def free_by_slot(poll: Poll) -> dict[datetime, set[int]]:
    free: dict[datetime, set[int]] = defaultdict(set)
    for s in poll.availability:
        free[s.slot].add(s.member_id)
    return free


def best_windows(
    poll: Poll, members: list[Member], min_minutes: int = 60, limit: int = 5
) -> list[Window]:
    """Longest stretches with the most people free, at least min_minutes long.

    Ranked by people free, then length, then earliest start. A window only
    counts people free for the whole stretch.
    """
    free = free_by_slot(poll)
    by_id = {m.id: m for m in members}
    step = timedelta(minutes=poll.slot_minutes)
    need = max(1, min_minutes // poll.slot_minutes)
    windows: list[Window] = []
    for day in poll_days(poll):
        slots = [slot_at(day, m) for m in poll_times(poll)]
        for i in range(len(slots)):
            people = free.get(slots[i], set())
            j = i
            while people:
                nxt = people & free.get(slots[j + 1], set()) if j + 1 < len(slots) else set()
                # slots i..j are the longest stretch these exact people share
                if nxt != people and j - i + 1 >= need:
                    names = sorted((by_id[p] for p in people if p in by_id), key=lambda m: m.name)
                    windows.append(Window(slots[i], slots[j] + step, names))
                people = nxt
                j += 1
    windows.sort(key=lambda w: (-len(w.members), -w.minutes, w.start))
    # Drop windows nested inside a better one with the same people.
    picked: list[Window] = []
    for w in windows:
        ids = {m.id for m in w.members}
        if any(p.start <= w.start and w.end <= p.end and ids <= {m.id for m in p.members} for p in picked):
            continue
        picked.append(w)
        if len(picked) == limit:
            break
    return picked


def ics_for(recording: Recording, url: str) -> str:
    title = "Gravação Então Ganhei" + (f": {recording.theme.title}" if recording.theme else "")
    end = recording.starts_at + timedelta(minutes=recording.duration_minutes)

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Entao Ganhei//Agenda//PT",
        "BEGIN:VEVENT",
        f"UID:gravacao-{recording.id}@entaoganhei",
        f"DTSTAMP:{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
        f"DTSTART;TZID=America/Sao_Paulo:{recording.starts_at:%Y%m%dT%H%M%S}",
        f"DTEND;TZID=America/Sao_Paulo:{end:%Y%m%dT%H%M%S}",
        f"SUMMARY:{esc(title)}",
        f"DESCRIPTION:{esc((recording.notes + chr(10) + url).strip())}",
        f"URL:{url}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
