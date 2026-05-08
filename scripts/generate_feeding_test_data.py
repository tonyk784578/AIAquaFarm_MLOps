"""Generate synthetic feeding activity training data for the ResNet18 regression model.

Produces a directory of JPEG images where pixel patterns encode feeding activity
at different intensity levels, plus a labels.csv mapping each image to its
ground-truth activity score (0.0 – 1.0).

Activity encoding
-----------------
Each frame is a 224×224 RGB image simulating an overhead fish tank view:

    - Background: dark water (low intensity blue-grey).
    - Fish bodies: semi-transparent ellipses scattered around the frame.
    - Surface disturbance blobs: Gaussian noise bursts that grow with activity.
    - Visible pellets: small bright circles, count proportional to activity.

The activity score for a frame is:
    score = surface_disturbance_weight + pellet_weight + fish_motion_weight
    (all components normalised, score clipped to [0, 1])

Layout produced::

    <output>/
      train/
        activity_0.00/  <n_per_class> *.jpg
        activity_0.25/  <n_per_class> *.jpg
        activity_0.50/  <n_per_class> *.jpg
        activity_0.75/  <n_per_class> *.jpg
        activity_1.00/  <n_per_class> *.jpg
      val/
        activity_0.00/  …
        …
      labels.csv         # path,score  (paths relative to <output>)

Usage::

    python scripts/generate_feeding_test_data.py \\
        --output data/feeding_dataset/ \\
        --n-per-class 200 \\
        --val-frac 0.2 \\
        --img-size 224 \\
        --seed 42
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path

import numpy as np

# ── Constants ──────────────────────────────────────────────────────────────────
ACTIVITY_LEVELS = [0.00, 0.25, 0.50, 0.75, 1.00]
IMG_SIZE = 224

# Water background colour (BGR values as floats 0-255)
_BG_COLOR = np.array([30, 40, 50], dtype=np.float32)  # dark blue-grey

# Fish body colour
_FISH_COLOR = np.array([180, 200, 160], dtype=np.float32)

# Pellet colour
_PELLET_COLOR = np.array([220, 200, 150], dtype=np.float32)


# ── Image synthesis ────────────────────────────────────────────────────────────

def _draw_ellipse(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    color: np.ndarray,
    alpha: float = 0.6,
) -> None:
    """Blend a filled ellipse onto canvas (in-place, RGB float32)."""
    h, w = canvas.shape[:2]
    y_coords, x_coords = np.ogrid[:h, :w]
    mask = ((x_coords - cx) / max(rx, 1)) ** 2 + ((y_coords - cy) / max(ry, 1)) ** 2 <= 1.0
    canvas[mask] = canvas[mask] * (1 - alpha) + color * alpha


def _draw_circle(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    r: int,
    color: np.ndarray,
) -> None:
    """Draw a solid circle (in-place)."""
    h, w = canvas.shape[:2]
    y_coords, x_coords = np.ogrid[:h, :w]
    mask = (x_coords - cx) ** 2 + (y_coords - cy) ** 2 <= r ** 2
    canvas[mask] = color


def _gaussian_blob(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    sigma: float,
    intensity: float,
    color: np.ndarray,
) -> None:
    """Add a soft Gaussian brightness burst to simulate water surface disturbance."""
    h, w = canvas.shape[:2]
    y_coords, x_coords = np.mgrid[:h, :w]
    g = np.exp(-((x_coords - cx) ** 2 + (y_coords - cy) ** 2) / (2 * sigma ** 2))
    for c in range(3):
        canvas[:, :, c] += g * intensity * (color[c] - canvas[:, :, c].mean())


def synthesize_frame(
    activity: float,
    img_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate one synthetic feeding activity frame.

    Args:
        activity: Ground-truth activity score [0.0, 1.0].
        img_size: Square image side length in pixels.
        rng: Numpy random generator (for reproducibility).

    Returns:
        uint8 RGB array of shape (img_size, img_size, 3).
    """
    canvas = np.tile(_BG_COLOR, (img_size, img_size, 1)).astype(np.float32)

    # ── Background texture: mild Perlin-like noise ─────────────────────────────
    noise = rng.normal(0, 4, (img_size, img_size, 3)).astype(np.float32)
    canvas = np.clip(canvas + noise, 0, 255)

    # ── Fish bodies (5–12 fish) ────────────────────────────────────────────────
    n_fish = rng.integers(5, 13)
    for _ in range(n_fish):
        cx = int(rng.integers(10, img_size - 10))
        cy = int(rng.integers(10, img_size - 10))
        rx = int(rng.integers(8, 18))
        ry = int(rng.integers(4, 10))
        angle_jitter = rng.normal(0, activity * 3)  # more scattered at high activity
        # simple axis-aligned ellipses (rotation omitted for speed)
        alpha = rng.uniform(0.3, 0.7)
        fish_col = _FISH_COLOR + rng.normal(0, 10, 3)
        _draw_ellipse(canvas, cx, cy, rx, ry, np.clip(fish_col, 0, 255), alpha)

    # ── Surface disturbance blobs (activity-driven) ────────────────────────────
    n_blobs = int(activity * 8) + int(rng.uniform(0, 2))
    for _ in range(n_blobs):
        cx = int(rng.integers(0, img_size))
        cy = int(rng.integers(0, img_size))
        sigma = rng.uniform(8, 20 + activity * 15)
        intensity = rng.uniform(0.3, 0.8) * activity
        blob_color = np.array([
            rng.uniform(150, 220),
            rng.uniform(180, 230),
            rng.uniform(200, 255),
        ], dtype=np.float32)
        _gaussian_blob(canvas, cx, cy, sigma, intensity, blob_color)

    # ── Visible pellets (bright dots) ─────────────────────────────────────────
    n_pellets = int(activity * 12) + rng.integers(0, 3)
    for _ in range(n_pellets):
        cx = int(rng.integers(5, img_size - 5))
        cy = int(rng.integers(5, img_size - 5))
        r = int(rng.integers(2, 5))
        pellet = np.clip(_PELLET_COLOR + rng.normal(0, 15, 3), 0, 255)
        _draw_circle(canvas, cx, cy, r, pellet)

    # ── Global brightness boost at high activity (agitation stirs sediment) ────
    canvas = canvas + activity * rng.uniform(0, 15)

    return np.clip(canvas, 0, 255).astype(np.uint8)


