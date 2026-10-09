"""
FILE: build_classifier_dataset.py

WHAT THIS FILE DOES
    Turns the downloaded Roboflow dataset ("FASTENER SORTER.v3i.yolov11": whole photos with a box
    drawn around each part) into the folder-per-class layout that train_yolo_classifier.py needs:
        fastener_sorter_cls/train/<CLASS>/...   val/<CLASS>/...   test/<CLASS>/...
    Run it again whenever the downloaded dataset changes:
        python build_classifier_dataset.py

MAIN PARTS
    - Part crops: every labelled part is cut out three times (tight, medium, wide), so the model also
      learns to recognise a part that does not fill the picture, as happens with a hand-held camera
    - Whole photos: photos showing a single kind of part are also used uncropped
    - NO_FASTENER class: empty patches of background plus plain frames, so the model can say
      "nothing here" instead of always naming a fastener
    - Your own photos: everything saved with the app's "Save Photo for Training" button
      (my_camera_photos/<CLASS>/) is added, so the model learns your camera, parts and lighting
"""

import argparse
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "FASTENER SORTER.v3i.yolov11"
OUTPUT_DIR = BASE_DIR / "fastener_sorter_cls"
CAMERA_PHOTOS_DIR = BASE_DIR / "my_camera_photos"

SOURCE_NAMES = ["bolt", "nut", "nuts", "rivet", "screw", "washer"]  # order used by the label files
MERGE = {"nuts": "nut"}                                              # duplicate label in the download
SPLITS = {"train": "train", "valid": "val", "test": "test"}
NO_FASTENER = "NO_FASTENER"

# How much of the surroundings each crop keeps, as a fraction of the part's size on every side
PADDINGS = {"tight": 0.08, "medium": 0.60, "wide": 1.50}
MIN_SIDE = 24            # crops smaller than this (px) are too blurry to learn from
# Background patches are only taken from the phone photos of a single part ("IMG..."): the photos of
# piles contain parts nobody labelled, which would end up inside "empty" patches
EMPTY_PATCH_SOURCE_PREFIX = "IMG"


