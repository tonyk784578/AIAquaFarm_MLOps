"""Generate synthetic fish growth detection dataset in YOLO v8 format.

Creates annotated overhead-tank images where fish are represented as
elliptical shapes with realistic size variation. Bounding boxes are
exported in YOLO normalised format (cls cx cy w h).

Image simulation
----------------
Each 640×640 RGB frame contains:
  - Dark water background with mild texture noise.
  - 2–15 fish per frame, drawn as semi-transparent ellipses.
  - Fish sizes sampled from a normal distribution (mean/std configurable)
    to simulate different growth stages.
  - Random partial occlusion at tank walls (fish cut off at edges).
  - Mild motion blur kernel applied at high fish-count frames.

YOLO label format (one .txt per image)::

    0 cx cy w h      (all values normalised to [0, 1])

data.yaml is written at the root so YOLOv8 can consume the dataset
directly::

    train: images/train
    val:   images/val
    nc:    1
    names: ['fish']

Usage::

    python scripts/generate_growth_test_data.py \\
        --output data/growth_dataset/ \\
        --n-train 800 \\
        --n-val 200 \\
        --img-size 640 \\
        --seed 42

Requirements: numpy only (Pillow optional for JPEG output).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

# ── Appearance constants ───────────────────────────────────────────────────────
IMG_SIZE = 640
YOLO_CLASS_ID = 0  # single class: fish

_BG_BASE = np.array([25, 35, 45], dtype=np.float32)       # dark water
_FISH_BASE = np.array([170, 200, 155], dtype=np.float32)   # greenish fish body
_SHADOW_BASE = np.array([15, 20, 30], dtype=np.float32)    # fish shadow

# Fish body size distribution (semi-axis lengths in pixels, 640px image)
_RX_MEAN, _RX_STD = 28, 8    # horizontal semi-axis (length)
_RY_MEAN, _RY_STD = 12, 4    # vertical semi-axis (width)
_RX_MIN, _RX_MAX = 10, 60
_RY_MIN, _RY_MAX = 5, 28


# ── Drawing helpers ────────────────────────────────────────────────────────────

def _ellipse_mask(
    h: int, w: int, cx: float, cy: float, rx: float, ry: float, angle: float,
) -> np.ndarray:
    """Return boolean mask for a rotated ellipse."""
    y_idx, x_idx = np.mgrid[:h, :w]
    dx = (x_idx - cx) * math.cos(angle) + (y_idx - cy) * math.sin(angle)
    dy = -(x_idx - cx) * math.sin(angle) + (y_idx - cy) * math.cos(angle)
    return (dx / max(rx, 1)) ** 2 + (dy / max(ry, 1)) ** 2 <= 1.0


def _draw_fish(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    angle: float,
    color: np.ndarray,
    rng: np.random.Generator,
) -> None:
    """Blend a rotated ellipse fish body onto the canvas."""
    h, w = canvas.shape[:2]
    mask = _ellipse_mask(h, w, cx, cy, rx, ry, angle)
    alpha = rng.uniform(0.55, 0.85)
    # slight colour jitter per fish
    jitter = rng.normal(0, 12, 3)
    col = np.clip(color + jitter, 0, 255)
    canvas[mask] = canvas[mask] * (1 - alpha) + col * alpha

    # fish eye: small dark dot
    ex = cx + math.cos(angle) * rx * 0.6
    ey = cy + math.sin(angle) * rx * 0.6
    eye_mask = _ellipse_mask(h, w, ex, ey, max(rx * 0.08, 2), max(ry * 0.1, 2), angle)
    canvas[eye_mask] = np.array([20, 20, 20], dtype=np.float32)

    # tail fin: smaller ellipse at the rear
    tx = cx - math.cos(angle) * rx * 0.85
    ty = cy - math.sin(angle) * rx * 0.85
    tail_mask = _ellipse_mask(h, w, tx, ty, rx * 0.3, ry * 0.8, angle + math.pi / 6)
    tail_col = np.clip(color * 0.7 + jitter, 0, 255)
    canvas[tail_mask] = canvas[tail_mask] * 0.5 + tail_col * 0.5


def _motion_blur(canvas: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Apply a simple horizontal motion blur (box filter)."""
    out = canvas.copy()
    k = kernel_size
    for c in range(3):
        padded = np.pad(out[:, :, c], ((0, 0), (k // 2, k // 2)), mode="edge")
        out[:, :, c] = np.stack(
            [padded[:, i : canvas.shape[1] + i] for i in range(k)], axis=0
        ).mean(axis=0)
    return out


# ── Frame + label synthesis ────────────────────────────────────────────────────

def synthesize_frame_and_boxes(
    img_size: int,
    rng: np.random.Generator,
    min_fish: int = 2,
    max_fish: int = 15,
) -> tuple[np.ndarray, list[tuple[float, float, float, float]]]:
    """Generate one synthetic frame and its fish bounding boxes.

    Args:
        img_size: Square image dimension.
        rng: Numpy random generator.
        min_fish: Minimum fish per frame.
        max_fish: Maximum fish per frame.

    Returns:
        Tuple of:
            - uint8 RGB canvas (img_size × img_size × 3)
            - List of YOLO boxes (cx_norm, cy_norm, w_norm, h_norm)
    """
    h = w = img_size
    canvas = np.tile(_BG_BASE, (h, w, 1)).astype(np.float32)

    # ── Background texture ─────────────────────────────────────────────────────
    canvas += rng.normal(0, 5, (h, w, 3))

    # ── Subtle grid lines (tank walls / grid overlay) ─────────────────────────
    step = img_size // 8
    for line in range(0, h, step):
        canvas[max(0, line - 1) : line + 1, :] = np.clip(
            canvas[max(0, line - 1) : line + 1, :] + 8, 0, 255
        )
        canvas[:, max(0, line - 1) : line + 1] = np.clip(
            canvas[:, max(0, line - 1) : line + 1] + 8, 0, 255
        )

    n_fish = int(rng.integers(min_fish, max_fish + 1))
    boxes: list[tuple[float, float, float, float]] = []

    for _ in range(n_fish):
        rx = float(np.clip(rng.normal(_RX_MEAN, _RX_STD), _RX_MIN, _RX_MAX))
        ry = float(np.clip(rng.normal(_RY_MEAN, _RY_STD), _RY_MIN, _RY_MAX))
        angle = float(rng.uniform(0, math.pi))

        # Allow fish to be partially cut off at edges (realistic)
        cx = float(rng.uniform(-rx * 0.3, w + rx * 0.3))
        cy = float(rng.uniform(-ry * 0.3, h + ry * 0.3))

        fish_col = _FISH_BASE + rng.normal(0, 15, 3)
        _draw_fish(canvas, cx, cy, rx, ry, angle, fish_col, rng)

        # YOLO bounding box — axis-aligned, clipped to image
        # Rotated ellipse AABB approximation
        bb_rx = math.sqrt((rx * math.cos(angle)) ** 2 + (ry * math.sin(angle)) ** 2)
        bb_ry = math.sqrt((rx * math.sin(angle)) ** 2 + (ry * math.cos(angle)) ** 2)

        x1 = max(0.0, cx - bb_rx) / w
        y1 = max(0.0, cy - bb_ry) / h
        x2 = min(float(w), cx + bb_rx) / w
        y2 = min(float(h), cy + bb_ry) / h

        bw = x2 - x1
        bh = y2 - y1
        if bw > 0.01 and bh > 0.01:  # skip degenerate boxes
            boxes.append((
                (x1 + x2) / 2,   # cx
                (y1 + y2) / 2,   # cy
                bw,
                bh,
            ))

    # Apply motion blur when many fish are present (simulates swimming)
    if n_fish > 8:
        canvas = _motion_blur(canvas, kernel_size=int(rng.integers(3, 7)))

    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    return canvas, boxes


def _save_jpeg(arr: np.ndarray, path: Path, quality: int = 90) -> None:
    """Save RGB array as JPEG (Pillow) or PPM fallback."""
    try:
        from PIL import Image
        Image.fromarray(arr).save(path, format="JPEG", quality=quality)
    except ImportError:
        h, w = arr.shape[:2]
        ppm = path.with_suffix(".ppm")
        with open(ppm, "wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode())
            f.write(arr.tobytes())
        ppm.rename(path)


def _write_yolo_label(boxes: list[tuple[float, float, float, float]], path: Path) -> None:
    """Write YOLO-format label file (one box per line)."""
    with open(path, "w") as f:
        for cx, cy, bw, bh in boxes:
            f.write(f"{YOLO_CLASS_ID} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")


def _write_data_yaml(root: Path, img_size: int) -> None:
    """Write data.yaml for YOLOv8."""
    content = (
        f"path: {root.resolve()}\n"
        "train: images/train\n"
        "val:   images/val\n"
        "\n"
        "nc: 1\n"
        "names: ['fish']\n"
        "\n"
        f"# Generated by scripts/generate_growth_test_data.py\n"
        f"# img_size: {img_size}\n"
    )
    (root / "data.yaml").write_text(content)


# ── Main generator ─────────────────────────────────────────────────────────────

def generate(
    output_dir: str,
    n_train: int = 800,
    n_val: int = 200,
    img_size: int = IMG_SIZE,
    min_fish: int = 2,
    max_fish: int = 15,
    seed: int = 42,
) -> None:
    """Generate YOLO-format fish detection dataset.

    Args:
        output_dir: Root directory; images/ and labels/ are created inside.
        n_train: Number of training frames.
        n_val: Number of validation frames.
        img_size: Square image size in pixels.
        min_fish: Minimum fish per frame.
        max_fish: Maximum fish per frame.
        seed: Random seed.
    """
    rng = np.random.default_rng(seed)
    root = Path(output_dir)

    for split, count in [("train", n_train), ("val", n_val)]:
        img_dir = root / "images" / split
        lbl_dir = root / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        total_boxes = 0
        for i in range(count):
            canvas, boxes = synthesize_frame_and_boxes(img_size, rng, min_fish, max_fish)
            fname = f"frame_{i:05d}"
            _save_jpeg(canvas, img_dir / f"{fname}.jpg")
            _write_yolo_label(boxes, lbl_dir / f"{fname}.txt")
            total_boxes += len(boxes)

        avg_fish = total_boxes / max(count, 1)
        print(f"  [{split}] {count} images, avg {avg_fish:.1f} fish/frame → {img_dir}")

    _write_data_yaml(root, img_size)
    print(f"\nDataset written to: {root.resolve()}")
    print(f"data.yaml         : {root / 'data.yaml'}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic fish growth detection dataset (YOLO v8 format)"
    )
    parser.add_argument(
        "--output", default="data/growth_dataset/",
        help="Root output directory (default: data/growth_dataset/)",
    )
    parser.add_argument(
        "--n-train", type=int, default=800,
        help="Number of training frames (default: 800)",
    )
    parser.add_argument(
        "--n-val", type=int, default=200,
        help="Number of validation frames (default: 200)",
    )
    parser.add_argument(
        "--img-size", type=int, default=IMG_SIZE,
        help=f"Square image size (default: {IMG_SIZE})",
    )
    parser.add_argument(
        "--min-fish", type=int, default=2,
        help="Minimum fish per frame (default: 2)",
    )
    parser.add_argument(
        "--max-fish", type=int, default=15,
        help="Maximum fish per frame (default: 15)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    print(f"Generating growth dataset → {args.output}")
    print(f"  train={args.n_train}, val={args.n_val}, "
          f"img_size={args.img_size}, fish=[{args.min_fish},{args.max_fish}], "
          f"seed={args.seed}\n")
    generate(
        output_dir=args.output,
        n_train=args.n_train,
        n_val=args.n_val,
        img_size=args.img_size,
        min_fish=args.min_fish,
        max_fish=args.max_fish,
        seed=args.seed,
    )
