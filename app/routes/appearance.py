"""Aparência: the podcast logo, editable by any member."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import branding
from app.models import Member
from app.web import current_member, render

router = APIRouter()


@router.get("/logo")
def logo():
    # Public: the login page shows it too.
    path = branding.current()
    if not path:
        return RedirectResponse("/static/icon.svg")
    ext = path.suffix.lstrip(".")
    return FileResponse(path, media_type=branding.MEDIA_TYPES[ext], headers={"Cache-Control": "public, max-age=86400"})


@router.get("/aparencia")
def appearance_page(request: Request, me: Member = Depends(current_member)):
    return render(request, "appearance.html", me, custom=branding.current() is not None)


@router.post("/aparencia/logo")
async def upload_logo(request: Request, file: UploadFile = File(...), me: Member = Depends(current_member)):
    data = await file.read(branding.MAX_BYTES + 1)
    try:
        branding.save(data)
    except branding.LogoError as e:
        return render(request, "appearance.html", me, custom=branding.current() is not None, error=str(e))
    return RedirectResponse("/aparencia?ok=1", status_code=303)


@router.post("/aparencia/logo/padrao")
def reset_logo(_me: Member = Depends(current_member)):
    branding.reset()
    return RedirectResponse("/aparencia?ok=1", status_code=303)
