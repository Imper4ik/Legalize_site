"""Small QR marker embedded in the printed Mazowiecki cover sheet.

The QR encodes a signed reference to the ``WniosekSubmission`` the sheet is
printed for. When the stamped sheet is later uploaded as a proof of submission,
the marker is decoded to auto-link it to the exact submission (with a reliable
"latest submission for the case" fallback when the photo is unreadable).
"""
from __future__ import annotations

import io
import logging

from django.core import signing

logger = logging.getLogger(__name__)

PROOF_QR_PREFIX = "LZS1:"
PROOF_SIGNING_SALT = "clients.proof_of_submission"


def build_proof_token(submission_id: int) -> str:
    """Return the signed, prefixed payload embedded in the cover-sheet QR."""
    signed = signing.dumps(int(submission_id), salt=PROOF_SIGNING_SALT)
    return f"{PROOF_QR_PREFIX}{signed}"


def parse_proof_token(text: str | None) -> int | None:
    """Recover the submission id from a decoded QR payload, or ``None``."""
    if not text or not text.startswith(PROOF_QR_PREFIX):
        return None
    payload = text[len(PROOF_QR_PREFIX):]
    try:
        return int(signing.loads(payload, salt=PROOF_SIGNING_SALT))
    except (signing.BadSignature, ValueError, TypeError):
        return None


def build_proof_qr_svg_data_uri(submission_id: int) -> str | None:
    """Build a compact SVG ``data:`` URI for the cover-sheet QR, or ``None``.

    SVG keeps the marker crisp at print resolution while staying tiny and
    dependency-light (no raster encoder needed at render time)."""
    try:
        import segno
    except ImportError:  # pragma: no cover - segno is a hard dependency in prod
        logger.warning("segno is not available; skipping cover-sheet QR marker")
        return None
    try:
        qr = segno.make(build_proof_token(submission_id), error="m")
        return qr.svg_data_uri(scale=3, border=2)
    except Exception as exc:  # pragma: no cover - defensive; never block printing
        logger.warning("Failed to build cover-sheet QR marker: %s", exc)
        return None


def _decode_qr_from_image_bytes(image_bytes: bytes) -> int | None:
    try:
        import cv2
        import numpy as np
    except ImportError:  # pragma: no cover - cv2/numpy are hard deps in prod
        return None
    try:
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return None
        data, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
        return parse_proof_token(data)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("QR decode from image failed: %s", exc)
        return None


def decode_proof_submission_id(file_bytes: bytes, *, is_pdf: bool) -> int | None:
    """Best-effort: decode the submission id from an uploaded proof file.

    Returns ``None`` when no valid marker is found so callers fall back to the
    default "latest submission for the case" linking."""
    if not file_bytes:
        return None
    if is_pdf:
        try:
            from pdf2image import convert_from_bytes

            pages = convert_from_bytes(file_bytes, first_page=1, last_page=2, dpi=200)
        except Exception as exc:  # pragma: no cover - poppler may be unavailable
            logger.info("Could not rasterize PDF for QR decode: %s", exc)
            return None
        for page in pages:
            buffer = io.BytesIO()
            page.save(buffer, format="PNG")
            submission_id = _decode_qr_from_image_bytes(buffer.getvalue())
            if submission_id is not None:
                return submission_id
        return None
    return _decode_qr_from_image_bytes(file_bytes)
