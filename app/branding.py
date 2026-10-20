"""The podcast logo: an uploaded image on the data volume, or the default icon."""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DEFAULT_LOGO = Path(__file__).parent / "static" / "icon.svg"
MAX_BYTES = 2 * 1024 * 1024

# Raster formats only: an uploaded SVG could carry scripts.
SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
}
MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


class LogoError(Exception):
    pass


def current() -> Path | None:
    for ext in MEDIA_TYPES:
        path = DATA_DIR / f"logo.{ext}"
        if path.exists():
            return path
    return None


def logo_url() -> str:
    path = current()
    return f"/logo?v={int(path.stat().st_mtime)}" if path else "/static/icon.svg"


def detect(data: bytes) -> str:
    for ext, sigs in SIGNATURES.items():
        if any(data.startswith(s) for s in sigs) and (ext != "webp" or data[8:12] == b"WEBP"):
            return ext
    raise LogoError("Envie uma imagem PNG, JPG, WEBP ou GIF.")


def save(data: bytes) -> None:
    if not data:
        raise LogoError("Escolha um arquivo.")
    if len(data) > MAX_BYTES:
        raise LogoError("A imagem precisa ter até 2 MB.")
    ext = detect(data)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / f".logo-upload.{ext}"
    tmp.write_bytes(data)
    reset()
    tmp.replace(DATA_DIR / f"logo.{ext}")


def reset() -> None:
    for ext in MEDIA_TYPES:
        (DATA_DIR / f"logo.{ext}").unlink(missing_ok=True)
