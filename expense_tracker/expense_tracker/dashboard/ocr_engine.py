"""
Receipt OCR Engine — PaddleOCR + Fuzzy Logic Extraction
Robust multi-pass extraction with confidence scoring
"""

import re
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from rapidfuzz import fuzz, process
from dataclasses import dataclass, field
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  FUZZY FIELD ANCHORS — multilingual friendly
# ─────────────────────────────────────────────
FIELD_ANCHORS = {
    "merchant": [
        "store", "shop", "restaurant", "hotel", "mart", "cafe", "bakery",
        "pharmacy", "supermarket", "outlet", "branch", "pvt ltd", "inc",
        "llc", "co.", "foods", "traders", "enterprises", "services",
        "sweets", "bakes", "junction", "medical", "hospital", "clinic",
    ],
    "date": [
        "date", "dated", "invoice date", "bill date", "transaction date",
        "purchase date", "receipt date", "dt", "दिनांक", "তারিখ",
    ],
    "time": [
        "time", "at", "clock", "hh:mm", "hrs", "समय",
    ],
    "total": [
        "total", "grand total", "amount due", "net total", "payable",
        "total amount", "total payable", "balance due", "net payable",
        "subtotal", "कुल", "সর্বমোট", "total due", "amount payable",
        "total bill", "bill total",
    ],
    "subtotal": [
        "subtotal", "sub total", "sub-total", "before tax", "net amount",
        "taxable amount", "taxable total",
    ],
    "tax": [
        "tax", "vat", "gst", "cgst", "sgst", "igst", "hst", "pst", "qst",
        "service tax", "sales tax", "tax amount", "कर", "cess",
    ],
    "discount": [
        "discount", "offer", "savings", "promo", "coupon", "rebate",
        "deduction", "off", "छूट",
    ],
    "payment_method": [
        "cash", "card", "credit card", "debit card", "upi", "gpay",
        "phonepe", "paytm", "neft", "rtgs", "net banking", "wallet",
        "visa", "mastercard", "rupay", "amex",
    ],
    "invoice_no": [
        "invoice", "invoice no", "invoice #", "receipt no", "receipt #",
        "bill no", "bill #", "order no", "order #", "txn id", "transaction id",
        "ref no", "reference", "voucher", "चालान", "বিল नं",
    ],
    "cashier": [
        "cashier", "served by", "operator", "staff", "teller", "attendant",
        "emp id", "employee",
    ],
    "phone": [
        "phone", "tel", "mobile", "contact", "call", "फोन",
    ],
    "address": [
        "address", "addr", "location", "पता", "ঠিকানা",
    ],
}

# ─────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────
@dataclass
class LineItem:
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    confidence: float = 0.0


@dataclass
class ReceiptData:
    raw_text: str = ""
    merchant: str = ""
    address: str = ""
    phone: str = ""
    date: str = ""
    time: str = ""
    invoice_no: str = ""
    cashier: str = ""
    payment_method: str = ""
    line_items: list = field(default_factory=list)
    subtotal: str = ""
    discount: str = ""
    tax: str = ""
    total: str = ""
    confidence_scores: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ─────────────────────────────────────────────
