"""Member photos: cropped to a small square on the data volume; initials when there's none."""

import io
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

from app.branding import DATA_DIR
from app.models import Member

PHOTO_DIR = DATA_DIR / "fotos"
MAX_BYTES = 15 * 1024 * 1024  # phone cameras; it's shrunk right away
SIZE = 256
Image.MAX_IMAGE_PIXELS = 50_000_000


class PhotoError(Exception):
    pass


def initials(name: str) -> str:
    words = [w for w in name.split() if w[:1].isalnum()]
    if not words:
        return "?"
    first, last = words[0][0], words[-1][0] if len(words) > 1 else ""
    return (first + last).upper()


def save(member: Member, data: bytes) -> None:
    """Stores the photo and points the member at it. Caller commits."""
    if not data:
        raise PhotoError("Escolha uma foto.")
    if len(data) > MAX_BYTES:
        raise PhotoError("A foto precisa ter até 15 MB.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ("JPEG", "PNG", "WEBP", "GIF", "MPO"):
                raise PhotoError("Envie uma foto JPG, PNG, WEBP ou GIF.")
            img.draft("RGB", (SIZE * 2, SIZE * 2))  # JPEG: decode at reduced size
            img = ImageOps.exif_transpose(img).convert("RGB")
            square = ImageOps.fit(img, (SIZE, SIZE), Image.LANCZOS)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise PhotoError("Não consegui ler essa imagem. Tente uma foto JPG ou PNG.")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    # A new name on every upload, so browsers can cache each file forever.
    name = f"{member.id}-{secrets.token_hex(4)}.webp"
    square.save(PHOTO_DIR / name, "WEBP", quality=85)  # re-encoding also drops EXIF (location etc.)
    remove(member)
    member.photo = name


def remove(member: Member) -> None:
    if member.photo:
        (PHOTO_DIR / member.photo).unlink(missing_ok=True)
    member.photo = None
