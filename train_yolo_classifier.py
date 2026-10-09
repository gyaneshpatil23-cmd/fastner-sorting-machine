"""
FILE: train_yolo_classifier.py

WHAT THIS FILE DOES
    Trains the YOLO11n-cls model that recognises the fastener type from a picture, then tests it
    and saves the finished model where the app looks for it. Run it whenever the dataset changes:
        python train_yolo_classifier.py
    Training runs on the CPU. The app itself never trains; it only loads the saved model.

MAIN PARTS
    - Train: start from the pretrained yolo11n-cls weights and train on <dataset>/train, checking on <dataset>/val
    - Save: copy the best weights to models/fastener_yolo11n_cls.pt and the class list next to it
    - Test: accuracy, per-class precision / recall / F1 and the confusion matrix on <dataset>/test

DATASET LAYOUT EXPECTED
    <dataset>/train/<CLASS>/*.jpg    <dataset>/val/<CLASS>/*.jpg    <dataset>/test/<CLASS>/*.jpg
"""

import argparse
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "training_runs"
MODELS_DIR = BASE_DIR / "models"
MODEL_FILE = MODELS_DIR / "fastener_yolo11n_cls.pt"
REPORT_FILE = MODELS_DIR / "fastener_yolo11n_cls_report.txt"
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


# ============================================================================
# TRAIN
# Fine-tune the pretrained YOLO11n classification model on the fastener images.
# ============================================================================
def train(dataset: Path, epochs: int, imgsz: int) -> Path:
    from ultralytics import YOLO

    RUNS_DIR.mkdir(exist_ok=True)
    model = YOLO(str(RUNS_DIR / "yolo11n-cls.pt"))  # downloaded on first use
    model.train(
        data=str(dataset),
        epochs=epochs,
        imgsz=imgsz,
        batch=32,
        device="cpu",
        workers=0,           # worker processes are unreliable on Windows
        project=str(RUNS_DIR),
        name="fastener_cls",
        exist_ok=True,
        # A fastener can lie at any angle, so flips in both directions are valid training variety
        fliplr=0.5,
        flipud=0.5,
        plots=False,
        verbose=False,
    )
    return RUNS_DIR / "fastener_cls" / "weights" / "best.pt"


# ============================================================================
# TEST
# Score the saved model on images it has never seen (the test split).
# ============================================================================
def evaluate(model_path: Path, dataset: Path, split: str, imgsz: int) -> str:
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    names = [model.names[i] for i in sorted(model.names)]
    matrix = [[0] * len(names) for _ in names]  # rows = true class, columns = predicted class

    for true_idx, name in enumerate(names):
        files = [str(p) for p in sorted((dataset / split / name).glob("*")) if p.suffix.lower() in IMAGE_TYPES]
        for start in range(0, len(files), 64):
            for result in model.predict(files[start:start + 64], imgsz=imgsz, device="cpu", verbose=False):
                matrix[true_idx][int(result.probs.top1)] += 1

    total = sum(map(sum, matrix))
    correct = sum(matrix[i][i] for i in range(len(names)))
    lines = [f"Split: {split}   Images: {total}   Accuracy: {correct}/{total} = {correct / max(1, total):.1%}", "",
             f"{'class':13}{'precision':>10}{'recall':>10}{'F1':>8}{'images':>8}"]
    for i, name in enumerate(names):
        predicted = sum(row[i] for row in matrix)
        actual = sum(matrix[i])
        precision = matrix[i][i] / predicted if predicted else 0.0
        recall = matrix[i][i] / actual if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        lines.append(f"{name:13}{precision:>10.2f}{recall:>10.2f}{f1:>8.2f}{actual:>8}")

    lines += ["", "Confusion matrix (rows = true class, columns = predicted class)",
              " " * 13 + "".join(f"{n:>13}" for n in names)]
    lines += [f"{name:13}" + "".join(f"{v:>13}" for v in matrix[i]) for i, name in enumerate(names)]
    return "\n".join(lines)


# ============================================================================
# RUN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="Train and test the YOLO11n fastener classifier.")
    parser.add_argument("--data", default=str(BASE_DIR / "fastener_sorter_cls"), help="dataset folder")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--test-only", action="store_true", help="skip training and only test the saved model")
    args = parser.parse_args()
    dataset = Path(args.data).resolve()

    if not args.test_only:
        best = train(dataset, args.epochs, args.imgsz)
        MODELS_DIR.mkdir(exist_ok=True)
        shutil.copyfile(best, MODEL_FILE)

        from ultralytics import YOLO
        names = YOLO(str(MODEL_FILE)).names
        MODEL_FILE.with_suffix(".json").write_text(
            json.dumps({"classes": [names[i] for i in sorted(names)], "imgsz": args.imgsz}, indent=2)
        )
        print(f"\nModel saved to {MODEL_FILE}")

    report = "\n\n".join(evaluate(MODEL_FILE, dataset, split, args.imgsz) for split in ("val", "test"))
    REPORT_FILE.write_text(f"Dataset: {dataset.name}\n\n{report}\n")
    print("\n" + report)


if __name__ == "__main__":
    main()
