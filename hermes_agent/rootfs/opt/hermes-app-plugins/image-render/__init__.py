"""image-render — SVG in PNG/JPEG/WEBP e conversione di immagini, per Hermes.

Plugin dell'App (non del catalogo di Hermes): sta nell'immagine in
/opt/hermes-app-plugins e `render_config.py` lo collega e lo abilita in ogni
profilo. Registra il toolset `image_render` tramite l'API pubblica dei plugin
(`ctx.register_tool`). La logica sta in `render.py`.

Le cartelle si risolvono a ogni chiamata, non all'import: lo stesso gateway
serve tutti i profili (multiplex) e `get_hermes_home()` dipende dal profilo
della richiesta in corso.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import render

logger = logging.getLogger(__name__)

TOOLSET = "image_render"


def _error(message: str) -> str:
    return json.dumps({"error": str(message)}, ensure_ascii=False)


def _home() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def _out_dir() -> Path:
    # Stessa cartella delle immagini ricevute dalle piattaforme: è fra quelle
    # da cui il gateway consegna i MEDIA: senza condizioni.
    from hermes_constants import get_hermes_dir

    return get_hermes_dir("cache/images", "image_cache")


def _read_roots() -> list[Path]:
    home = _home()
    return [home / "cache", home / "image_cache"]


def _check_available() -> bool:
    try:
        import PIL  # noqa: F401
        import resvg_py  # noqa: F401
    except ImportError:
        return False
    return True


def _handle_svg_to_image(args: dict, **kw) -> str:
    try:
        result = render.svg_to_image(
            args.get("svg"), _out_dir(), fmt=args.get("format"), width=args.get("width"),
            height=args.get("height"), background=args.get("background"),
            quality=args.get("quality") or 90, filename=args.get("filename"))
    except render.RenderError as e:
        return _error(e)
    except Exception as e:
        logger.exception("image-render: svg_to_image fallito")
        return _error(f"Conversione fallita: {type(e).__name__}")
    return json.dumps(result, ensure_ascii=False)


def _handle_convert_image(args: dict, **kw) -> str:
    try:
        result = render.convert_image(
            args.get("path"), _out_dir(), _read_roots(), fmt=args.get("format"),
            width=args.get("width"), height=args.get("height"),
            background=args.get("background"), quality=args.get("quality") or 90)
    except render.RenderError as e:
        return _error(e)
    except Exception as e:
        logger.exception("image-render: convert_image fallito")
        return _error(f"Conversione fallita: {type(e).__name__}")
    return json.dumps(result, ensure_ascii=False)


_COMMON_PROPS = {
    "format": {"type": "string", "enum": ["png", "jpg", "jpeg", "webp"],
               "description": "Output format. Default: png."},
    "width": {"type": "integer", "description": "Target width in px (aspect ratio is kept). Max 4096."},
    "height": {"type": "integer", "description": "Target height in px (aspect ratio is kept). Max 4096."},
    "background": {"type": "string",
                   "description": "CSS colour for the background, e.g. '#ffffff'. Transparent by default "
                                  "for png/webp; jpg is always flattened (white if not given)."},
    "quality": {"type": "integer", "description": "jpg/webp quality 1-100. Default 90."},
}

SVG_TO_IMAGE_SCHEMA = {
    "name": "svg_to_image",
    "description": (
        "Render SVG markup to a PNG, JPG or WEBP file you can send to the user or inspect with vision. "
        "Use it to create charts, diagrams, cards, icons, posters: write the full SVG yourself, then call "
        "this tool. Returns JSON with `path` and `media`; to deliver the image put the `media` line "
        "(MEDIA:/absolute/path) in your reply. Draw a background rect or pass `background`: transparent "
        "areas can show up black in chat apps. Fonts available: sans-serif, serif, monospace (DejaVu); "
        "other families fall back to sans-serif, colour emoji are not available. Only internal references "
        "(#id) and inline data:image/png|jpeg|gif|webp images are allowed: no external files or URLs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "svg": {"type": "string", "description": "Complete SVG document, starting with <svg ...>. "
                                                      "Include width/height or a viewBox."},
            **_COMMON_PROPS,
            "filename": {"type": "string", "description": "Optional short name for the output file."},
        },
        "required": ["svg"],
    },
}

CONVERT_IMAGE_SCHEMA = {
    "name": "convert_image",
    "description": (
        "Convert or resize an existing image (png, jpg, webp, gif, bmp, heic, svg) into PNG, JPG or WEBP. "
        "Only files in Hermes' cache are accepted, e.g. images the user sent or files produced by "
        "svg_to_image. Returns JSON with `path` and `media` (put the MEDIA: line in your reply to send it)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path of the source image."},
            **_COMMON_PROPS,
        },
        "required": ["path"],
    },
}


def register(ctx) -> None:
    """Entry point chiamato dal loader dei plugin di Hermes."""
    for schema, handler, emoji in (
        (SVG_TO_IMAGE_SCHEMA, _handle_svg_to_image, "🖼️"),
        (CONVERT_IMAGE_SCHEMA, _handle_convert_image, "🔄"),
    ):
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema,
                          handler=handler, check_fn=_check_available, emoji=emoji)
