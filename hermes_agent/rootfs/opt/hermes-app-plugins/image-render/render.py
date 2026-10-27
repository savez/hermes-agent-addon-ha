"""Conversione SVG -> raster e conversione fra formati raster.

Logica pura, senza dipendenze da Hermes: i test la importano direttamente.
Le cartelle (da dove si legge, dove si scrive) le passa sempre il chiamante.

Vincoli, ognuno con un motivo:
- Si scrive solo in `out_dir` (la cache immagini del profilo), con un nome
  generato: il tool non diventa un modo di scrivere file arbitrari.
- `convert_image` legge solo sotto `read_roots` (la cache del profilo): con i
  toolset `file`/`terminal` spenti l'agente non deve poter leggere altro
  (regola #8 di CLAUDE.md, il token di HA sta in /data/hermes/.env).
- Nell'SVG sono ammessi solo riferimenti interni (`#id`) o immagini raster
  inline (`data:image/png|jpeg|gif|webp`): resvg caricherebbe da disco
  qualunque `href` a un file, e un SVG annidato in un data URI potrebbe a sua
  volta puntare a un file.
- Lato massimo MAX_SIDE e SVG di al più MAX_SVG_CHARS: un `width="100000"`
  allocherebbe gigabyte e il gateway sul Pi verrebbe ucciso per memoria.
- Nell'immagine ci sono solo i font DejaVu: resvg scarta in silenzio il testo
  in una famiglia che non trova, quindi a ogni `font-family` si accoda una
  famiglia generica, mappata su DejaVu.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import uuid
from pathlib import Path

MAX_SIDE = 4096
MAX_SVG_CHARS = 2_000_000
# Lato massimo accettato in ingresso per convert_image (prima del resize).
MAX_INPUT_PIXELS = 50_000_000
PROBE_WIDTH = 16
DEFAULT_WIDTH = 1024

FORMATS = {"png": "PNG", "jpeg": "JPEG", "jpg": "JPEG", "webp": "WEBP"}
EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}

FONT_FAMILIES = {
    "font_family": "DejaVu Sans",
    "sans_serif_family": "DejaVu Sans",
    "serif_family": "DejaVu Serif",
    "monospace_family": "DejaVu Sans Mono",
    "cursive_family": "DejaVu Sans",
    "fantasy_family": "DejaVu Sans",
}
_GENERIC = ("sans-serif", "serif", "monospace", "cursive", "fantasy")

_HREF_RE = re.compile(r"""(?:[\w.-]+:)?href\s*=\s*(["'])(.*?)\1""", re.S)
_DATA_OK_RE = re.compile(r"data:image/(?:png|jpeg|jpg|gif|webp)[;,]", re.I)
_CSS_URL_RE = re.compile(r"""url\(\s*["']?([^"')]*)""", re.I)
_FONT_ATTR_RE = re.compile(r"""(font-family\s*=\s*)(["'])(.*?)\2""", re.S)
_FONT_CSS_RE = re.compile(r"""(font-family\s*:\s*)([^;}"<>]+)""")
_SVG_TAG_RE = re.compile(r"<svg\b[^>]*>", re.S | re.I)


class RenderError(ValueError):
    """Errore da riportare all'agente così com'è (mai contenuto di file)."""


def _normalize_format(fmt: str | None) -> str:
    key = (fmt or "png").strip().lower().lstrip(".")
    if key not in FORMATS:
        raise RenderError(f"Formato non supportato: {fmt!r}. Usa png, jpg o webp.")
    return FORMATS[key]


def check_refs(svg: str) -> None:
    """Rifiuta riferimenti a file o URL esterni (vedi docstring del modulo)."""
    for _, value in _HREF_RE.findall(svg):
        value = value.strip()
        if value.startswith("#") or _DATA_OK_RE.match(value):
            continue
        raise RenderError(
            "Riferimento esterno non ammesso nell'SVG: usa solo #id o immagini "
            "inline data:image/png|jpeg|gif|webp;base64,...")
    for value in _CSS_URL_RE.findall(svg):
        value = value.strip()
        if value.startswith("#") or _DATA_OK_RE.match(value):
            continue
        raise RenderError("url(...) esterno non ammesso nell'SVG: usa solo url(#id).")


def _with_generic(families: str) -> str:
    names = [f.strip().strip("'\"").lower() for f in families.split(",")]
    if any(n in _GENERIC for n in names):
        return families
    return f"{families.rstrip()}, sans-serif"


def add_font_fallback(svg: str) -> str:
    """Accoda `sans-serif` a ogni font-family che non ha già una generica."""
    svg = _FONT_ATTR_RE.sub(lambda m: f"{m[1]}{m[2]}{_with_generic(m[3])}{m[2]}", svg)
    return _FONT_CSS_RE.sub(lambda m: f"{m[1]}{_with_generic(m[2])}", svg)


def _intrinsic_width(svg: str) -> float | None:
    """Larghezza dichiarata dal tag <svg> (numero o px), altrimenti dal viewBox."""
    tag = _SVG_TAG_RE.search(svg)
    if not tag:
        return None
    attrs = tag.group(0)
    m = re.search(r"""\swidth\s*=\s*["']\s*([\d.]+)\s*(px)?\s*["']""", attrs)
    if m:
        return float(m.group(1))
    m = re.search(r"""viewBox\s*=\s*["']\s*[-\d.eE]+[\s,]+[-\d.eE]+[\s,]+([\d.eE]+)""", attrs)
    if m:
        return float(m.group(1))
    return None


def _render_svg(svg: str, width: int, background: str | None, resources_dir: str) -> bytes:
    import resvg_py

    try:
        return bytes(resvg_py.svg_to_bytes(
            svg_string=svg, width=width, background=background,
            resources_dir=resources_dir, **FONT_FAMILIES))
    except BaseException as e:  # resvg_py solleva anche PanicException
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        raise RenderError(f"SVG non valido: {str(e)[:200]}") from None


def _fit(width: float, height: float, req_w: int | None, req_h: int | None) -> tuple[int, int]:
    """Dimensioni finali: rispetta le proporzioni e il lato massimo."""
    if req_w and req_h:
        scale = min(req_w / width, req_h / height)
    elif req_w:
        scale = req_w / width
    elif req_h:
        scale = req_h / height
    else:
        scale = 1.0
    scale = min(scale, MAX_SIDE / width, MAX_SIDE / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _positive_int(value, name: str) -> int | None:
    if value in (None, "", 0):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise RenderError(f"{name} deve essere un intero positivo") from None
    if n <= 0:
        raise RenderError(f"{name} deve essere un intero positivo")
    return n


def _encode(img, fmt: str, background: str | None, quality: int) -> bytes:
    from PIL import Image

    if fmt == "JPEG" or background:
        # JPEG non ha trasparenza: senza sfondo esplicito si appiattisce sul bianco.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            try:
                base = Image.new("RGBA", img.size, background or "white")
            except ValueError:
                raise RenderError(f"Colore di sfondo non valido: {background!r}") from None
            img = Image.alpha_composite(base, img)
        if fmt == "JPEG":
            img = img.convert("RGB")
    buf = io.BytesIO()
    if fmt == "PNG":
        img.save(buf, "PNG", optimize=True)
    else:
        img.save(buf, fmt, quality=max(1, min(int(quality), 100)))
    return buf.getvalue()


def _write(out_dir: Path, data: bytes, fmt: str, name_hint: str | None) -> Path:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(name_hint or "image").stem).strip("-")[:40] or "image"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}-{uuid.uuid4().hex[:8]}.{EXTENSIONS[fmt]}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _result(path: Path, fmt: str, size: tuple[int, int], data: bytes) -> dict:
    return {
        "path": str(path),
        "media": f"MEDIA:{path}",
        "format": EXTENSIONS[fmt],
        "width": size[0],
        "height": size[1],
        "bytes": len(data),
        "hint": "Per inviare l'immagine includi la riga MEDIA:<path> nella risposta. "
                "Per controllarla puoi passarla al tool di vision.",
    }


