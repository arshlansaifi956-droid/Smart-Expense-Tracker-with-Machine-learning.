import os
import sys
import numpy as np

# Set flags BEFORE importing paddle
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_new_ir_api"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"

from dashboard.ocr_engine import ReceiptOCR
from PIL import Image

def fast_test():
    engine = ReceiptOCR()
    image_path = os.path.join('media', 'receipts', 'Screenshot_2026-04-26_171848.png')
    
    # Simple single-variant OCR
    print(f"--- Fast Testing OCR on {image_path} ---")
    pil = Image.open(image_path).convert("RGB")
    lines = engine._run_paddle(np.array(pil))
    
    print("\n--- Detected Lines ---")
    for i, (text, conf) in enumerate(lines):
        print(f"{i}: {text} ({conf:.2f})")
    
    # Just text extraction
    merged = [t for t, c in lines]
    data = engine.extractor.extract(merged)
    
    print("\n--- Extraction Results ---")
    print(f"Merchant: {data.merchant}")
    print(f"Total: {data.total}")
    print(f"Subtotal: {data.subtotal}")
    print(f"Tax: {data.tax}")
    print(f"Date: {data.date}")
    print(f"Warnings: {data.warnings}")

if __name__ == "__main__":
    fast_test()
