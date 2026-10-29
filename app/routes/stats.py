"""Números: the podcast's numbers — releases over time, quadros, who's on air, games."""

from collections import Counter
from datetime import date
from statistics import median

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import THEME_STATUSES, Member, Segment, Theme
from app.schedule import MONTHS
from app.web import current_member, render

router = APIRouter(prefix="/numeros")

PIPELINE = ["ideia", "pauta", "agendado", "gravado", "publicado"]


def _months(first: date, last: date) -> list[tuple[int, int]]:
    y, m = first.year, first.month
    out = []
    while (y, m) <= (last.year, last.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@router.get("")
def stats(
    request: Request,
    ano: int | None = None,
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    all_published = db.scalars(
        select(Theme).where(Theme.status == "publicado", Theme.published_on.is_not(None)).order_by(Theme.published_on)
    ).all()
    years = sorted({t.published_on.year for t in all_published}, reverse=True)
    if ano not in years:
        ano = None
    published = [t for t in all_published if ano is None or t.published_on.year == ano]

    # Releases per month: every month of the chosen year, or first release → last.
    if ano:
        months = [(ano, m) for m in range(1, 13)]
    elif published:
        months = _months(published[0].published_on, max(published[-1].published_on, date.today()))
    else:
        months = []
    # Each month's bar is split by quadro. An episode counts once, under its first quadro
    # (by the quadros' order), so the bar's height is still the number of episodes.
    per_month: dict[tuple[int, int], Counter] = {}
    month_quadros: dict[int | None, Segment | None] = {}
    for t in published:
        seg = t.segments[0] if t.segments else None
        month_quadros[seg.id if seg else None] = seg
        per_month.setdefault((t.published_on.year, t.published_on.month), Counter())[seg.id if seg else None] += 1
    legend = sorted(month_quadros.values(), key=lambda s: (s is None, s.position if s else 0, s.name if s else ""))
    monthly = []
    for y, m in months:
        counts = per_month.get((y, m), Counter())
        monthly.append({
            "label": f"{MONTHS[m - 1]}/{str(y)[2:]}", "short": MONTHS[m - 1][0].upper() if ano else MONTHS[m - 1],
            "year": y, "first_of_year": m == 1, "count": sum(counts.values()),
            "parts": [(s, counts[s.id if s else None]) for s in legend if counts[s.id if s else None]],
        })

    days = [b.published_on - a.published_on for a, b in zip(published, published[1:])]
    last = all_published[-1].published_on if all_published else None
    kpis = {
        "published": len(published),
        "last": last,
        "since_last": (date.today() - last).days if last else None,
        "gap": round(median(d.days for d in days)) if days else None,
        "in_progress": db.scalar(select(func.count()).where(Theme.status.in_(["pauta", "agendado", "gravado"]))),
    }

    seg_counts: Counter = Counter()
    segs = {}
    people: Counter = Counter()
    members = {}
    games: Counter = Counter()
    game_rows = {}
    for t in published:
        for s in t.segments:
            seg_counts[s.id] += 1
            segs[s.id] = s
        for m in t.participants:
            people[m.id] += 1
            members[m.id] = m
        for g in t.games:
            games[g.id] += 1
            game_rows[g.id] = g

    pipeline = dict(db.execute(select(Theme.status, func.count()).group_by(Theme.status)).all())

    return render(
        request, "stats.html", me,
        ano=ano, years=years, kpis=kpis, monthly=monthly, legend=legend,
        month_max=max((r["count"] for r in monthly), default=0),
        by_segment=[(segs[i], n) for i, n in seg_counts.most_common()],
        by_member=[(members[i], n) for i, n in people.most_common()],
        by_game=[(game_rows[i], n) for i, n in games.most_common(10)],
        pipeline=[(THEME_STATUSES[s], pipeline.get(s, 0), s) for s in PIPELINE],
        no_segment=sum(1 for t in published if not t.segments),
    )