# ── Dataset builder ────────────────────────────────────────────────────────────

def _save_jpeg(arr: np.ndarray, path: Path, quality: int = 85) -> None:
    """Save a uint8 RGB numpy array as JPEG without requiring cv2.

    Falls back to writing a raw PPM if Pillow is unavailable.
    """
    try:
        from PIL import Image
        Image.fromarray(arr).save(path, format="JPEG", quality=quality)
    except ImportError:
        # PPM fallback (no external deps)
        h, w = arr.shape[:2]
        ppm_path = path.with_suffix(".ppm")
        with open(ppm_path, "wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode())
            f.write(arr.tobytes())
        # rename to .jpg so training script finds it
        ppm_path.rename(path)


def generate(
    output_dir: str,
    n_per_class: int = 200,
    val_frac: float = 0.2,
    img_size: int = IMG_SIZE,
    seed: int = 42,
) -> None:
    """Generate the full feeding activity dataset.

    Args:
        output_dir: Root directory for the dataset.
        n_per_class: Images per activity level per split.
        val_frac: Fraction of images reserved for validation.
        img_size: Square image dimension.
        seed: Random seed for reproducibility.
    """
    rng = np.random.default_rng(seed)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    label_rows: list[dict[str, str]] = []
    n_val = max(1, int(n_per_class * val_frac))
    n_train = n_per_class - n_val

    for split, count in [("train", n_train), ("val", n_val)]:
        for score in ACTIVITY_LEVELS:
            label = f"activity_{score:.2f}"
            class_dir = root / split / label
            class_dir.mkdir(parents=True, exist_ok=True)

            for i in range(count):
                # Add Gaussian noise around the target score for realism
                noisy_score = float(np.clip(rng.normal(score, 0.05), 0.0, 1.0))
                img = synthesize_frame(noisy_score, img_size, rng)
                fname = f"{label}_{i:04d}.jpg"
                fpath = class_dir / fname
                _save_jpeg(img, fpath)
                label_rows.append({
                    "path": str(fpath.relative_to(root)),
                    "score": f"{noisy_score:.4f}",
                })

        print(f"  [{split}] {count} images per class × {len(ACTIVITY_LEVELS)} levels = "
              f"{count * len(ACTIVITY_LEVELS)} images")

    # Write labels.csv
    labels_path = root / "labels.csv"
    with open(labels_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "score"])
        writer.writeheader()
        writer.writerows(label_rows)

    total = len(label_rows)
    print(f"\nDataset written to: {root.resolve()}")
    print(f"Total images : {total}")
    print(f"labels.csv   : {labels_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic feeding activity image dataset"
    )
    parser.add_argument(
        "--output", default="data/feeding_dataset/",
        help="Root output directory (default: data/feeding_dataset/)",
    )
    parser.add_argument(
        "--n-per-class", type=int, default=200,
        help="Images per activity level per split (default: 200)",
    )
    parser.add_argument(
        "--val-frac", type=float, default=0.2,
        help="Validation fraction (default: 0.2)",
    )
    parser.add_argument(
        "--img-size", type=int, default=IMG_SIZE,
        help=f"Square image size in pixels (default: {IMG_SIZE})",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    print(f"Generating feeding dataset → {args.output}")
    print(f"  {args.n_per_class} images/class, val_frac={args.val_frac}, "
          f"img_size={args.img_size}, seed={args.seed}\n")
    generate(
        output_dir=args.output,
        n_per_class=args.n_per_class,
        val_frac=args.val_frac,
        img_size=args.img_size,
        seed=args.seed,
    )
