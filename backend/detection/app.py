"""
App detection - identifies which social media platform is being viewed.
Uses OCR to find keywords, falls back to aspect ratio detection.
"""

from PIL import Image

try:
    import pytesseract  # type: ignore[import-not-found]

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


# Keywords that identify each platform
KEYWORDS = {
    "tiktok": ["for you", "following", "tiktok"],
    "instagram": ["reels", "story", "instagram"],
    "youtube": ["subscribe", "shorts", "youtube"],
    "twitter": ["tweet", "retweet", "timeline", "repost", "x.com"],
}


def is_vertical_video(im: Image.Image) -> bool:
    """Check if image has vertical aspect ratio (typical of short-form content)."""
    return (im.width / max(1, im.height)) < 0.7


def detect_app(im: Image.Image) -> str:
    """
    Identify which app is being viewed.

    Returns:
        App name: "tiktok", "instagram", "youtube", "twitter", "short-form", or "unknown"
    """
    # Try OCR-based detection first
    if OCR_AVAILABLE:
        try:
            text = pytesseract.image_to_string(im, timeout=5).lower()
            for app, keywords in KEYWORDS.items():
                if any(keyword in text for keyword in keywords):
                    return app
        except Exception:
            pass

    # Fallback: aspect ratio detection
    return "short-form" if is_vertical_video(im) else "unknown"