def svg_to_image(svg: str, out_dir: Path, *, fmt: str | None = "png", width=None, height=None,
                 background: str | None = None, quality: int = 90, filename: str | None = None) -> dict:
    from PIL import Image

    if not isinstance(svg, str) or not svg.strip():
        raise RenderError("Il parametro svg è vuoto: passa il markup SVG completo.")
    if len(svg) > MAX_SVG_CHARS:
        raise RenderError(f"SVG troppo grande ({len(svg)} caratteri, massimo {MAX_SVG_CHARS}).")
    out_fmt = _normalize_format(fmt)
    req_w, req_h = _positive_int(width, "width"), _positive_int(height, "height")
    check_refs(svg)
    svg = add_font_fallback(svg)

    with tempfile.TemporaryDirectory() as empty:
        # Un render minuscolo dà le proporzioni senza allocare l'immagine piena.
        probe = Image.open(io.BytesIO(_render_svg(svg, PROBE_WIDTH, None, empty)))
        ratio = probe.height / probe.width
        native_w = _intrinsic_width(svg) or (req_w or DEFAULT_WIDTH)
        target_w, _ = _fit(native_w, native_w * ratio, req_w, req_h)
        png = _render_svg(svg, target_w, None, empty)

    img = Image.open(io.BytesIO(png))
    img.load()
    data = _encode(img, out_fmt, background, quality)
    path = _write(out_dir, data, out_fmt, filename)
    return _result(path, out_fmt, img.size, data)


def _inside(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def convert_image(src: str, out_dir: Path, read_roots: list[Path], *, fmt: str | None = "png",
                  width=None, height=None, background: str | None = None,
                  quality: int = 90) -> dict:
    from PIL import Image, ImageOps

    if not src or not isinstance(src, str):
        raise RenderError("Il parametro path è vuoto.")
    path = Path(os.path.expanduser(src))
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RenderError(f"File non trovato: {src}") from None
    if not _inside(path, read_roots) or not path.is_file():
        allowed = ", ".join(str(r) for r in read_roots)
        raise RenderError(f"Si possono convertire solo file nella cache di Hermes ({allowed}).")

    out_fmt = _normalize_format(fmt)
    req_w, req_h = _positive_int(width, "width"), _positive_int(height, "height")

    if path.suffix.lower() == ".svg":
        if path.stat().st_size > MAX_SVG_CHARS * 4:
            raise RenderError("SVG troppo grande.")
        svg = path.read_text(encoding="utf-8", errors="replace")
        return svg_to_image(svg, out_dir, fmt=out_fmt, width=req_w, height=req_h,
                            background=background, quality=quality, filename=path.name)

    try:
        import pillow_heif  # HEIC/AVIF delle foto da telefono, già nel venv di Hermes

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        img = Image.open(path)
    except Exception:
        raise RenderError("Il file non è un'immagine riconosciuta.") from None
    if img.width * img.height > MAX_INPUT_PIXELS:
        raise RenderError(f"Immagine troppo grande ({img.width}x{img.height}).")
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    size = _fit(img.width, img.height, req_w, req_h)
    if size != img.size:
        img = img.resize(size, Image.LANCZOS)
    data = _encode(img, out_fmt, background, quality)
    out = _write(out_dir, data, out_fmt, path.name)
    return _result(out, out_fmt, img.size, data)
