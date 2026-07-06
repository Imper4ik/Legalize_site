"""PDF rendering for email copies, extracted from ``notifications``.

Self-contained: turns plain email text into a paginated PDF via PIL. No
dependency on the notification-sending machinery, so it lives here and
``_render_email_pdf`` is imported back into ``notifications`` (callers and mock
targets there are unaffected).
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PDF_FONT_TEST_TEXT = "Привет"


def _get_pdf_font_path() -> Path | None:
    configured_path = str(getattr(settings, "PDF_FONT_PATH", ""))
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return path
        logger.warning("PDF font path does not exist: %s", configured_path)
    nix_store = Path("/nix/store")
    nix_candidates: list[Path] = []
    if nix_store.exists():
        nix_candidates.extend(nix_store.glob("**/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        nix_candidates.extend(nix_store.glob("**/share/fonts/truetype/noto/NotoSans-Regular.ttf"))
    candidate_paths = [
        Path(str(settings.BASE_DIR)) / "static" / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/arialuni.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        *nix_candidates,
    ]
    for path in candidate_paths:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), 24)
            except OSError:
                continue
            mask = font.getmask(PDF_FONT_TEST_TEXT)
            if not mask or mask.getbbox() is None:
                continue
            return path
    logger.warning("PDF font not found in default locations; falling back to PIL default font.")
    return None


def _wrap_text_lines(text: str, draw: ImageDraw.ImageDraw, font: Any, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _render_email_pdf(text: str) -> bytes:
    page_width, page_height = (1240, 1754)
    margin = 80
    font_path = _get_pdf_font_path()
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    if font_path:
        font = ImageFont.truetype(str(font_path), 24)
    else:
        logger.warning("Using PIL default font for PDF rendering.")
        font = ImageFont.load_default()
    temp_image = Image.new("RGB", (1, 1), "white")
    draw = ImageDraw.Draw(temp_image)
    max_width = page_width - (margin * 2)
    lines = _wrap_text_lines(text, draw, font, max_width)

    # Calculate line height
    if hasattr(font, "getbbox"):
        bbox = font.getbbox("Hg")
        line_height = int(bbox[3] - bbox[1] + 6)
    else:
        # Fallback for old PIL versions or default font
        line_height = 30

    max_lines_per_page = max(1, (page_height - (margin * 2)) // line_height)

    pages: list[Image.Image] = []
    for start in range(0, len(lines), max_lines_per_page):
        page = Image.new("RGB", (page_width, page_height), "white")
        page_draw = ImageDraw.Draw(page)
        y = margin
        for line in lines[start : start + max_lines_per_page]:
            page_draw.text((margin, y), line, font=font, fill="black")
            y += line_height
        pages.append(page)

    buffer = BytesIO()
    if pages:
        pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()
