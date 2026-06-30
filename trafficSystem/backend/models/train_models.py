"""
Training Script: Angkot & TransJakarta YOLOv8n Models
=====================================================
Device: MacBook Air M2 16GB (MPS acceleration)
Base model: YOLOv8n (nano — optimal for small datasets)
"""

import os
import time
import shutil
import psutil

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_memory():
    mem = psutil.virtual_memory()
    print(f"  💾 RAM: {mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB ({mem.percent}%)")

def train_model(name, data_yaml, epochs=100, batch=8, imgsz=640):
    from ultralytics import YOLO
    import torch

    print_header(f"TRAINING: {name}")
    print_memory()

    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"  🖥️  Device: {device}")
    print(f"  📊 Epochs: {epochs} | 📦 Batch: {batch} | 🖼️ ImgSz: {imgsz}")

    model = YOLO('yolov8n.pt')
    project_dir = os.path.dirname(data_yaml)

    t_start = time.time()

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        device=device,
        patience=20,
        save=True,
        save_period=25,
        project=project_dir,
        name=f'{name}_train',
        exist_ok=True,
        pretrained=True,
        optimizer='AdamW',
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        workers=4,
        verbose=True,
    )

    elapsed = time.time() - t_start
    print(f"\n  ⏱️  Training time: {elapsed/60:.1f} minutes")

    # Copy best model
    best_pt = os.path.join(project_dir, f'{name}_train', 'weights', 'best.pt')
    if os.path.exists(best_pt):
        output_path = os.path.join(MODELS_DIR, f"{name}.pt")
        shutil.copy2(best_pt, output_path)
        size_mb = os.path.getsize(output_path) / (1024**2)
        print(f"  ✅ Model saved: {output_path} ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ best.pt not found!")

    # Validate
    print(f"\n  Running validation...")
    val_results = model.val(data=data_yaml, device=device)
    print(f"  📈 mAP@50:    {val_results.box.map50:.4f}")
    print(f"  📈 mAP@50-95: {val_results.box.map:.4f}")

    return results


MODELS_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    print_header("🚐 YOLO Training Pipeline — Angkot & TransJakarta")
    print_memory()

    # 1. Train Angkot
    train_model("angkot", os.path.join(MODELS_DIR, "MOBIL.v3i.yolov8", "data.yaml"))

    # 2. Train TransJakarta
    train_model("transjakarta", os.path.join(MODELS_DIR, "tj.v1i.yolov8", "data.yaml"))

    print_header("🎉 ALL TRAINING COMPLETE")
    for f in sorted(os.listdir(MODELS_DIR)):
        if f.endswith('.pt'):
            size = os.path.getsize(os.path.join(MODELS_DIR, f)) / (1024**2)
            print(f"  • {f} ({size:.1f} MB)")
