"""Test del plugin `image-render` (rootfs/opt/hermes-app-plugins/image-render).

Provano `render.py` direttamente, senza Hermes. Servono le stesse librerie
che il plugin trova nel venv di Hermes:

    uv run -p 3.14 --with resvg-py==0.4.0 --with pillow --with pytest \\
        pytest tests/test_image_render.py

Il testo è verificato solo se i font DejaVu sono installati (nell'immagine li
porta `fonts-dejavu-core`); altrove quel test viene saltato.
"""
import importlib.util
import io
import os
from pathlib import Path

import pytest

pytest.importorskip("resvg_py")
from PIL import Image  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_PY = REPO_ROOT / "hermes_agent" / "rootfs" / "opt" / "hermes-app-plugins" / "image-render" / "render.py"
_spec = importlib.util.spec_from_file_location("image_render_render", RENDER_PY)
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)

RECT = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="200" height="100" fill="#ff0000"/></svg>')


def _open(result):
    return Image.open(result["path"])


def test_png_native_size(tmp_path):
    r = render.svg_to_image(RECT, tmp_path)
    assert r["format"] == "png" and (r["width"], r["height"]) == (200, 100)
    assert r["media"] == f"MEDIA:{r['path']}"
    assert Path(r["path"]).parent == tmp_path
    assert _open(r).getpixel((10, 10))[:3] == (255, 0, 0)


def test_jpg_flattens_transparency_on_white(tmp_path):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
           '<rect width="50" height="100" fill="#0000ff"/></svg>')
    r = render.svg_to_image(svg, tmp_path, fmt="jpg")
    img = _open(r)
    assert img.format == "JPEG" and r["path"].endswith(".jpg")
    assert all(c > 240 for c in img.getpixel((90, 50)))


def test_webp_and_background(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"/>'
    r = render.svg_to_image(svg, tmp_path, fmt="webp", background="#00ff00")
    img = _open(r).convert("RGB")
    assert img.getpixel((20, 20))[1] > 200


def test_width_keeps_aspect_ratio(tmp_path):
    r = render.svg_to_image(RECT, tmp_path, width=1000)
    assert (r["width"], r["height"]) == (1000, 500)
    r = render.svg_to_image(RECT, tmp_path, height=300)
    assert (r["width"], r["height"]) == (600, 300)


def test_huge_svg_is_clamped(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100000" height="50000"><rect width="10" height="10"/></svg>'
    r = render.svg_to_image(svg, tmp_path)
    assert max(r["width"], r["height"]) <= render.MAX_SIDE
    r = render.svg_to_image(RECT, tmp_path, width=99999)
    assert r["width"] == render.MAX_SIDE


def test_viewbox_only(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 150"><circle cx="150" cy="75" r="50"/></svg>'
    r = render.svg_to_image(svg, tmp_path)
    assert (r["width"], r["height"]) == (300, 150)


@pytest.mark.parametrize("href", [
    "/data/hermes/.env",
    "file:///etc/passwd",
    "http://example.com/x.png",
    "&#47;data/hermes/x.png",
    "data:image/svg+xml;base64,PHN2Zy8+",
])
def test_external_refs_rejected(tmp_path, href):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="10" height="10"><image xlink:href="{href}" width="10" height="10"/></svg>')
    with pytest.raises(render.RenderError):
        render.svg_to_image(svg, tmp_path)
    assert not list(tmp_path.iterdir())


def test_css_url_rejected(tmp_path):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
           '<rect width="10" height="10" style="fill:url(/etc/x.svg#g)"/></svg>')
    with pytest.raises(render.RenderError):
        render.svg_to_image(svg, tmp_path)


def test_internal_refs_and_inline_png_allowed(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, "PNG")
    import base64
    data = base64.b64encode(buf.getvalue()).decode()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="20" height="20">'
           '<defs><linearGradient id="g"><stop offset="0" stop-color="#000"/></linearGradient></defs>'
           '<rect width="10" height="10" fill="url(#g)"/>'
           f'<image href="data:image/png;base64,{data}" x="10" y="10" width="10" height="10"/></svg>')
    r = render.svg_to_image(svg, tmp_path)
    assert _open(r).getpixel((15, 15))[:3] == (255, 0, 0)


@pytest.mark.parametrize("svg", ["", "   ", "ciao", '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"/>'])
def test_invalid_svg_is_a_clean_error(tmp_path, svg):
    with pytest.raises(render.RenderError):
        render.svg_to_image(svg, tmp_path)


def test_too_long_svg_rejected(tmp_path):
    with pytest.raises(render.RenderError):
        render.svg_to_image("<svg>" + " " * render.MAX_SVG_CHARS + "</svg>", tmp_path)


def test_bad_format_rejected(tmp_path):
    with pytest.raises(render.RenderError):
        render.svg_to_image(RECT, tmp_path, fmt="gif")


def test_font_fallback_rewrite():
    f = render.add_font_fallback
    assert f('<text font-family="Comic Sans MS">') == '<text font-family="Comic Sans MS, sans-serif">'
    assert f("<text font-family='Arial, serif'>") == "<text font-family='Arial, serif'>"
    assert f('<text style="font-family: Arial; fill:red">') == '<text style="font-family: Arial, sans-serif; fill:red">'
    assert f('<style>text { font-family: monospace }</style>') == '<style>text { font-family: monospace }</style>'


@pytest.mark.skipif(not Path("/usr/share/fonts/truetype/dejavu").is_dir(), reason="font DejaVu assenti")
def test_text_is_rendered_with_unknown_family(tmp_path):
    # Senza font, o con una famiglia che non c'è, resvg scarta il testo in
    # silenzio: si controlla che nell'area del testo ci siano pixel scuri.
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80">'
           '<rect width="300" height="80" fill="white"/>'
           '<text x="10" y="55" font-family="Comic Sans MS" font-size="40" fill="black">Ciao àè</text></svg>')
    r = render.svg_to_image(svg, tmp_path)
    img = _open(r).convert("L")
    dark = sum(img.histogram()[:100])
    assert dark > 200


def test_convert_image_resize_and_format(tmp_path):
    cache = tmp_path / "cache"
    (cache / "images").mkdir(parents=True)
    src = cache / "images" / "foto.png"
    Image.new("RGBA", (800, 400), (0, 0, 255, 128)).save(src)
    r = render.convert_image(str(src), cache / "images", [cache], fmt="jpg", width=200)
    assert (r["width"], r["height"]) == (200, 100)
    assert _open(r).format == "JPEG"


def test_convert_image_svg_file(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "x.svg").write_text(RECT)
    r = render.convert_image(str(cache / "x.svg"), cache, [cache])
    assert (r["width"], r["height"]) == (200, 100)


def test_convert_image_outside_cache_rejected(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    secret = tmp_path / ".env"
    secret.write_text("HERMES_HA_TOKEN=segreto\n")
    with pytest.raises(render.RenderError) as e:
        render.convert_image(str(secret), cache, [cache])
    assert "segreto" not in str(e.value)
    # Neanche passando dalla cache con un link o con ../
    os.symlink(secret, cache / "link.png")
    with pytest.raises(render.RenderError):
        render.convert_image(str(cache / "link.png"), cache, [cache])
    with pytest.raises(render.RenderError):
        render.convert_image(str(cache / ".." / ".env"), cache, [cache])


def test_convert_image_non_image_in_cache(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "note.png").write_text("HERMES_HA_TOKEN=segreto\n")
    with pytest.raises(render.RenderError) as e:
        render.convert_image(str(cache / "note.png"), cache, [cache])
    assert "segreto" not in str(e.value)
