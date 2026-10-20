from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import THEME_STATUSES, Member, Theme, ThemeComment, ThemeVote
from app.web import current_member, render

router = APIRouter(prefix="/temas")

SORTS = {"votos": "Mais votados", "recentes": "Mais recentes"}


def _theme_or_404(db: Session, theme_id: int) -> Theme:
    theme = db.get(Theme, theme_id)
    if not theme:
        raise HTTPException(404, "Tema não encontrado.")
    return theme


def _back(request: Request, fallback: str) -> RedirectResponse:
    # Return to the page the form was on (list or detail); only same-site paths.
    ref = request.headers.get("referer", "")
    path = ref.split(request.url.netloc, 1)[-1] if request.url.netloc in ref else ""
    return RedirectResponse(path if path.startswith("/") else fallback, status_code=303)


@router.get("")
def list_themes(
    request: Request,
    status: str = "abertos",
    ordem: str = "votos",
    q: str = "",
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    votes = func.count(ThemeVote.member_id)
    stmt = select(Theme, votes).outerjoin(ThemeVote).group_by(Theme.id)
    if status == "abertos":
        stmt = stmt.where(Theme.status.in_(["ideia", "pauta"]))
    elif status in THEME_STATUSES:
        stmt = stmt.where(Theme.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(Theme.title.ilike(like) | Theme.description.ilike(like))
    if ordem == "recentes":
        stmt = stmt.order_by(Theme.created_at.desc())
    else:
        stmt = stmt.order_by(votes.desc(), Theme.created_at.desc())
    rows = db.execute(stmt).all()
    counts = dict(db.execute(select(Theme.status, func.count()).group_by(Theme.status)).all())
    my_votes = set(db.scalars(select(ThemeVote.theme_id).where(ThemeVote.member_id == me.id)).all())
    comment_counts = dict(
        db.execute(select(ThemeComment.theme_id, func.count()).group_by(ThemeComment.theme_id)).all()
    )
    return render(
        request,
        "themes.html",
        me,
        rows=rows,
        status=status,
        ordem=ordem,
        q=q,
        counts=counts,
        my_votes=my_votes,
        comment_counts=comment_counts,
        sorts=SORTS,
    )


@router.post("")
def create_theme(
    title: str = Form(...),
    description: str = Form(""),
    links: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    title = title.strip()
    if not title:
        raise HTTPException(400, "O tema precisa de um título.")
    theme = Theme(title=title[:200], description=description.strip(), links=links.strip(), created_by_id=me.id)
    db.add(theme)
    db.flush()
    db.add(ThemeVote(theme_id=theme.id, member_id=me.id))  # suggesting counts as wanting it
    db.commit()
    return RedirectResponse(f"/temas/{theme.id}", status_code=303)


@router.get("/{theme_id}")
def show_theme(theme_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    voters = sorted((v.member for v in theme.votes), key=lambda m: m.name)
    return render(
        request,
        "theme.html",
        me,
        theme=theme,
        voters=voters,
        voted=any(v.id == me.id for v in voters),
        can_delete=me.is_admin or theme.created_by_id == me.id,
    )


@router.post("/{theme_id}/editar")
def edit_theme(
    theme_id: int,
    title: str = Form(...),
    description: str = Form(""),
    links: str = Form(""),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    if title.strip():
        theme.title = title.strip()[:200]
    theme.description = description.strip()
    theme.links = links.strip()
    db.commit()
    return RedirectResponse(f"/temas/{theme_id}", status_code=303)


@router.post("/{theme_id}/voto")
def toggle_vote(theme_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    _theme_or_404(db, theme_id)
    vote = db.get(ThemeVote, (theme_id, me.id))
    if vote:
        db.delete(vote)
    else:
        db.add(ThemeVote(theme_id=theme_id, member_id=me.id))
    db.commit()
    return _back(request, f"/temas/{theme_id}")


@router.post("/{theme_id}/status")
def set_status(
    theme_id: int,
    status: str = Form(...),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    if status not in THEME_STATUSES:
        raise HTTPException(400, "Status inválido.")
    _theme_or_404(db, theme_id).status = status
    db.commit()
    return RedirectResponse(f"/temas/{theme_id}", status_code=303)


@router.post("/{theme_id}/comentarios")
def add_comment(
    theme_id: int,
    body: str = Form(...),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    _theme_or_404(db, theme_id)
    if body.strip():
        db.add(ThemeComment(theme_id=theme_id, member_id=me.id, body=body.strip()))
        db.commit()
    return RedirectResponse(f"/temas/{theme_id}#comentarios", status_code=303)


@router.post("/{theme_id}/comentarios/{comment_id}/excluir")
def delete_comment(
    theme_id: int, comment_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    comment = db.get(ThemeComment, comment_id)
    if comment and comment.theme_id == theme_id and (comment.member_id == me.id or me.is_admin):
        db.delete(comment)
        db.commit()
    return RedirectResponse(f"/temas/{theme_id}#comentarios", status_code=303)


@router.post("/{theme_id}/excluir")
def delete_theme(theme_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    if not (me.is_admin or theme.created_by_id == me.id):
        raise HTTPException(403, "Só quem sugeriu o tema ou um admin pode excluir.")
    db.delete(theme)
    db.commit()
    return RedirectResponse("/temas", status_code=303)
