"""Image preprocessing for OCR — deskew, denoise, contrast enhancement.

Improves OCR accuracy on scanned documents by cleaning up the image
before passing it to Tesseract (or any other OCR engine).

Requires OpenCV::

    pip install 'ppke[preprocess]'

All functions accept and return PIL Images so they slot naturally into
the existing OCR pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def preprocess_for_ocr(
    img: Any,
    *,
    deskew: bool = True,
    denoise: bool = True,
    contrast: bool = True,
    binarize: bool = False,
    resize_factor: float | None = None,
) -> Any:
    """Apply a battery of preprocessing steps to a PIL Image.

    Parameters
    ----------
    img:
        A ``PIL.Image.Image`` instance.
    deskew:
        Correct rotation / skew using Hough transform.
    denoise:
        Apply non-local means denoising.
    contrast:
        Apply CLAHE (Contrast-Limited Adaptive Histogram Equalization).
    binarize:
        Convert to binary (black & white) using adaptive thresholding.
        Useful for very noisy scans but may lose grey-scale detail.
    resize_factor:
        Scale factor for up/down-sizing. ``2.0`` means double the dimensions
        (useful for tiny text).  ``None`` skips resizing.

    Returns
    -------
    PIL.Image.Image
        The preprocessed image, ready for OCR.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        logger.debug("OpenCV not installed — skipping image preprocessing")
        return img  # Return original unchanged

    # PIL → OpenCV (BGR)
    cv_img = np.array(img)
    if len(cv_img.shape) == 2:
        # Already grayscale
        gray = cv_img
        is_color = False
    elif cv_img.shape[2] == 4:
        # RGBA → BGR
        gray = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2GRAY)
        is_color = True
    else:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
        is_color = True

    # 1. Resize
    if resize_factor is not None and resize_factor > 0 and resize_factor != 1.0:
        h, w = gray.shape[:2]
        new_w = int(w * resize_factor)
        new_h = int(h * resize_factor)
        interpolation = cv2.INTER_CUBIC if resize_factor > 1 else cv2.INTER_AREA
        gray = cv2.resize(gray, (new_w, new_h), interpolation=interpolation)
        logger.debug("Resized image to %dx%d (factor %.2f)", new_w, new_h, resize_factor)

    # 2. Deskew
    if deskew:
        gray = _deskew(gray)

    # 3. Denoise
    if denoise:
        gray = _denoise(gray)

    # 4. Contrast enhancement (CLAHE)
    if contrast:
        gray = _enhance_contrast(gray)

    # 5. Binarize (optional)
    if binarize:
        gray = _binarize(gray)

    # OpenCV → PIL
    return Image.fromarray(gray)


# ── Individual pipeline steps ───────────────────────────────────────


def _deskew(gray: Any) -> Any:
    """Correct skew angle using projection profile / Hough lines.

    Detects the dominant line angle in the image and rotates to
    correct it.  Leaves the image unchanged if no clear skew
    is detected (< 0.3° or > 15°).
    """
    import cv2
    import numpy as np

    # Edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Probabilistic Hough Transform
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=100,
        minLineLength=gray.shape[1] // 4,
        maxLineGap=20,
    )

    if lines is None or len(lines) == 0:
        logger.debug("No lines detected for deskew — skipping")
        return gray

    # Compute angles of all detected lines
    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1:
            continue
        angle = np.degrees(np.arctan2(dy, dx))
        # Only consider near-horizontal lines (±45°)
        if abs(angle) < 45:
            angles.append(angle)

    if not angles:
        return gray

    # Median angle is more robust than mean against outliers
    median_angle = float(np.median(angles))

    # Don't correct very small or unreasonably large angles
    if abs(median_angle) < 0.3 or abs(median_angle) > 15:
        logger.debug("Skew angle %.2f° — outside correction range, skipping", median_angle)
        return gray

    logger.info("Deskewing by %.2f°", -median_angle)

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)

    # Compute new bounding box to avoid clipping corners
    cos_a = abs(rotation_matrix[0, 0])
    sin_a = abs(rotation_matrix[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    rotation_matrix[0, 2] += (new_w - w) / 2
    rotation_matrix[1, 2] += (new_h - h) / 2

    rotated = cv2.warpAffine(
        gray, rotation_matrix, (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def _denoise(gray: Any) -> Any:
    """Apply non-local means denoising.

    Uses the fast variant ``fastNlMeansDenoising`` tuned for
    scanned document images (moderate noise, sharp text edges).
    """
    import cv2

    try:
        denoised = cv2.fastNlMeansDenoising(
            gray,
            None,
            h=10,             # filter strength — higher removes more noise
            templateWindowSize=7,
            searchWindowSize=21,
        )
        logger.debug("Applied NLMeans denoising")
        return denoised
    except Exception as exc:
        logger.debug("Denoising failed: %s", exc)
        return gray


def _enhance_contrast(gray: Any) -> Any:
    """Apply CLAHE (Contrast-Limited Adaptive Histogram Equalization).

    CLAHE prevents over-amplification of contrast in already-bright
    areas while boosting faded text regions.
    """
    import cv2

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    logger.debug("Applied CLAHE contrast enhancement")
    return enhanced


def _binarize(gray: Any) -> Any:
    """Adaptive thresholding — converts to pure black & white.

    Uses Gaussian-weighted adaptive thresholding which handles
    uneven lighting across the page better than global Otsu.
    """
    import cv2

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,   # neighbourhood size
        C=8,            # constant subtracted from mean
    )
    logger.debug("Applied adaptive binarization")
    return binary