#  IMAGE PREPROCESSING PIPELINE
# ─────────────────────────────────────────────
class ImagePreprocessor:
    """Multi-strategy image enhancement for noisy receipt images."""

    @staticmethod
    def deskew(img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        gray = cv2.bitwise_not(gray)
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) < 10:
            return img
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) > 30:
            return img
        (h, w) = img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def enhance_pil(img_path: str) -> list:
        """Return multiple enhancement variants for best OCR."""
        variants = []
        try:
            pil = Image.open(img_path).convert("RGB")
            # Variant 1: Original (upscaled to optimized 1500px)
            w, h = pil.size
            scale = max(1, 1500 // max(w, h))
            if scale > 1:
                pil = pil.resize((w * scale, h * scale), Image.LANCZOS)
            variants.append(np.array(pil))

            # Variant 2: Grayscale + high contrast (Good for faded receipts)
            gray = pil.convert("L")
            enhanced = ImageEnhance.Contrast(gray).enhance(2.5)
            enhanced = ImageEnhance.Sharpness(enhanced).enhance(2.0)
            variants.append(np.array(enhanced.convert("RGB")))

            # We skip heavy thresholding/deskewing to save time unless requested
        except Exception as e:
            logger.warning(f"Preprocessing error: {e}")
        return variants


# ─────────────────────────────────────────────
#  FUZZY FIELD EXTRACTOR
# ─────────────────────────────────────────────
class FuzzyExtractor:
    """Fuzzy-logic field extraction with confidence scoring."""

    MONEY_RE = re.compile(
        r"""
        (?:Rs\.?|₹|INR|USD|\$|EUR|€|GBP|£|AED|SAR|MYR|SGD|AUD|CAD)?
        \s*
        (\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?)
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    DATE_RE = re.compile(
        r"""
        (?:
            \d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}   # DD/MM/YYYY
          | \d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}      # YYYY-MM-DD
          | \d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4}
          | (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}
        )
        """,
        re.VERBOSE | re.IGNORECASE,
    )
    TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b")
    PHONE_RE = re.compile(
        r"""
        (?:\+?\d{1,3}[\s\-]?)?
        (?:\(?\d{3,5}\)?[\s\-]?)
        \d{3,4}[\s\-]?\d{3,4}
        """,
        re.VERBOSE,
    )
    INVOICE_RE = re.compile(
        r"(?:invoice|bill|receipt|order|txn|ref|voucher)[^\d]*#?\s*([A-Z0-9\-\/]+)",
        re.IGNORECASE,
    )
    QTY_PRICE_RE = re.compile(
        r"""
        (.+?)\s+
        (?:(\d+(?:\.\d+)?)\s*[xX@]\s*)?
        ([\d,]+\.?\d*)\s*$
        """,
        re.VERBOSE,
    )

    def __init__(self, threshold: int = 72):
        self.threshold = threshold

    def _fuzzy_match_field(self, line: str, anchors: list) -> tuple[bool, int]:
        """Returns (matched, score) using token_set_ratio for robustness."""
        line_lower = line.lower().strip()
        result = process.extractOne(
            line_lower, anchors,
            scorer=fuzz.token_set_ratio
        )
        if result and result[1] >= self.threshold:
            return True, result[1]
        # Also try partial ratio for short labels
        for anchor in anchors:
            if anchor in line_lower:
                return True, 100
        return False, 0

    def _extract_money(self, text: str) -> Optional[str]:
        # Filter out common false positives
        text_upper = text.upper()
        if any(x in text_upper for x in ["PH", "GST", "BILL", "NO:", "DATE", "TEL", "PIN", "QTY", "ITEM"]):
            return None

        matches = self.MONEY_RE.findall(text)
        if matches:
            valid_matches = []
            for m in matches:
                # Reliability check: does it contain letters? (e.g. 14C.00)
                # We allow currency symbols but not middle-string letters
                clean = re.sub(r"[^\d\.]", "", m)
                if not clean: continue
                
                try:
                    f_val = float(clean)
                    if 2010 <= f_val <= 2030 and "." not in m: continue
                    if len(clean) > 5 and "." not in m: continue
                    
                    # Score based on cleanliness (no letters is better)
                    reliability = 1.0
                    if any(c.isalpha() for c in m):
                        reliability = 0.5
                    
                    valid_matches.append((clean, reliability))
                except:
                    continue
            
            if valid_matches:
                # Return the most reliable (cleanest) and then largest
                best = max(valid_matches, key=lambda x: (x[1], float(x[0])))
                return best[0]
        return None

    def extract(self, lines: list[str]) -> ReceiptData:
        data = ReceiptData()
        data.raw_text = "\n".join(lines)
        scores = {}

        money_candidates = {"total": [], "subtotal": [], "tax": [], "discount": []}
        item_zone = False
        item_zone_end = False
        line_items_raw = []

        # ── MERCHANT REFINEMENT ──
        # Filter top lines for branding (no digits, no keywords like GST/DATE)
        top_branding_lines = [l.strip() for l in lines[:8] if len(l.strip()) > 3 
                              and not any(c.isdigit() for c in l.strip())
                              and not any(x in l.upper() for x in ["GST", "PH ", "BILL", "DATE", "TAX"])]
        if top_branding_lines:
            data.merchant = " ".join(top_branding_lines[:3])
            scores["merchant"] = 90

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue
            line_lower = line.lower()

            # ── DATE ──
            if not data.date:
                m = self.DATE_RE.search(line)
                if m:
                    data.date = m.group().strip()
                    scores["date"] = 95

            # ── MONEY FIELDS (Look-ahead logic) ──
            field_map = {
                "total": FIELD_ANCHORS["total"],
                "subtotal": FIELD_ANCHORS["subtotal"],
                "tax": FIELD_ANCHORS["tax"],
                "discount": FIELD_ANCHORS["discount"]
            }
            
            for f_name, anchors in field_map.items():
                matched, score = self._fuzzy_match_field(line, anchors)
                if matched:
                    # Penalize lines with 'qty' or 'item' when looking for money
                    final_score = score
                    if any(x in line_lower for x in ["item", "qty", "count", "ph", "gst"]):
                        final_score -= 50
                    
                    val = self._extract_money(line)
                    # Look-ahead: if no value on current line, check next 2 lines
                    if not val:
                        for offset in [1, 2]:
                            if i + offset < len(lines):
                                next_l = lines[i+offset]
                                # Very strong match if next line is strictly a decimal number
                                if re.match(r"^\s*(?:Rs\.?|₹)?\s*[\d,]+\.\d{2}\s*$", next_l):
                                    val = self._extract_money(next_l)
                                    final_score += 10
                                    break
                                elif not val:
                                    val = self._extract_money(next_l)

                    if val:
                        money_candidates[f_name].append((val, final_score))

            # ── OTHER FIELDS ──
            if not data.time:
                m = self.TIME_RE.search(line)
                if m:
                    data.time = m.group().strip()
                    scores["time"] = 90
            
            if not data.phone:
                if any(x in line.upper() for x in ["PH", "TEL", "MOBILE"]):
                    m = self.PHONE_RE.search(line)
                    if m:
                        data.phone = m.group().strip()
                        scores["phone"] = 90

            if not data.invoice_no:
                m = self.INVOICE_RE.search(line)
                if m:
                    data.invoice_no = m.group(1).strip()
                    scores["invoice_no"] = 90

            # ── LINE ITEMS ZONE DETECTION ──
            item_triggers = ["item", "description", "product", "qty", "quantity", "unit", "price", "amount", "particulars"]
            item_end_triggers = ["total", "subtotal", "tax", "vat", "gst", "discount", "payment", "thank", "visit"]

            if any(t in line_lower for t in item_triggers) and not item_zone_end:
                item_zone = True
            
            if item_zone and not item_zone_end:
                if any(t in line_lower for t in item_end_triggers):
                    item_zone_end = True
                else:
                    m = self.QTY_PRICE_RE.match(line)
                    if m:
                        desc = m.group(1).strip()
                        qty_str = m.group(2)
                        price_str = m.group(3).replace(",", "")
                        if len(desc) > 2 and re.search(r"\d", price_str):
                            try:
                                item = LineItem(
                                    description=desc,
                                    quantity=float(qty_str) if qty_str else 1.0,
                                    total=float(price_str),
                                    confidence=0.8,
                                )
                                line_items_raw.append(item)
                            except ValueError:
                                pass

        # ── RESOLVE MONEY FIELDS ──
        for field_name, candidates in money_candidates.items():
            if candidates:
                if field_name == "total":
                    # Tie-break: pick highest score, then LARGEST value
                    candidates.sort(key=lambda x: (x[1], float(x[0].replace(",", ""))), reverse=True)
                    best = candidates[0]
                else:
                    best = max(candidates, key=lambda x: x[1])
                setattr(data, field_name, best[0])
                scores[field_name] = best[1]

        # ── FALLBACK ──
        if not data.total:
            all_amounts = self.MONEY_RE.findall(data.raw_text)
            if all_amounts:
                try:
                    data.total = max(all_amounts, key=lambda x: float(x.replace(",", "")))
                    scores["total"] = 50
                    data.warnings.append("Total extracted via fallback heuristic.")
                except ValueError:
                    pass

        # ── MATH CONSISTENCY CHECK & AUTO-CORRECTION ──
        try:
            sub = float(data.subtotal.replace(",", "")) if data.subtotal else 0
            tot = float(data.total.replace(",", "")) if data.total else 0
            tax = float(data.tax.replace(",", "")) if data.tax else 0
            disc = float(data.discount.replace(",", "")) if data.discount else 0
            
            if sub > 0:
                expected = sub + tax - disc
                if tot == 0:
                    data.total = f"{expected:.2f}"
                    scores["total"] = 90
                    data.warnings.append(f"Total inferred from subtotal + tax: {data.total}")
                elif abs(expected - tot) > 0.05:
                    item_sum = sum(item.total for item in line_items_raw)
                    if abs(item_sum - expected) < 0.1 and abs(item_sum - tot) > 0.1:
                        data.total = f"{expected:.2f}"
                        scores["total"] = 95
                        data.warnings.append("Total corrected based on line items and subtotal.")
                    elif abs(expected - tot) > 1.0:
                        data.warnings.append(f"Math check: {sub} + {tax} - {disc} = {expected:.2f} ≠ {tot:.2f}")
                else:
                    scores["math_check"] = 100
            elif tot == 0 and line_items_raw:
                item_sum = sum(item.total for item in line_items_raw)
                if item_sum > 0:
                    data.total = f"{item_sum:.2f}"
                    scores["total"] = 80
                    data.warnings.append(f"Total calculated from line items: {data.total}")

        except Exception as e:
            logger.warning(f"Math check failed: {e}")

        data.line_items = line_items_raw
        data.confidence_scores = scores
        return data


# ─────────────────────────────────────────────
#  MAIN OCR PIPELINE
# ─────────────────────────────────────────────
class ReceiptOCR:
    """
    Full pipeline:
      1. Multi-variant image preprocessing
      2. PaddleOCR with reading-order preserved merging
      3. Fuzzy extraction + multi-line look-ahead
      4. Math consistency validation
    """

    def __init__(self, use_gpu: bool = False, lang: str = "en"):
        self.lang = lang
        self._ocr = None
        self.preprocessor = ImagePreprocessor()
        self.extractor = FuzzyExtractor(threshold=70)
        logger.info("ReceiptOCR engine initialized (lazy PaddleOCR load)")

    def _get_ocr(self):
        if self._ocr is None:
            try:
                import os
                os.environ["FLAGS_enable_pir_api"] = "0"
                os.environ["FLAGS_enable_new_ir_api"] = "0"
                os.environ["FLAGS_use_mkldnn"] = "0"
                
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    use_angle_cls=True, 
                    lang=self.lang,
                    enable_mkldnn=False,
                    use_tensorrt=False,
                    show_log=False
                )
                logger.info("PaddleOCR loaded successfully")
            except Exception as e:
                try:
                    from paddleocr import PaddleOCR
                    self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, enable_mkldnn=False)
                    logger.info("PaddleOCR loaded successfully (fallback)")
                except ImportError:
                    logger.warning("PaddleOCR not available — using mock mode")
                    self._ocr = "mock"
        return self._ocr

    def _run_paddle(self, img_array: np.ndarray) -> list[tuple[str, float]]:
        """Run PaddleOCR on a numpy image, return [(text, confidence)]."""
        ocr = self._get_ocr()
        if ocr == "mock":
            return []
        try:
            result = ocr.ocr(img_array)
            lines = []
            if not result:
                return []
                
            if isinstance(result[0], dict):
                res_dict = result[0]
                texts = res_dict.get('rec_texts', [])
                scores = res_dict.get('rec_scores', [])
                for text, score in zip(texts, scores):
                    if text.strip():
                        lines.append((text.strip(), float(score)))
            else:
                for res in result[0]:
                    if res and len(res) >= 2:
                        text = res[1][0]
                        conf = float(res[1][1])
                        if text.strip():
                            lines.append((text.strip(), conf))
            return lines
        except Exception as e:
            logger.error(f"PaddleOCR error: {e}")
            return []

    def _merge_results(self, all_results: list[list]) -> list[str]:
        """Merge OCR results preserving original reading order."""
        merged_lines = []
        seen_texts = []
        for result_set in all_results:
            for text, conf in result_set:
                if conf < 0.4: continue
                is_duplicate = False
                for existing_text in seen_texts:
                    if fuzz.ratio(text.lower(), existing_text.lower()) > 85:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    merged_lines.append(text)
                    seen_texts.append(text)
        return merged_lines

    def process_image(self, image_path: str) -> ReceiptData:
        """Full pipeline: preprocess → OCR → extract → validate."""
        logger.info(f"Processing: {image_path}")

        # Step 1: Get preprocessing variants (Optimized to skip redundant ones)
        variants = self.preprocessor.enhance_pil(image_path)
        if not variants:
            data = ReceiptData()
            data.warnings.append("Image loading failed.")
            return data

        # Step 2: Adaptive multi-pass with Early Exit
        all_results = []
        final_data = None

        for i, variant in enumerate(variants):
            logger.info(f"  Running OCR pass {i+1}/{len(variants)}")
            lines = self._run_paddle(variant)
            
            if not lines:
                continue
                
            all_results.append(lines)
            
            # ── EARLY EXIT LOGIC ──
            # If this specific pass found a Merchant AND a Total with good confidence, stop here!
            merged_so_far = self._merge_results([lines])
            temp_data = self.extractor.extract(merged_so_far)
            
            # Thresholds for early exit: Total found + Merchant found
            if temp_data.total and temp_data.merchant:
                logger.info("  >> High confidence results found. Stopping early to save time.")
                return temp_data
            
            # Cache the best one so far in case we don't find a perfect one
            final_data = temp_data

        # Step 3: If no early exit, merge all passes and do final extraction
        if len(all_results) > 1:
            logger.info("  >> No early exit. Merging all passes for robust extraction.")
            merged_lines = self._merge_results(all_results)
            return self.extractor.extract(merged_lines)

        return final_data or ReceiptData(warnings=["No text detected."])

    def process_image_bytes(self, image_bytes: bytes) -> ReceiptData:
        """Process from raw bytes (for web API usage)."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name
        try:
            return self.process_image(tmp_path)
        finally:
            os.unlink(tmp_path)
