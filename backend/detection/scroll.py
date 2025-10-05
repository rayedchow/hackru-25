"""
Scroll detection using perceptual hashing.
Detects when user scrolls to new content by comparing visual similarity.
"""

from PIL import Image


def phash64(im: Image.Image) -> int:
    """
    Compute 64-bit perceptual hash of an image.
    Similar images have similar hashes.
    """
    small = im.convert("L").resize((8, 8))
    pix = list(small.getdata())
    avg = sum(pix) / 64.0
    h = 0
    for i, p in enumerate(pix):
        if p > avg:
            h |= 1 << i
    return h


def hamming_distance(a: int, b: int) -> int:
    """Count number of differing bits between two integers."""
    x = a ^ b
    count = 0
    while x:
        count += x & 1
        x >>= 1
    return count


def detect_scroll(
    current_image: Image.Image, previous_hash: int | None
) -> tuple[bool, int]:
    """
    Detect if content changed (scroll occurred).

    Args:
        current_image: Current frame to analyze
        previous_hash: Hash of previous frame (None if first frame)

    Returns:
        (did_scroll, current_hash): Whether scroll detected and current frame's hash
    """
    current_hash = phash64(current_image)

    if previous_hash is None:
        return (False, current_hash)

    # Calculate visual difference
    distance = hamming_distance(previous_hash, current_hash)

    # Scroll detected if change is significant but not extreme
    # Higher threshold to avoid false positives from video motion
    # Actual scrolling causes major layout changes (25-40 bit difference)
    # Video motion typically causes smaller changes (< 25 bits)
    did_scroll = 20 <= distance <= 40

    return (did_scroll, current_hash)