# ============================================================================
# READING THE DOWNLOADED LABELS
# ============================================================================
def read_boxes(label_file: Path):
    """Returns [(class_name, x1, y1, x2, y2)] with coordinates as fractions of the image size."""
    boxes = []
    for line in label_file.read_text().splitlines():
        values = line.split()
        if not values:
            continue
        name = SOURCE_NAMES[int(values[0])]
        name = MERGE.get(name, name).upper()
        nums = list(map(float, values[1:]))
        if len(nums) == 4:      # box: centre x, centre y, width, height
            cx, cy, bw, bh = nums
            boxes.append((name, cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
        else:                   # outline polygon: use the box around it
            boxes.append((name, min(nums[0::2]), min(nums[1::2]), max(nums[0::2]), max(nums[1::2])))
    return boxes


# ============================================================================
# PART CROPS AND WHOLE PHOTOS
# ============================================================================
def save(image: np.ndarray, folder: Path, name: str) -> bool:
    if image.shape[0] < MIN_SIDE or image.shape[1] < MIN_SIDE:
        return False
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / name), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return True


def crop_part(image: np.ndarray, box, padding: float) -> np.ndarray:
    h, w = image.shape[:2]
    _, x1, y1, x2, y2 = box
    px, py = (x2 - x1) * padding, (y2 - y1) * padding
    left, top = max(0, int((x1 - px) * w)), max(0, int((y1 - py) * h))
    right, bottom = min(w, int((x2 + px) * w)), min(h, int((y2 + py) * h))
    return image[top:bottom, left:right]


# ============================================================================
# NO_FASTENER CLASS
# Background patches that touch no labelled part, plus plain frames.
# ============================================================================
def empty_patches(image: np.ndarray, boxes, rng: random.Random, count: int = 2):
    h, w = image.shape[:2]
    patches = []
    for _ in range(40):
        if len(patches) >= count:
            break
        side = int(rng.uniform(0.25, 0.45) * min(h, w))
        x, y = rng.randint(0, w - side), rng.randint(0, h - side)
        # Keep a margin around every part so no piece of a fastener ends up in an "empty" patch
        touches = any(x < (x2 + 0.03) * w and x + side > (x1 - 0.03) * w and
                      y < (y2 + 0.03) * h and y + side > (y1 - 0.03) * h for _, x1, y1, x2, y2 in boxes)
        if not touches:
            patches.append(image[y:y + side, x:x + side])
    return patches


def plain_frame(rng: random.Random, np_rng: np.random.Generator) -> np.ndarray:
    """An empty table / wall / dark frame: flat colour with a soft gradient and sensor noise."""
    size = 256
    colour = np.array([rng.uniform(20, 235)] * 3) + np.array([rng.uniform(-18, 18) for _ in range(3)])
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    shade = (xx * rng.uniform(-40, 40) + yy * rng.uniform(-40, 40))[..., None]
    frame = colour + shade + np_rng.normal(0, rng.uniform(1, 9), (size, size, 3))
    return np.clip(frame, 0, 255).astype(np.uint8)


# ============================================================================
# YOUR OWN CAMERA PHOTOS
# Each photo is used whole and as the centre guide box (where the part is held during live video).
# ============================================================================
def add_camera_photos(out: Path, counts: dict) -> int:
    added = 0
    if not CAMERA_PHOTOS_DIR.exists():
        return added
    for class_dir in sorted(p for p in CAMERA_PHOTOS_DIR.iterdir() if p.is_dir()):
        label = class_dir.name.upper()
        for index, photo in enumerate(sorted(class_dir.glob("*.jpg"))):
            image = cv2.imdecode(np.fromfile(str(photo), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            # Photos saved one after another look alike, so they go to the same split in groups of three;
            # one group in ten is kept for validation and one for testing
            group = (index // 3) % 10
            split = "val" if group == 8 else "test" if group == 9 else "train"
            h, w = image.shape[:2]
            box_w, box_h = int(w * 0.45), int(h * 0.50)  # same box the app draws on live video
            x, y = w // 2 - box_w // 2, h // 2 - box_h // 2
            for view, picture in (("whole", image), ("guide", image[y:y + box_h, x:x + box_w])):
                if save(picture, out / split / label, f"mycam_{photo.stem}_{view}.jpg"):
                    counts[(split, label)] = counts.get((split, label), 0) + 1
            added += 1
    return added


# ============================================================================
# RUN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="Build the classifier dataset from the Roboflow download.")
    parser.add_argument("--source", default=str(SOURCE_DIR))
    parser.add_argument("--out", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    source, out = Path(args.source), Path(args.out)

    rng, np_rng = random.Random(7), np.random.default_rng(7)
    if out.exists():
        # OneDrive or File Explorer can hold a folder open; empty folders left behind are harmless
        shutil.rmtree(out, ignore_errors=True)
        leftovers = list(out.rglob("*.jpg")) if out.exists() else []
        if leftovers:
            raise SystemExit(f"Could not clear {out}: {len(leftovers)} old images are locked. Close them and run again.")
    counts = {}

    for split_in, split_out in SPLITS.items():
        for image_file in sorted((source / split_in / "images").glob("*.jpg")):
            boxes = read_boxes(source / split_in / "labels" / f"{image_file.stem}.txt")
            if not boxes:
                continue
            image = cv2.imread(str(image_file))
            stem = image_file.stem[:40]

            for i, box in enumerate(boxes):
                for view, padding in PADDINGS.items():
                    if save(crop_part(image, box, padding), out / split_out / box[0], f"{stem}_{i:02d}_{view}.jpg"):
                        counts[(split_out, box[0])] = counts.get((split_out, box[0]), 0) + 1

            kinds = {box[0] for box in boxes}
            if len(kinds) == 1:
                kind = kinds.pop()
                save(image, out / split_out / kind, f"{stem}_whole.jpg")
                counts[(split_out, kind)] = counts.get((split_out, kind), 0) + 1

            if image_file.name.startswith(EMPTY_PATCH_SOURCE_PREFIX):
                for j, patch in enumerate(empty_patches(image, boxes, rng)):
                    if save(patch, out / split_out / NO_FASTENER, f"{stem}_empty{j}.jpg"):
                        counts[(split_out, NO_FASTENER)] = counts.get((split_out, NO_FASTENER), 0) + 1

        for k in range({"train": 60, "val": 15, "test": 10}[split_out]):
            save(plain_frame(rng, np_rng), out / split_out / NO_FASTENER, f"plain_{k:03d}.jpg")
            counts[(split_out, NO_FASTENER)] = counts.get((split_out, NO_FASTENER), 0) + 1

    own = add_camera_photos(out, counts)
    print(f"Photos from my_camera_photos/ added: {own}\n")

    classes = sorted({name for _, name in counts})
    print(f"{'':8}" + "".join(f"{c:>13}" for c in classes) + f"{'total':>9}")
    for split in ("train", "val", "test"):
        row = [counts.get((split, c), 0) for c in classes]
        print(f"{split:8}" + "".join(f"{n:>13}" for n in row) + f"{sum(row):>9}")
    print(f"\nDataset written to {out}")


if __name__ == "__main__":
    main()
