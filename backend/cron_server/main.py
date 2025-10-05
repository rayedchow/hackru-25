import json
import base64
import numpy as np
from PIL import Image
from io import BytesIO
from collections import defaultdict
from pathlib import Path
from typing import List, Dict
from scipy.fftpack import dct
from graph import upsert_content
from community import summarize_and_index_communities

# Configuration
CONTENT_QUEUE_PATH = Path(__file__).parent.parent / "database" / "content_queue.json"
OUTPUT_PATH = Path(__file__).parent.parent / "database" / "representative_images.json"
MIN_IMAGES_FOR_DEDUP = 3  # Only deduplicate groups with at least this many images
TARGET_REPRESENTATIVES = 5  # Target number of representative images per group
SIMILARITY_THRESHOLD = (
    8  # Hamming distance threshold (lower = more similar, 0-64 range)
)


def compute_perceptual_hash(image_b64: str, hash_size: int = 8) -> int:
    try:
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(BytesIO(image_bytes)).convert("L")
        img_size = hash_size * 4
        image = image.resize((img_size, img_size), Image.Resampling.LANCZOS)
        pixels = np.asarray(image, dtype=np.float32)
        dct_coeffs = dct(dct(pixels, axis=0, norm="ortho"), axis=1, norm="ortho")
        dct_low_freq = dct_coeffs[:hash_size, :hash_size]
        median = np.median(dct_low_freq)
        binary_hash = dct_low_freq > median
        hash_int = 0
        for i in range(hash_size):
            for j in range(hash_size):
                if binary_hash[i, j]:
                    hash_int |= 1 << (i * hash_size + j)
        return hash_int
    except Exception:
        return 0


def hamming_distance(hash1: int, hash2: int) -> int:
    return bin(hash1 ^ hash2).count("1")


def greedy_maximal_diversity_sampling(
    entries: List[Dict], hashes: List[int], k: int, similarity_threshold: int = 8
) -> List[Dict]:
    n = len(entries)
    if n <= k:
        return entries

    selected_indices = []
    remaining_indices = set(range(n))

    max_total_distance = -1
    best_start_idx = 0

    for i in range(n):
        total_distance = sum(
            hamming_distance(hashes[i], hashes[j]) for j in range(n) if i != j
        )
        if total_distance > max_total_distance:
            max_total_distance = total_distance
            best_start_idx = i

    selected_indices.append(best_start_idx)
    remaining_indices.remove(best_start_idx)

    for iteration in range(1, k):
        if not remaining_indices:
            break

        max_min_distance = -1
        best_idx = None

        for idx in remaining_indices:
            min_distance = min(
                hamming_distance(hashes[idx], hashes[sel_idx])
                for sel_idx in selected_indices
            )

            if min_distance > max_min_distance:
                max_min_distance = min_distance
                best_idx = idx

        if max_min_distance < similarity_threshold:
            break

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

    return [entries[idx] for idx in selected_indices]


def analyze_content_groups():
    try:
        with open(CONTENT_QUEUE_PATH, "r") as f:
            all_entries = json.load(f)
        with open(CONTENT_QUEUE_PATH, "w") as f:
            json.dump([], f, indent=2)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    print(f"Analyzing {len(all_entries)} content groups")

    groups = defaultdict(list)
    for entry in all_entries:
        content_id = entry.get("content_id")
        if content_id:
            groups[content_id].append(entry)

    results = {}
    total_original = 0
    total_representatives = 0

    for content_id, entries in sorted(
        groups.items(), key=lambda x: len(x[1]), reverse=True
    ):
        group_size = len(entries)
        total_original += group_size

        if group_size < MIN_IMAGES_FOR_DEDUP:
            results[content_id] = {
                "total_images": group_size,
                "representatives": entries,
                "reduction_ratio": 1.0,
            }
            total_representatives += group_size

            # Convert base64 images to RGB PIL images
            rgb_images = []
            for entry in entries:
                try:
                    image_bytes = base64.b64decode(entry["image"])
                    image = Image.open(BytesIO(image_bytes)).convert("RGB")
                    rgb_images.append(image)
                except Exception:
                    pass

            if rgb_images:
                upsert_content(rgb_images, content_id)
            continue

        hashes = [compute_perceptual_hash(entry["image"]) for entry in entries]

        distances = []
        for i in range(len(hashes)):
            for j in range(i + 1, len(hashes)):
                distances.append(hamming_distance(hashes[i], hashes[j]))

        avg_distance = np.mean(distances) if distances else 0
        min_distance = np.min(distances) if distances else 0
        max_distance = np.max(distances) if distances else 0

        k = min(TARGET_REPRESENTATIVES, group_size)
        representatives = greedy_maximal_diversity_sampling(
            entries, hashes, k, SIMILARITY_THRESHOLD
        )

        total_representatives += len(representatives)
        reduction_ratio = len(representatives) / group_size

        results[content_id] = {
            "total_images": group_size,
            "representatives": representatives,
            "reduction_ratio": reduction_ratio,
            "similarity_stats": {
                "avg_distance": float(avg_distance),
                "min_distance": int(min_distance),
                "max_distance": int(max_distance),
            },
        }

        # Convert base64 images to RGB PIL images
        rgb_images = []
        for rep in representatives:
            try:
                image_bytes = base64.b64decode(rep["image"])
                image = Image.open(BytesIO(image_bytes)).convert("RGB")
                rgb_images.append(image)
            except Exception:
                pass

        if rgb_images:
            upsert_content(rgb_images, content_id)

    output_data = {
        "metadata": {
            "total_original_images": total_original,
            "total_representative_images": total_representatives,
            "overall_reduction_ratio": total_representatives / total_original
            if total_original > 0
            else 1.0,
            "num_groups": len(groups),
        },
        "groups": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2)


if __name__ == "__main__":
    analyze_content_groups()
    summarize_and_index_communities()
