# main.py - ENHANCED VERSION WITH MULTIPLE DOCUMENT TYPES
import io
import re
import cv2
import os
import zipfile
import numpy as np
import uuid
import base64
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Tuple
from enum import Enum
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from paddleocr import PaddleOCR
try:
    from paddlex import create_model
    PADDLEX_AVAILABLE = True
except ImportError:
    PADDLEX_AVAILABLE = False
    print("Warning: PaddleX not available, VL model will not be used")
import json
from datetime import datetime
from pdf2image import convert_from_bytes
from PIL import Image
import fitz  # PyMuPDF
from PyPDF2 import PdfReader

# --- 1. DOCUMENT TYPE DEFINITIONS ---
class DocumentType(str, Enum):
    FORM_A = "FORM_A"
    FORM_B = "FORM_B"
    FORM_C = "FORM_C"
    VERIFICATION = "VERIFICATION"
    INDIVIDUAL_PATTA = "INDIVIDUAL_PATTA"
    COMMUNITY_PATTA = "COMMUNITY_PATTA"
    CFR_PATTA = "CFR_PATTA"
    SHAPEFILE = "SHAPEFILE"

class UploadMethod(str, Enum):
    SINGLE = "SINGLE"
    BULK = "BULK"
    MOBILE = "MOBILE"

# --- 2. RESPONSE MODELS ---
class HealthCheckResult(BaseModel):
    score: int
    total_checks: int
    passed_checks: int
    failed_checks: List[str]
    warnings: List[str] = []
    critical_issues: List[str] = []



class ProcessingResult(BaseModel):
    document_type: str
    confidence: float
    extracted_data: dict
    processing_time: float
    file_name: str
    health_check: Optional[HealthCheckResult] = None
    is_pdf: bool = False
    total_pages: int = 1
    pages_processed: List[int] = []
    page_images_base64: Optional[List[str]] = None  # Base64 encoded page images for PDFs

class BulkProcessingResult(BaseModel):
    total_files: int
    processed_files: int
    failed_files: int
    results: List[ProcessingResult]
    errors: List[dict]

# --- VERIFICATION MODELS ---
class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class VerificationRecord(BaseModel):
    session_id: str
    original_data: dict
    verified_data: Optional[dict] = None
    mobile_number: str
    official_notes: Optional[str] = None
    status: VerificationStatus = VerificationStatus.PENDING
    created_at: str
    verified_at: Optional[str] = None
    document_image_base64: Optional[str] = None

# --- 3. INITIALIZE MODELS ---
print("=" * 50)
print("Loading PaddleOCR-VL-0.9B models into memory...")
print("Multi-language support: Odia, Hindi, Tamil, English")
print("=" * 50)

# Initialize OCR engines
vl_ocr_engine = None
standard_ocr_engine = None
use_vl_model = False

if PADDLEX_AVAILABLE:
    try:
        print("Creating PaddleOCR-VL-0.9B model...")
        vl_ocr_engine = create_model("PaddleOCR-VL-0.9B")
        use_vl_model = True
        print(f"PaddleOCR-VL engine initialized: {type(vl_ocr_engine).__name__}")
        print("✅ PaddleOCR-VL-0.9B loaded successfully!")
        print("   Supported Languages: Odia, Hindi, Tamil, English")
        print("   Model Type: Vision-Language OCR")
        print("   Capabilities: Multi-language text detection and recognition")
    except Exception as e:
        print(f"⚠️ Error loading PaddleOCR-VL-0.9B: {e}")
        print("Falling back to standard PaddleOCR...")
        PADDLEX_AVAILABLE = False

def initialize_standard_ocr():
    """Ensure the standard PaddleOCR engine is ready (lazy initialization)."""
    global standard_ocr_engine
    if standard_ocr_engine is not None:
        return standard_ocr_engine

    print("Initializing standard PaddleOCR with multi-language support...")
    try:
        standard_ocr_engine = PaddleOCR(
            use_textline_orientation=True,
            lang='en',
            text_det_thresh=0.3,
            text_det_box_thresh=0.5,
            text_det_unclip_ratio=1.6,
        )
        print("✅ Standard PaddleOCR loaded (fallback mode)")
        print("   Note: For better Odia/Tamil support, install PaddleX")
    except Exception as e:
        print(f"❌ Failed to load standard PaddleOCR: {e}")
        raise

    return standard_ocr_engine

# Always prepare standard OCR (needed even when VL succeeds for fallback processing)
initialize_standard_ocr()

def run_vl_ocr(image_bgr: np.ndarray) -> str:
    """
    Run PaddleOCR-VL-0.9B on the given BGR image and return extracted text.
    """
    if not use_vl_model or vl_ocr_engine is None:
        return ""

    try:
        img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        vl_prompt = (
            "OCR: Transcribe every piece of text you can see in this document image. "
            "Preserve the original language (Odia/Hindi/Tamil/English) and line breaks."
        )
        vl_inputs = {"image": pil_img, "query": vl_prompt}
        vl_results = list(
            vl_ocr_engine.predict(
                vl_inputs,
                skip_special_tokens=True,
                max_new_tokens=4096,
            )
        )

        if not vl_results:
            return ""

        # DocVLMResult behaves like a dict
        primary = vl_results[0]
        vl_text = ""

        if isinstance(primary, dict):
            vl_text = primary.get("result", "") or primary.get("text", "")
        else:
            # Fallback to attribute-style access
            vl_text = getattr(primary, "result", "")

        if vl_text:
            print(
                f"✓ VL model produced {len(vl_text.splitlines())} lines, {len(vl_text)} characters"
            )
            return normalize_hindi_text(vl_text)

    except Exception as vl_error:
        print(f"⚠ VL model error: {vl_error}")
        import traceback

        traceback.print_exc()

    return ""

print("=" * 50)
print("Models loaded successfully!")
print("=" * 50)
print(f"✓ Model Type: {'PaddleOCR-VL-0.9B (Vision-Language)' if use_vl_model else 'Standard PaddleOCR (Fallback)'}")
print(f"✓ Language Support: Odia, Hindi, Tamil, English")

# --- 4. VERIFICATION STORAGE ---
verification_records = {}

# --- 5. INITIALIZE FASTAPI APP ---
app = FastAPI(
    title="FRA Document Intelligence API",
    description="Advanced OCR system for Forest Rights Act document processing",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint to verify the API is running."""
    return {
        "status": "ok",
        "message": "FRA Document Intelligence API v2.0 is running",
        "version": "2.0.0",
        "supported_document_types": [doc_type.value for doc_type in DocumentType],
        "upload_methods": [method.value for method in UploadMethod]
    }

# --- 5. DOCUMENT TYPE DETECTION ---
def detect_document_type(text: str) -> tuple[DocumentType, float]:
    """Detect document type based on OCR text with confidence score."""
    text_lower = text.lower()
    
    # Form detection patterns with confidence scoring
    patterns = {
        DocumentType.FORM_A: [
            r"form\s*-?\s*a", r"individual\s+rights", r"self\s*-?\s*cultivation",
            r"habitation", r"individual\s+claim"
        ],
        DocumentType.FORM_B: [
            r"form\s*-?\s*b", r"community\s+rights", r"nistar", r"minor\s+forest\s+produce",
            r"grazing\s+rights", r"community\s+claim"
        ],
        DocumentType.FORM_C: [
            r"form\s*-?\s*c", r"community\s+forest\s+resource", r"gram\s+sabha",
            r"protect.*regenerate.*conserve", r"cfr"
        ],
        DocumentType.VERIFICATION: [
            r"verification", r"sdlc", r"district\s+level\s+committee", r"dlc",
            r"resolution", r"examination", r"sub\s*-?\s*divisional"
        ],
        DocumentType.INDIVIDUAL_PATTA: [
            r"individual\s+patta", r"title.*forest\s+land.*occupation",
            r"heritable.*not\s+alienable", r"individual\s+title"
        ],
        DocumentType.COMMUNITY_PATTA: [
            r"community\s+patta", r"community\s+forest\s+rights",
            r"title.*community", r"village\s+rights"
        ],
        DocumentType.CFR_PATTA: [
            r"cfr\s+patta", r"community\s+forest\s+resources",
            r"gram\s+sabha.*right", r"manage.*community\s+forest"
        ],
        DocumentType.SHAPEFILE: [
            r"shapefile", r"digital\s+map", r"boundary", r"demarcation",
            r"potential\s+area\s+map", r"gis", r"coordinates"
        ]
    }
    
    best_match = DocumentType.FORM_A
    max_confidence = 0.0
    
    for doc_type, pattern_list in patterns.items():
        confidence = 0.0
        for pattern in pattern_list:
            matches = len(re.findall(pattern, text_lower))
            confidence += matches * (1.0 / len(pattern_list))
        
        if confidence > max_confidence:
            max_confidence = confidence
            best_match = doc_type
    
    # Normalize confidence to 0-1 range
    normalized_confidence = min(max_confidence / 2.0, 1.0) if max_confidence > 0 else 0.1
    
    return best_match, normalized_confidence

# --- 6. PDF PROCESSING UTILITIES ---

def is_pdf(file_bytes: bytes) -> bool:
    """Check if the file is a PDF."""
    return file_bytes[:4] == b'%PDF'

# --- HINDI TEXT PROCESSING UTILITIES ---

def normalize_hindi_text(text: str) -> str:
    """Normalize Hindi text for consistent pattern matching."""
    if not text:
        return text
    
    # Unicode normalization (NFC for composed characters)
    text = unicodedata.normalize('NFC', text)
    
    # Common OCR mistakes in Hindi
    replacements = {
        'ॉ': 'ो',  # Candra O to O
        'ऺ': 'ष',  # Similar looking characters
        '।': ':',  # Devanagari danda to colon
        '॥': '::',
        'ο': 'ο',  # Greek omicron mistaken for Hindi O
        '०': '0',  # Devanagari digits to ASCII
        '१': '1',
        '२': '2',
        '३': '3',
        '४': '4',
        '५': '5',
        '६': '6',
        '७': '7',
        '८': '8',
        '९': '9',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove zero-width characters
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def preprocess_for_hindi(image_bytes: bytes) -> np.ndarray:
    """Enhanced preprocessing specifically for Hindi/Devanagari text."""
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None
    
    # Increase contrast for better character separation
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l,a,b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    
    # Convert to grayscale
    gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    
    # Denoise while preserving edges (important for matras/diacritics)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    
    # Adaptive thresholding (better for varying lighting)
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 15, 2
    )
    
    # Morphological operations to connect broken characters
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    # Convert back to BGR for PaddleOCR (expects 3 channels)
    morph_bgr = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)
    
    return morph_bgr

def extract_hindi_fields_multipass(text: str, patterns: dict) -> dict:
    """Multi-pass extraction with fallback strategies for Hindi text."""
    extracted = {}
    
    # Pass 1: Exact pattern matching with normalized text
    normalized_text = normalize_hindi_text(text)
    
    for field, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, normalized_text, re.UNICODE | re.MULTILINE | re.IGNORECASE)
            if match and len(match.group(1).strip()) > 1:
                extracted[field] = normalize_hindi_text(match.group(1))
                break
    
    # Pass 2: Line-by-line extraction for table structures
    if len(extracted) < len(patterns) // 2:  # If less than 50% extracted
        lines = normalized_text.split('\n')
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Claimant name after "दावेदार"
            if 'claimant_name' not in extracted:
                if any(word in line_clean for word in ['दावेदार', 'आवेदक', 'claimant', 'applicant']):
                    # Check same line
                    parts = re.split(r'[:।/-]\s*', line_clean)
                    if len(parts) > 1 and len(parts[-1].strip()) > 2:
                        candidate = parts[-1].strip()
                        if candidate.lower() not in ['नाम', 'name', 'का', 'के']:
                            extracted['claimant_name'] = candidate
                    # Check next line
                    elif i + 1 < len(lines):
                        next_line = normalize_hindi_text(lines[i + 1])
                        if len(next_line) > 2 and not any(skip in next_line for skip in ['पिता', 'पता', 'गांव', 'father', 'address']):
                            extracted['claimant_name'] = next_line.strip()
            
            # Village
            if 'village' not in extracted and any(word in line_clean for word in ['गांव', 'ग्राम', 'village']):
                parts = re.split(r'[:।/-]\s*', line_clean)
                if len(parts) > 1:
                    extracted['village'] = parts[-1].strip()
            
            # District
            if 'district' not in extracted and any(word in line_clean for word in ['जिला', 'district']):
                parts = re.split(r'[:।/-]\s*', line_clean)
                if len(parts) > 1:
                    extracted['district'] = parts[-1].strip()
            
            # Father/Mother name
            if 'father_mother_name' not in extracted and any(word in line_clean for word in ['पिता', 'माता', 'father', 'mother']):
                parts = re.split(r'[:।/-]\s*', line_clean)
                if len(parts) > 1 and len(parts[-1].strip()) > 2:
                    candidate = parts[-1].strip()
                    if candidate.lower() not in ['नाम', 'name']:
                        extracted['father_mother_name'] = candidate
            
            # Husband/Wife name
            if 'husband_wife_name' not in extracted and any(word in line_clean for word in ['पति', 'पत्नी', 'husband', 'wife']):
                parts = re.split(r'[:।/-]\s*', line_clean)
                if len(parts) > 1 and len(parts[-1].strip()) > 2:
                    candidate = parts[-1].strip()
                    if candidate.lower() not in ['नाम', 'name']:
                        extracted['husband_wife_name'] = candidate
    
    # Pass 3: Fuzzy matching for critical fields still missing
    critical_fields = ['claimant_name', 'village', 'district']
    for field in critical_fields:
        if field not in extracted:
            # Try to find field with fuzzy matching
            field_keywords = {
                'claimant_name': ['दावेदार', 'आवेदक', 'नाम'],
                'village': ['गांव', 'ग्राम'],
                'district': ['जिला']
            }
            
            if field in field_keywords:
                for line in lines:
                    for keyword in field_keywords[field]:
                        ratio = SequenceMatcher(None, keyword, line).ratio()
                        if ratio > 0.6:  # 60% similarity
                            # Extract value after this line
                            line_idx = lines.index(line)
                            if line_idx + 1 < len(lines):
                                candidate = normalize_hindi_text(lines[line_idx + 1])
                                if len(candidate) > 2:
                                    extracted[field] = candidate
                                    break
    
    return extracted

def extract_images_from_pdf(pdf_bytes: bytes, dpi: int = 300) -> List[Tuple[int, bytes]]:
    """
    Extract images from PDF using multiple methods for best quality.
    Returns list of tuples: (page_number, image_bytes)
    """
    images = []
    
    try:
        # Method 1: Try PyMuPDF for embedded images (faster, better quality)
        print("Attempting PDF extraction with PyMuPDF...")
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            
            # Convert page to image at high DPI
            mat = fitz.Matrix(dpi/72, dpi/72)  # 72 is default DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert pixmap to bytes
            img_bytes = pix.tobytes("png")
            images.append((page_num + 1, img_bytes))
            
            print(f"Extracted page {page_num + 1} using PyMuPDF")
        
        pdf_document.close()
        
        if images:
            return images
    
    except Exception as e:
        print(f"PyMuPDF extraction failed: {str(e)}. Trying pdf2image...")
    
    try:
        # Method 2: Fallback to pdf2image (more compatible but slower)
        print("Attempting PDF extraction with pdf2image...")
        pil_images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            fmt='png',
            thread_count=2
        )
        
        for page_num, pil_image in enumerate(pil_images):
            # Convert PIL image to bytes
            img_buffer = io.BytesIO()
            pil_image.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()
            images.append((page_num + 1, img_bytes))
            
            print(f"Extracted page {page_num + 1} using pdf2image")
        
        return images
    
    except Exception as e:
        print(f"pdf2image extraction failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract images from PDF: {str(e)}"
        )

def get_pdf_metadata(pdf_bytes: bytes) -> dict:
    """Extract PDF metadata."""
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        metadata = {
            'total_pages': len(pdf_reader.pages),
            'title': pdf_reader.metadata.get('/Title', 'Unknown') if pdf_reader.metadata else 'Unknown',
            'author': pdf_reader.metadata.get('/Author', 'Unknown') if pdf_reader.metadata else 'Unknown',
            'creator': pdf_reader.metadata.get('/Creator', 'Unknown') if pdf_reader.metadata else 'Unknown',
        }
        return metadata
    except Exception as e:
        print(f"Failed to extract PDF metadata: {str(e)}")
        return {'total_pages': 0, 'title': 'Unknown', 'author': 'Unknown', 'creator': 'Unknown'}

def process_pdf_document(pdf_bytes: bytes, max_pages: int = 10, dpi: int = 300) -> dict:
    """
    Process a PDF document with PaddleOCR v4 on all pages.
    Returns combined text, page-wise results, and base64 encoded page images.
    """
    print(f"\n=== Processing PDF Document with PaddleOCR v4 ===")
    
    # Get PDF metadata
    metadata = get_pdf_metadata(pdf_bytes)
    total_pages = metadata['total_pages']
    
    print(f"PDF has {total_pages} pages")
    
    if total_pages == 0:
        raise HTTPException(status_code=400, detail="PDF appears to be empty or corrupted")
    
    if total_pages > max_pages:
        print(f"Warning: PDF has {total_pages} pages, processing first {max_pages} pages only")
        pages_to_process = max_pages
    else:
        pages_to_process = total_pages
    
    # Extract images from PDF
    page_images = extract_images_from_pdf(pdf_bytes, dpi=dpi)
    
    if not page_images:
        raise HTTPException(status_code=500, detail="Failed to extract any pages from PDF")
    
    # Process each page with OCR
    all_text = []
    page_results = []
    processed_pages = []
    page_images_base64 = []
    
    for page_num, img_bytes in page_images[:pages_to_process]:
        print(f"\nProcessing page {page_num} with PaddleOCR v4...")
        
        try:
            # Convert to base64 for storage
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            page_images_base64.append(f"data:image/png;base64,{img_base64}")
            
            # Extract text with enhanced preprocessing
            page_text = extract_text_from_image(img_bytes, enhance_image=True)
            
            if page_text:
                all_text.append(f"\n--- Page {page_num} ---\n{page_text}")
                page_results.append({
                    'page': page_num,
                    'text': page_text,
                    'word_count': len(page_text.split())
                })
                processed_pages.append(page_num)
                print(f"Page {page_num}: Extracted {len(page_text.split())} words")
            else:
                print(f"Page {page_num}: No text extracted")
                page_results.append({
                    'page': page_num,
                    'text': '',
                    'word_count': 0,
                    'warning': 'No text extracted from this page'
                })
        
        except Exception as e:
            print(f"Error processing page {page_num}: {str(e)}")
            page_results.append({
                'page': page_num,
                'text': '',
                'word_count': 0,
                'error': str(e)
            })
    
    combined_text = "\n".join(all_text)
    
    return {
        'combined_text': combined_text,
        'page_results': page_results,
        'total_pages': total_pages,
        'processed_pages': processed_pages,
        'metadata': metadata,
        'page_images_base64': page_images_base64
    }


# --- 7. ENHANCED TEXT EXTRACTION ---
def extract_text_from_image(image_bytes: bytes, enhance_image: bool = True) -> str:
    """Enhanced OCR with PaddleOCR v4 and Hindi-optimized preprocessing."""
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            print("OCR Error: Failed to decode image")
            return ""
        
        print(f"Image loaded: shape={img.shape}, dtype={img.dtype}")
        
        # Try VL model first if available (PaddleOCR-VL-0.9B)
        if use_vl_model and vl_ocr_engine is not None:
            print("Using PaddleOCR-VL-0.9B for multi-language OCR...")
            vl_text = run_vl_ocr(img)
            if vl_text:
                return vl_text
            print("⚠ VL model returned no text, falling back to standard OCR")
        
        # Try standard OCR first (simpler, works for both English and Hindi)
        print("Attempting standard OCR...")
        result_to_use = None
        std_engine = initialize_standard_ocr()
        
        try:
            result = std_engine.ocr(img)
            
            if result and len(result) > 0:
                # Check if it's the new dict format (PaddleOCR v4)
                if isinstance(result[0], dict) and 'rec_texts' in result[0]:
                    print(f"Detected {len(result[0]['rec_texts'])} text regions (v4 format)")
                    result_to_use = result
                # Check if it's the old list format
                elif isinstance(result[0], list) and len(result[0]) > 0:
                    print(f"Detected {len(result[0])} text regions (v3 format)")
                    result_to_use = result
                else:
                    print("OCR returned empty result")
            else:
                print("OCR returned None or empty list")
        except Exception as e:
            print(f"Error with OCR: {e}")
            import traceback
            traceback.print_exc()
        
        # If standard fails, try with Hindi preprocessing
        if not result_to_use:
            print("Trying Hindi-optimized preprocessing...")
            try:
                img_hindi = preprocess_for_hindi(image_bytes)
                if img_hindi is not None:
                    result = std_engine.ocr(img_hindi)
                    if result and len(result) > 0 and result[0]:
                        print(f"Hindi preprocessing: detected {len(result[0])} text regions")
                        result_to_use = result
            except Exception as e:
                print(f"Error with Hindi preprocessing: {e}")
        
        if not result_to_use or not result_to_use[0]:
            print("OCR Warning: No text detected")
            return ""
        
        # Parse PaddleOCR v4 results
        recognized_texts = []
        try:
            ocr_data = result_to_use[0]
            
            # New v4 dict format: {'rec_texts': [...], 'rec_scores': [...]}
            if isinstance(ocr_data, dict) and 'rec_texts' in ocr_data:
                texts = ocr_data['rec_texts']
                scores = ocr_data.get('rec_scores', [1.0] * len(texts))
                
                print(f"Processing {len(texts)} text regions (v4 format)...")
                for idx, (text, confidence) in enumerate(zip(texts, scores)):
                    text = str(text).strip()
                    confidence = float(confidence)
                    
                    print(f"  [{idx}] '{text}' (conf: {confidence:.2f})")
                    
                    # Use lower threshold (0.3) for both English and Hindi
                    if confidence >= 0.3 and len(text) > 0:
                        # Only normalize if it looks like Hindi text
                        if any('\u0900' <= c <= '\u097F' for c in text):
                            text = normalize_hindi_text(text)
                        
                        if text:  # Check again after normalization
                            recognized_texts.append(text)
                            print(f"      ✓ Accepted")
                        else:
                            print(f"      ✗ Empty after normalization")
                    else:
                        print(f"      ✗ Low confidence or empty")
            
            # Old v3 list format: [[[bbox, (text, confidence)], ...]]
            else:
                print(f"Processing {len(ocr_data)} text regions (v3 format)...")
                for idx, line in enumerate(ocr_data):
                    if not line or len(line) < 2:
                        print(f"  Region {idx}: Invalid format, skipping")
                        continue
                    
                    # line format: [bbox, (text, confidence)]
                    text_info = line[1]
                    
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                        text = str(text_info[0]).strip()
                        confidence = float(text_info[1])
                    elif isinstance(text_info, str):
                        text = text_info.strip()
                        confidence = 1.0
                    else:
                        print(f"  Region {idx}: Unexpected text_info format: {type(text_info)}")
                        continue
                    
                    print(f"  [{idx}] '{text}' (conf: {confidence:.2f})")
                    
                    # Use lower threshold (0.3) for both English and Hindi
                    if confidence >= 0.3 and len(text) > 0:
                        # Only normalize if it looks like Hindi text
                        if any('\u0900' <= c <= '\u097F' for c in text):
                            text = normalize_hindi_text(text)
                        
                        if text:  # Check again after normalization
                            recognized_texts.append(text)
                            print(f"      ✓ Accepted")
                        else:
                            print(f"      ✗ Empty after normalization")
                    else:
                        print(f"      ✗ Low confidence or empty")
                    
        except Exception as e:
            print(f"Error parsing OCR results: {e}")
            import traceback
            traceback.print_exc()
            return ""
        
        if not recognized_texts:
            print("No text recognized after filtering")
            return ""
        
        full_text = "\n".join(recognized_texts)
        print(f"✓ OCR Success: Extracted {len(recognized_texts)} lines, {len(full_text)} characters")
        return full_text
        
    except Exception as e:
        print(f"OCR extraction error: {e}")
        import traceback
        traceback.print_exc()
        return ""

# --- 7. DOCUMENT-SPECIFIC PARSERS ---
def extract_from_table_structure(text: str) -> dict:
    """Extract data from table-structured Hindi/bilingual forms."""
    extracted = {}
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or len(line) < 2:
            continue
            
        # Claimant name
        if any(word in line for word in ['दावेदार', 'आवेदक', 'दावेदारों', 'claimant', 'applicant']) and 'claimant_name' not in extracted:
            parts = re.split(r'[\s:।/-]{2,}', line)
            if len(parts) > 1 and not any(skip in parts[-1].lower() for skip in ['नाम', 'name', 'का', 'के']):
                candidate = parts[-1].strip()
                if len(candidate) > 2:
                    extracted['claimant_name'] = candidate
            elif i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 2:
                    if not any(hindi in next_line for hindi in ['पता', 'गांव', 'जिला', 'पिता', 'पति', 'तहसील', 'ग्राम']):
                        extracted['claimant_name'] = next_line
        
        # Father/Husband name
        if any(word in line for word in ['पति', 'पिता', 'father', 'husband']) and 'father_husband_name' not in extracted:
            parts = re.split(r'[\s:।/-]{2,}', line)
            if len(parts) > 1:
                candidate = parts[-1].strip()
                if len(candidate) > 2 and not any(skip in candidate.lower() for skip in ['नाम', 'name', 'का', 'के']):
                    extracted['father_husband_name'] = candidate
            elif i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 2:
                    if not any(hindi in next_line for hindi in ['पता', 'गांव', 'जिला', 'तहसील']):
                        extracted['father_husband_name'] = next_line
        
        # Other fields
        field_mappings = [
            (['गांव', 'ग्राम', 'गाँव', 'village'], 'village'),
            (['पता', 'address', 'पत्ता'], 'address'),
            (['जिला', 'जिल्हा', 'district'], 'district'),
            (['ग्राम पंचायत', 'पंचायत', 'gram panchayat'], 'gram_panchayat'),
            (['तहसील', 'तालुका', 'tehsil', 'taluka'], 'tehsil'),
            (['राज्य', 'प्रदेश', 'state'], 'state')
        ]
        
        for keywords, field_name in field_mappings:
            if any(word in line for word in keywords) and field_name not in extracted:
                parts = re.split(r'[\s:।/-]{2,}', line)
                if len(parts) > 1:
                    candidate = parts[-1].strip()
                    if len(candidate) > 1:
                        extracted[field_name] = candidate
    
    return extracted

def parse_form_data(text: str, doc_type: DocumentType) -> dict:
    """Parse data specific to different document types with enhanced Hindi support."""
    base_data = {
        "claim_number": "Not Found",
        "claimant_name": "Not Found",
        "husband_wife_name": "Not Found",
        "father_mother_name": "Not Found",
        "claim_type": doc_type.value,
        "address": "Not Found",
        "village": "Not Found",
        "gram_panchayat": "Not Found",
        "tehsil": "Not Found",
        "district": "Not Found",
        "state": "Not Found",
        "claim_status": "Not Found",
        "date_submitted": "Not Found",
        "scheduled_tribe": "Not Found",
        "raw_text": text
    }
    
    # First try table-based extraction
    table_data = extract_from_table_structure(text)
    for key, value in table_data.items():
        if value and len(str(value).strip()) > 1:
            base_data[key] = value
    
    # Enhanced bilingual patterns
    patterns = {
        "claim_number": [
            r"(?:दावा\s*क्रमांक|क्रमांक)[\s:।./-]*([A-Za-z0-9/\-]{1,30})",
            r"(?i)(?:claim\s*number|serial\s*no|claim\s*no)[\s:/-]*([A-Za-z0-9/\-]{1,30})",
            r"क्रमांक[\s:।./-]*([^\n]{1,20})",
        ],
        "claimant_name": [
            r"(?:दावेदार[\s]*(?:\(रों\))?[\s]*का[\s]*/[\s]*के[\s]*नाम)[\s:।./-]*([^\n]{3,60})",
            r"(?:दावेदार[\s]*(?:\(रों\))?[\s]*का[\s]*नाम)[\s:।./-]*([^\n]{3,60})",
            r"(?:दावेदार|दावेदारों|आवेदक)[\s:।./-]+([^\n]{3,60})",
            r"(?i)(?:Name\s*of\s*the\s*claimant|claimant.*name|applicant.*name)[\s:।./-]*([^\n]{3,60})",
            r"(?:श्री\s*मती|श्री|श्रीमती|सुश्री|कु\.|कुमारी|Shri|Smt|Mr\.|Mrs\.)[\s\.]*([^\n]{3,60})",
            r"नाम[\s:।./-]+([A-Za-z\u0900-\u097F\s]{3,60})",
            r"(?:दावेदार|आवेदक|claimant|applicant)[\s:।./-]*\n+\s*([A-Za-z\u0900-\u097F\s]{3,60})",
        ],
        "husband_wife_name": [
            r"(?:पति[\s]*/[\s]*पत्नी[\s]*का[\s]*नाम|पति/पत्नी)[\s:।/-]+([^\n]{3,50})",
            r"(?i)(?:husband[\s]*/[\s]*wife|spouse)[\s]*(?:'?s)?[\s]*(?:name)?[\s:/-]+([^\n]{3,50})",
        ],
        "father_mother_name": [
            r"(?:पिता[\s]*/[\s]*माता[\s]*का[\s]*नाम|पिता/माता)[\s:।/-]+([^\n]{3,50})",
            r"(?i)(?:father[\s]*/[\s]*mother|parents)[\s]*(?:'?s)?[\s]*(?:name)?[\s:/-]+([^\n]{3,50})",
        ],
        "father_husband_name": [
            r"(?:पति|पिता)[\s]*(?:का)?[\s]*(?:नाम)?[\s:।/-]*([^\n]{3,50})",
            r"(?i)(?:father|husband)[\s]*(?:'?s)?[\s]*(?:name)?[\s:/-]*([^\n]{3,50})",
        ],
        "address": [
            r"(?:पता|पत्ता|निवास)[\s:।/-]+([^\n]{3,100})",
            r"(?i)address[\s:/-]+([^\n]{3,100})",
        ],
        "village": [
            r"(?:गांव|ग्राम|गाँव)[\s:।/-]+([^\n]{2,50})",
            r"(?i)village[\s:/-]+([^\n]{2,50})",
        ],
        "gram_panchayat": [
            r"(?:ग्राम\s*पंचायत|पंचायत)[\s:।/-]+([^\n]{2,50})",
            r"(?i)gram panchayat[\s:/-]+([^\n]{2,50})",
        ],
        "tehsil": [
            r"(?:तहसील[\s]*/[\s]*तालुका|तहसील|तालुका)[\s:।/-]+([^\n]{2,50})",
            r"(?i)(?:tehsil[\s]*/[\s]*taluka|tehsil|taluka|block)[\s:/-]+([^\n]{2,50})",
        ],
        "district": [
            r"(?:जिला|जिल्हा)[\s:।/-]+([^\n]{2,50})",
            r"(?i)district[\s:/-]+([^\n]{2,50})",
        ],
        "state": [
            r"(?:राज्य|प्रदेश)[\s:।/-]+([^\n]{2,50})",
            r"(?i)state[\s:/-]+([^\n]{2,50})",
        ],
        "date_submitted": [
            r"(?:दिनांक|तारीख|तिथि)[\s:।/-]*(\d{1,2}[-/.\s]\d{1,2}[-/.\s]\d{2,4})",
            r"(?i)date[\s:/-]*(\d{1,2}[-/.\s]\d{1,2}[-/.\s]\d{2,4})",
        ],
        "scheduled_tribe": [
            r"(?:अनुसूचित\s*जनजाति|एस\.?टी\.?)[\s:।/-]*(हाँ|हां|नहीं|Yes|No|yes|no)",
            r"(?i)scheduled tribe[\s:/\-]*(Yes|No|yes|no|हाँ|हां|नहीं)",
        ]
    }
    
    # Field labels to detect invalid extractions
    field_labels = {
        'claimant_name': ['name', 'नाम', 'claimant', 'दावेदार', 'आवेदक', 'applicant'],
        'address': ['address', 'पता', 'पता:', 'पता।'],
        'village': ['village', 'गांव', 'ग्राम', 'village:', 'गांव:'],
        'gram_panchayat': ['gram panchayat', 'ग्राम पंचायत', 'panchayat', 'पंचायत'],
        'tehsil': ['tehsil', 'तहसील', 'तहसील:'],
        'district': ['district', 'जिला', 'जिला:'],
        'state': ['state', 'राज्य', 'राज्य:'],
    }
    
    # Extract with regex patterns
    for field, pattern_list in patterns.items():
        current_value = str(base_data.get(field, "")).strip()
        
        # Skip if we have a valid value (not "Not Found" and not just a label)
        if current_value != "Not Found" and len(current_value) > 2:
            # Check if current value is just a field label
            is_label = False
            if field in field_labels:
                current_lower = current_value.lower()
                for label in field_labels[field]:
                    if current_lower == label or current_lower == label + ':' or current_lower == label + '।':
                        is_label = True
                        break
            
            # If it's a valid value (not a label), skip to next field
            if not is_label:
                continue
            
        for pattern in pattern_list:
            match = re.search(pattern, text, re.UNICODE | re.MULTILINE | re.IGNORECASE)
            if match:
                extracted_value = match.group(1).strip()
                extracted_value = re.sub(r'^[\s:।./-]+', '', extracted_value)
                extracted_value = re.sub(r'[\s:।./-]+$', '', extracted_value)
                
                if len(extracted_value) > 1:
                    lower_value = extracted_value.lower()
                    
                    # Full skip values - reject if value is EXACTLY these
                    skip_values_full = ['name', 'नाम', 'address', 'पता', 'village', 'गांव', 'of', 'the']
                    
                    # Partial skip values - only reject if value is JUST this single word
                    skip_values_partial = ['का', 'के', 'की']
                    
                    # Check if value should be skipped
                    should_skip = False
                    if lower_value in skip_values_full or extracted_value in skip_values_full:
                        should_skip = True
                    elif len(extracted_value.split()) == 1 and (lower_value in skip_values_partial or extracted_value in skip_values_partial):
                        should_skip = True
                    
                    # Also check against field-specific labels
                    if field in field_labels and not should_skip:
                        for label in field_labels[field]:
                            if lower_value == label or lower_value == label + ':':
                                should_skip = True
                                break
                    
                    if not should_skip:
                        base_data[field] = extracted_value
                        break
    
    # Special fallback for claimant_name if still not found
    if base_data.get("claimant_name") == "Not Found" or base_data.get("claimant_name", "").lower() in ['नाम', 'name', 'दावेदार', 'claimant']:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            # Look for lines with claimant keywords
            if any(keyword in line.lower() for keyword in ['दावेदार', 'आवेदक', 'claimant', 'applicant']):
                # Check current line for name after separator
                parts = re.split(r'[:\।/-]{1,3}', line)
                if len(parts) > 1:
                    candidate = parts[-1].strip()
                    candidate_lower = candidate.lower()
                    if len(candidate) > 3 and not any(skip in candidate_lower for skip in ['नाम', 'name', 'का', 'के', 'पता', 'गांव', 'address', 'village']):
                        # Avoid field labels
                        if candidate_lower not in ['दावेदार', 'आवेदक', 'claimant', 'applicant']:
                            base_data["claimant_name"] = candidate
                            break
                
                # Check next line if current line didn't have a value
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    next_lower = next_line.lower()
                    
                    # Make sure next line isn't another field label
                    if (len(next_line) > 3 and 
                        not any(keyword in next_lower for keyword in ['पिता', 'पति', 'माता', 'गांव', 'जिला', 'father', 'husband', 'mother', 'village', 'district', 'address', 'पता']) and
                        next_lower not in ['नाम', 'name', 'दावेदार', 'claimant']):
                        base_data["claimant_name"] = next_line
                        break
    
    # NEW: Apply multi-pass extraction if many fields still missing
    missing_count = sum(1 for v in base_data.values() if v == "Not Found")
    if missing_count > len(base_data) // 3:  # If more than 1/3 fields missing
        print(f"🔍 Applying multi-pass extraction ({missing_count} fields missing)...")
        multipass_data = extract_hindi_fields_multipass(text, patterns)
        
        # Merge multi-pass results
        for field, value in multipass_data.items():
            if field in base_data and base_data[field] == "Not Found":
                base_data[field] = value
                print(f"  ✓ Multi-pass found {field}: {value}")
    
    # Document-specific extractions
    if doc_type in [DocumentType.FORM_A, DocumentType.FORM_B, DocumentType.FORM_C]:
        # Form type detection
        form_match = re.search(r"(?i)(FORM\s*-\s*[A-C])", text)
        if form_match:
            base_data["claim_type"] = form_match.group(1).strip()
    
    elif doc_type == DocumentType.VERIFICATION:
        # Verification-specific fields
        verification_data = {
            "committee_type": "Not Found",
            "resolution_number": "Not Found",
            "verification_date": "Not Found",
            "recommendation": "Not Found"
        }
        
        # Committee type
        if re.search(r"(?i)gram sabha", text):
            verification_data["committee_type"] = "Gram Sabha"
        elif re.search(r"(?i)sdlc|sub.*divisional", text):
            verification_data["committee_type"] = "SDLC"
        elif re.search(r"(?i)dlc|district.*level", text):
            verification_data["committee_type"] = "DLC"
        
        # Resolution number
        res_match = re.search(r"(?i)resolution.*no[\s.:-]*([A-Z0-9\/\-]+)", text)
        if res_match:
            verification_data["resolution_number"] = res_match.group(1).strip()
        
        # Recommendation
        if re.search(r"(?i)approved|recommend.*approval", text):
            verification_data["recommendation"] = "Approved"
        elif re.search(r"(?i)rejected|recommend.*rejection", text):
            verification_data["recommendation"] = "Rejected"
        elif re.search(r"(?i)pending|under.*review", text):
            verification_data["recommendation"] = "Pending"
        
        base_data.update(verification_data)
    
    elif doc_type in [DocumentType.INDIVIDUAL_PATTA, DocumentType.COMMUNITY_PATTA, DocumentType.CFR_PATTA]:
        # Patta-specific fields
        patta_data = {
            "title_number": "Not Found",
            "area_granted": "Not Found",
            "survey_number": "Not Found",
            "issue_date": "Not Found"
        }
        
        # Title number
        title_match = re.search(r"(?i)title.*no[\s.:-]*([A-Z0-9\/\-]+)", text)
        if title_match:
            patta_data["title_number"] = title_match.group(1).strip()
        
        # Area granted
        area_match = re.search(r"(?i)area[\s]*granted[\s.:-]*([0-9.]+)\s*(hectare|acre|ha)", text)
        if area_match:
            patta_data["area_granted"] = f"{area_match.group(1)} {area_match.group(2)}"
        
        # Survey number
        survey_match = re.search(r"(?i)survey.*no[\s.:-]*([A-Z0-9\/\-]+)", text)
        if survey_match:
            patta_data["survey_number"] = survey_match.group(1).strip()
        
        base_data.update(patta_data)
    
    return base_data

# --- 8. DOCUMENT HEALTH CHECK ENGINE ---

class DocumentHealthChecker:
    """
    Document Health Check Engine for FRA documents.
    Implements automated pre-scrutiny based on FRA Act and Rules.
    """
    
    def __init__(self):
        # Evidence types as per Rule 13 of FRA Rules
        self.evidence_keywords = {
            'voter_id': ['voter identity card', 'voter id', 'epic', 'electoral', 'voter card'],
            'ration_card': ['ration card', 'ration', 'pds card', 'food card'],
            'census': ['census', 'survey settlement', 'revenue records', 'land records'],
            'government_orders': ['government order', 'go', 'notification', 'gazette'],
            'court_judgments': ['judgment', 'court order', 'decree', 'court case'],
            'maps': ['map', 'survey map', 'settlement map', 'cadastral', 'khasra'],
            'oral_evidence': ['statement of elders', 'oral evidence', 'community testimony', 'elder statement'],
            'physical_evidence': ['structures', 'cultivation', 'habitation', 'dwelling'],
            'other_documents': ['affidavit', 'self declaration', 'certificate', 'license']
        }
        
        # Mandatory fields by document type
        self.mandatory_fields = {
            DocumentType.FORM_A: [
                'claim_number', 'claimant_name', 'father_mother_name', 'address', 
                'village', 'gram_panchayat', 'tehsil', 'district', 'state', 'scheduled_tribe'
            ],
            DocumentType.FORM_B: [
                'claimant_name', 'village', 'gram_panchayat', 
                'tehsil', 'district', 'state'
            ],
            DocumentType.FORM_C: [
                'village', 'gram_panchayat', 'tehsil', 'district', 'state'
            ]
        }

    def perform_health_check(self, extracted_data: dict, document_type: DocumentType) -> HealthCheckResult:
        """
        Perform comprehensive health check on extracted document data.
        """
        failed_checks = []
        warnings = []
        critical_issues = []
        total_checks = 0

        # 1. Presence Checks
        presence_results = self._check_mandatory_fields(extracted_data, document_type)
        failed_checks.extend(presence_results['failed'])
        critical_issues.extend(presence_results['critical'])
        total_checks += presence_results['total']

        # 2. Evidence Checks (Critical for claim forms)
        if document_type in [DocumentType.FORM_A, DocumentType.FORM_B, DocumentType.FORM_C]:
            evidence_results = self._check_evidence_sufficiency(extracted_data)
            failed_checks.extend(evidence_results['failed'])
            warnings.extend(evidence_results['warnings'])
            total_checks += evidence_results['total']

        # 3. Format Checks
        format_results = self._check_data_formats(extracted_data)
        failed_checks.extend(format_results['failed'])
        warnings.extend(format_results['warnings'])
        total_checks += format_results['total']

        # 4. Content/Value Checks
        content_results = self._check_content_validity(extracted_data, document_type)
        failed_checks.extend(content_results['failed'])
        warnings.extend(content_results['warnings'])
        total_checks += content_results['total']

        # 5. Document-Specific Checks
        specific_results = self._check_document_specific_rules(extracted_data, document_type)
        failed_checks.extend(specific_results['failed'])
        warnings.extend(specific_results['warnings'])
        total_checks += specific_results['total']

        # Calculate score
        passed_checks = total_checks - len(failed_checks)
        score = int((passed_checks / total_checks) * 100) if total_checks > 0 else 0

        # Adjust score based on critical issues
        if critical_issues:
            score = max(0, score - len(critical_issues) * 15)  # Reduce score for critical issues

        return HealthCheckResult(
            score=score,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            warnings=warnings,
            critical_issues=critical_issues
        )

    def _check_mandatory_fields(self, data: dict, doc_type: DocumentType) -> dict:
        """Check presence of mandatory fields based on document type."""
        failed = []
        critical = []
        
        if doc_type not in self.mandatory_fields:
            return {'failed': [], 'critical': [], 'total': 0}
        
        required_fields = self.mandatory_fields[doc_type]
        
        for field in required_fields:
            if field not in data or not data[field] or data[field] == "Not Found":
                field_name = self._format_field_name(field)
                failed.append(f"{field_name} is missing or empty.")
                
                # Mark critical fields
                if field in ['claimant_name', 'village', 'district']:
                    critical.append(f"Critical: {field_name} is mandatory for processing.")
        
        return {
            'failed': failed,
            'critical': critical,
            'total': len(required_fields)
        }

    def _check_evidence_sufficiency(self, data: dict) -> dict:
        """
        Check if the claim mentions at least two forms of supporting evidence as per Rule 13.
        """
        failed = []
        warnings = []
        
        raw_text = data.get('raw_text', '').lower()
        if not raw_text:
            failed.append("No text available for evidence verification.")
            return {'failed': failed, 'warnings': warnings, 'total': 1}
        
        # Find mentioned evidence types
        mentioned_evidence = []
        evidence_details = {}
        
        for evidence_type, keywords in self.evidence_keywords.items():
            for keyword in keywords:
                if keyword in raw_text:
                    mentioned_evidence.append(evidence_type)
                    evidence_details[evidence_type] = keyword
                    break
        
        # Remove duplicates
        mentioned_evidence = list(set(mentioned_evidence))
        
        if len(mentioned_evidence) < 2:
            failed.append(
                "The claim does not mention at least two forms of supporting evidence as per Rule 13. "
                f"Found: {len(mentioned_evidence)} type(s). "
                f"Mentioned: {', '.join([self._format_evidence_name(e) for e in mentioned_evidence]) if mentioned_evidence else 'None'}"
            )
        elif len(mentioned_evidence) == 2:
            warnings.append(
                f"Minimum evidence requirement met with {len(mentioned_evidence)} types. "
                f"Consider providing additional evidence for stronger claim."
            )
        else:
            # Sufficient evidence found - this is good
            pass
        
        return {
            'failed': failed,
            'warnings': warnings,
            'total': 1,
            'evidence_found': mentioned_evidence,
            'evidence_details': evidence_details
        }

    def _check_data_formats(self, data: dict) -> dict:
        """Check format validity of extracted data."""
        failed = []
        warnings = []
        total_checks = 0
        
        # Date format checks
        date_fields = ['date_submitted', 'verification_date', 'issue_date']
        for field in date_fields:
            if field in data and data[field] != "Not Found":
                total_checks += 1
                if not self._is_valid_date_format(data[field]):
                    failed.append(f"Invalid date format in {self._format_field_name(field)}: '{data[field]}'")
        
        # Scheduled Tribe field check
        if 'scheduled_tribe' in data and data['scheduled_tribe'] != "Not Found":
            total_checks += 1
            st_value = data['scheduled_tribe'].lower().strip()
            if st_value not in ['yes', 'no', 'य़ेस', 'नो', 'हाँ', 'नहीं']:
                warnings.append(
                    f"Scheduled Tribe status unclear: '{data['scheduled_tribe']}'. "
                    "Should be clearly 'Yes' or 'No'."
                )
        
        # Area format check (for Patta documents)
        if 'area_granted' in data and data['area_granted'] != "Not Found":
            total_checks += 1
            if not self._is_valid_area_format(data['area_granted']):
                warnings.append(f"Area format may be unclear: '{data['area_granted']}'")
        
        return {
            'failed': failed,
            'warnings': warnings,
            'total': total_checks
        }

    def _check_content_validity(self, data: dict, doc_type: DocumentType) -> dict:
        """Check logical validity of content."""
        failed = []
        warnings = []
        total_checks = 0
        
        # Name validation
        if 'claimant_name' in data and data['claimant_name'] != "Not Found":
            total_checks += 1
            name = data['claimant_name'].strip()
            if len(name) < 2:
                failed.append("Claimant name appears too short to be valid.")
            elif name.lower() in ['name', 'claimant', 'applicant']:
                failed.append("Claimant name appears to be a field label rather than actual name.")
        
        # Address consistency check
        location_fields = ['village', 'gram_panchayat', 'tehsil', 'district', 'state']
        found_locations = [field for field in location_fields if field in data and data[field] != "Not Found"]
        
        if found_locations:
            total_checks += 1
            if len(found_locations) < 3:
                warnings.append(
                    f"Incomplete address information. Found: {', '.join([self._format_field_name(f) for f in found_locations])}"
                )
        
        # Document type consistency
        if 'claim_type' in data and data['claim_type'] != "Not Found":
            total_checks += 1
            claimed_type = data['claim_type'].upper()
            expected_patterns = {
                DocumentType.FORM_A: ['FORM-A', 'FORM A'],
                DocumentType.FORM_B: ['FORM-B', 'FORM B'],
                DocumentType.FORM_C: ['FORM-C', 'FORM C']
            }
            
            if doc_type in expected_patterns:
                if not any(pattern in claimed_type for pattern in expected_patterns[doc_type]):
                    warnings.append(
                        f"Document type mismatch. Detected as {doc_type.value} but form shows '{data['claim_type']}'"
                    )
        
        return {
            'failed': failed,
            'warnings': warnings,
            'total': total_checks
        }

    def _check_document_specific_rules(self, data: dict, doc_type: DocumentType) -> dict:
        """Apply document-type specific validation rules."""
        failed = []
        warnings = []
        total_checks = 0
        
        if doc_type == DocumentType.FORM_A:
            # Individual rights specific checks
            total_checks += 1
            if 'scheduled_tribe' in data and data['scheduled_tribe'] == "Not Found":
                failed.append("Form-A requires clear indication of Scheduled Tribe or OTFD status.")
            
        elif doc_type == DocumentType.FORM_B:
            # Community rights specific checks
            total_checks += 1
            raw_text = data.get('raw_text', '').lower()
            community_indicators = ['community', 'nistar', 'grazing', 'minor forest produce', 'water body']
            if not any(indicator in raw_text for indicator in community_indicators):
                warnings.append("Form-B should clearly mention community rights being claimed.")
                
        elif doc_type == DocumentType.FORM_C:
            # CFR specific checks
            total_checks += 1
            raw_text = data.get('raw_text', '').lower()
            cfr_indicators = ['gram sabha', 'community forest resource', 'protect', 'conserve', 'manage']
            if not any(indicator in raw_text for indicator in cfr_indicators):
                warnings.append("Form-C should clearly mention Gram Sabha and forest resource management.")
        
        elif doc_type == DocumentType.VERIFICATION:
            # Verification document checks
            total_checks += 1
            if 'committee_type' in data and data['committee_type'] == "Not Found":
                failed.append("Verification document should clearly indicate the committee type (Gram Sabha/SDLC/DLC).")
            
            if 'recommendation' in data and data['recommendation'] == "Not Found":
                warnings.append("Verification document should clearly state the committee's recommendation.")
        
        elif doc_type in [DocumentType.INDIVIDUAL_PATTA, DocumentType.COMMUNITY_PATTA, DocumentType.CFR_PATTA]:
            # Patta document checks
            total_checks += 1
            if 'title_number' in data and data['title_number'] == "Not Found":
                failed.append("Patta document should have a clear title/reference number.")
            
            if 'area_granted' in data and data['area_granted'] == "Not Found":
                warnings.append("Patta should specify the area granted/confirmed.")
        
        return {
            'failed': failed,
            'warnings': warnings,
            'total': total_checks
        }

    def _is_valid_date_format(self, date_str: str) -> bool:
        """Check if date string is in valid format."""
        import re
        date_patterns = [
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{2,4}[-/]\d{1,2}[-/]\d{1,2}',  # YYYY/MM/DD or YYYY-MM-DD
        ]
        return any(re.match(pattern, date_str.strip()) for pattern in date_patterns)

    def _is_valid_area_format(self, area_str: str) -> bool:
        """Check if area string contains valid area information."""
        import re
        area_pattern = r'\d+\.?\d*\s*(hectare|acre|ha|sq\s*m|square\s*meter)'
        return bool(re.search(area_pattern, area_str.lower()))

    def _format_field_name(self, field_name: str) -> str:
        """Format field name for display."""
        return field_name.replace('_', ' ').title()

    def _format_evidence_name(self, evidence_type: str) -> str:
        """Format evidence type name for display."""
        evidence_names = {
            'voter_id': 'Voter ID Card',
            'ration_card': 'Ration Card',
            'census': 'Census/Survey Records',
            'government_orders': 'Government Orders',
            'court_judgments': 'Court Judgments',
            'maps': 'Maps/Survey Documents',
            'oral_evidence': 'Oral Evidence/Elder Statements',
            'physical_evidence': 'Physical Evidence',
            'other_documents': 'Other Supporting Documents'
        }
        return evidence_names.get(evidence_type, evidence_type.title())

# Initialize health checker
health_checker = DocumentHealthChecker()

# --- 9. API ENDPOINTS ---

@app.post("/process-document/", response_model=ProcessingResult)
async def process_single_document(
    file: UploadFile = File(...),
    document_type: Optional[DocumentType] = None,
    upload_method: UploadMethod = UploadMethod.SINGLE,
    max_pdf_pages: int = 10,
    pdf_dpi: int = 300
):
    """Process a single document (image or PDF) with enhanced OCR and document type detection."""
    start_time = datetime.now()
    
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=415, 
                detail=f"Unsupported file type: {file.content_type}. Supported types: {allowed_types}"
            )
        
        # File size validation (increased for PDFs)
        MAX_SIZE = 50 * 1024 * 1024  # 50MB for PDFs
        contents = await file.read()
        if len(contents) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="File size exceeds 50MB limit.")
        
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file received.")
        
        # Check if file is PDF
        is_pdf_file = is_pdf(contents)
        extracted_text = ""
        pdf_info = None
        
        if is_pdf_file:
            print("\nDetected PDF file, processing...")
            # Process PDF with multi-page support
            pdf_result = process_pdf_document(contents, max_pages=max_pdf_pages, dpi=pdf_dpi)
            extracted_text = pdf_result['combined_text']
            pdf_info = {
                'total_pages': pdf_result['total_pages'],
                'processed_pages': pdf_result['processed_pages'],
                'page_results': pdf_result['page_results'],
                'metadata': pdf_result['metadata']
            }
            # Store page images for verification
            page_images_b64 = pdf_result.get('page_images_base64', [])
            print(f"PDF processed: {len(pdf_result['processed_pages'])} pages extracted")
        else:
            # Extract text from image
            extracted_text = extract_text_from_image(contents, enhance_image=True)
        
        if not extracted_text:
            return ProcessingResult(
                document_type="UNKNOWN",
                confidence=0.0,
                extracted_data={"error": "No text could be extracted from the document"},
                processing_time=0.0,
                file_name=file.filename or "unknown",
                is_pdf=is_pdf_file,
                total_pages=pdf_info['total_pages'] if pdf_info else 1,
                pages_processed=pdf_info['processed_pages'] if pdf_info else []
            )
        
        # Detect document type if not provided
        if document_type is None:
            detected_type, confidence = detect_document_type(extracted_text)
        else:
            detected_type = document_type
            confidence = 0.95  # High confidence when manually specified
        
        # Parse data based on document type
        extracted_data = parse_form_data(extracted_text, detected_type)
        
        # Add PDF-specific information to extracted data
        if is_pdf_file and pdf_info:
            extracted_data['pdf_info'] = pdf_info
        
        # Perform health check
        health_check = health_checker.perform_health_check(extracted_data, detected_type)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ProcessingResult(
            document_type=detected_type.value,
            confidence=confidence,
            extracted_data=extracted_data,
            processing_time=processing_time,
            file_name=file.filename or "unknown",
            health_check=health_check,
            is_pdf=is_pdf_file,
            total_pages=pdf_info['total_pages'] if pdf_info else 1,
            pages_processed=pdf_info['processed_pages'] if pdf_info else [1],
            page_images_base64=page_images_b64 if is_pdf_file else None
        )
    
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

@app.post("/process-bulk/", response_model=BulkProcessingResult)
async def process_bulk_documents(
    files: List[UploadFile] = File(...),
    document_type: Optional[DocumentType] = None
):
    """Process multiple documents in bulk."""
    start_time = datetime.now()
    results = []
    errors = []
    processed_count = 0
    
    for file in files:
        try:
            # Reuse single document processing logic
            result = await process_single_document(file, document_type, UploadMethod.BULK)
            results.append(result)
            processed_count += 1
        except Exception as e:
            errors.append({
                "file_name": file.filename or "unknown",
                "error": str(e)
            })
    
    return BulkProcessingResult(
        total_files=len(files),
        processed_files=processed_count,
        failed_files=len(errors),
        results=results,
        errors=errors
    )

@app.post("/process-mobile/", response_model=ProcessingResult)
async def process_mobile_upload(
    file: UploadFile = File(...),
    document_type: Optional[DocumentType] = None,
    location_data: Optional[str] = Form(None)
):
    """Process document uploaded from mobile device with optional location data."""
    try:
        result = await process_single_document(file, document_type, UploadMethod.MOBILE)
        
        # Add location data if provided
        if location_data:
            try:
                location = json.loads(location_data)
                result.extracted_data["location_data"] = location
            except json.JSONDecodeError:
                result.extracted_data["location_data"] = {"error": "Invalid location data"}
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mobile processing error: {str(e)}")

@app.get("/document-types/")
async def get_document_types():
    """Get all supported document types with descriptions."""
    return {
        "FORM_A": {
            "name": "FRA Claim Form A (Individual Rights)",
            "description": "Individual claim for forest land habitation or self-cultivation"
        },
        "FORM_B": {
            "name": "FRA Claim Form B (Community Rights)",
            "description": "Community claim for nistar, minor forest produce, grazing rights"
        },
        "FORM_C": {
            "name": "FRA Claim Form C (Community Forest Resource Rights)",
            "description": "Gram Sabha claim to protect, regenerate, conserve community forest"
        },
        "VERIFICATION": {
            "name": "FRA Verification Document",
            "description": "Official verification records and committee decisions"
        },
        "INDIVIDUAL_PATTA": {
            "name": "Individual Patta (Title)",
            "description": "Individual forest rights title document"
        },
        "COMMUNITY_PATTA": {
            "name": "Community Patta (Title)",
            "description": "Community forest rights title document"
        },
        "CFR_PATTA": {
            "name": "CFR Patta (Title)",
            "description": "Community Forest Resource management title"
        },
        "SHAPEFILE": {
            "name": "Shapefile/Digital Map",
            "description": "Digital boundary maps and GIS data"
        }
    }

@app.post("/health-check/", response_model=HealthCheckResult)
async def perform_document_health_check(
    extracted_data: dict,
    document_type: DocumentType
):
    """
    Perform standalone health check on extracted document data.
    This endpoint allows for health checking of already processed documents.
    """
    try:
        health_result = health_checker.perform_health_check(extracted_data, document_type)
        return health_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check error: {str(e)}")

@app.get("/health-check/rules/")
async def get_health_check_rules():
    """Get information about health check rules and requirements."""
    return {
        "mandatory_fields": {
            "FORM_A": health_checker.mandatory_fields.get(DocumentType.FORM_A, []),
            "FORM_B": health_checker.mandatory_fields.get(DocumentType.FORM_B, []),
            "FORM_C": health_checker.mandatory_fields.get(DocumentType.FORM_C, [])
        },
        "evidence_types": {
            category: {
                "name": health_checker._format_evidence_name(category),
                "keywords": keywords
            }
            for category, keywords in health_checker.evidence_keywords.items()
        },
        "scoring_system": {
            "total_score": 100,
            "critical_issue_penalty": 15,
            "minimum_evidence_required": 2,
            "check_categories": [
                "Presence Checks - Verify mandatory fields",
                "Evidence Checks - Verify supporting evidence per Rule 13",
                "Format Checks - Validate data formats",
                "Content Checks - Verify logical content",
                "Document-Specific Checks - Type-specific validations"
            ]
        }
    }

# Legacy endpoint for backward compatibility
@app.post("/process-document-legacy/")
async def process_document_legacy(file: UploadFile = File(...)):
    """Legacy endpoint for backward compatibility."""
    try:
        result = await process_single_document(file)
        return result.extracted_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- MANUAL VERIFICATION ENDPOINTS ---

@app.post("/create-verification/")
async def create_verification(
    extracted_data: str = Form(...),
    mobile_number: str = Form(...),
    document_image: str = Form(...)
):
    """Create a new verification record for manual review."""
    try:
        session_id = str(uuid.uuid4())
        
        record = VerificationRecord(
            session_id=session_id,
            original_data=json.loads(extracted_data),
            mobile_number=mobile_number,
            created_at=datetime.now().isoformat(),
            document_image_base64=document_image
        )
        
        verification_records[session_id] = record
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Verification record created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating verification: {str(e)}")

@app.get("/verification/{session_id}")
async def get_verification(session_id: str):
    """Get verification record for review."""
    if session_id not in verification_records:
        raise HTTPException(status_code=404, detail="Verification record not found")
    
    record = verification_records[session_id]
    return {
        "session_id": record.session_id,
        "original_data": record.original_data,
        "verified_data": record.verified_data,
        "mobile_number": record.mobile_number,
        "status": record.status,
        "document_image_base64": record.document_image_base64,
        "created_at": record.created_at,
        "official_notes": record.official_notes
    }

@app.post("/submit-verification/{session_id}")
async def submit_verification(
    session_id: str,
    verified_data: str = Form(...),
    mobile_number: str = Form(...),
    official_notes: str = Form(""),
    status: str = Form("APPROVED")
):
    """Submit verified data."""
    if session_id not in verification_records:
        raise HTTPException(status_code=404, detail="Verification record not found")
    
    try:
        record = verification_records[session_id]
        record.verified_data = json.loads(verified_data)
        record.mobile_number = mobile_number
        record.official_notes = official_notes
        record.status = VerificationStatus(status)
        record.verified_at = datetime.now().isoformat()
        
        return {
            "success": True,
            "session_id": session_id,
            "status": status,
            "message": f"Verification {status.lower()} successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error submitting verification: {str(e)}")

@app.get("/verifications/")
async def list_verifications():
    """List all verification records."""
    records = []
    for session_id, record in verification_records.items():
        records.append({
            "session_id": record.session_id,
            "status": record.status,
            "mobile_number": record.mobile_number,
            "created_at": record.created_at,
            "verified_at": record.verified_at
        })
    
    return {"records": records}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)