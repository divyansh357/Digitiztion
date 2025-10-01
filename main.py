# main.py - ENHANCED VERSION WITH MULTIPLE DOCUMENT TYPES
import io
import re
import cv2
import os
import zipfile
import numpy as np
import uuid
import base64
from typing import List, Optional
from enum import Enum
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from paddleocr import PaddleOCR
import json
from datetime import datetime

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
print("Loading models into memory...")
ocr_engine = PaddleOCR(use_textline_orientation=True, lang='en')
print("Models loaded successfully!")

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

# --- 6. ENHANCED TEXT EXTRACTION ---
def extract_text_from_image(image_bytes: bytes, enhance_image: bool = True) -> str:
    """Enhanced OCR with image preprocessing."""
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if enhance_image:
            # Image preprocessing for better OCR
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Noise removal
            denoised = cv2.medianBlur(gray, 3)
            
            # Contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(denoised)
            
            # Convert back to BGR for PaddleOCR
            img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        
        result = ocr_engine.predict(img)
        if result and result[0] is not None:
            # Handle different PaddleOCR output formats
            if isinstance(result[0], list):
                recognized_texts = [item[1][0] for item in result[0] if len(item) > 1]
            else:
                recognized_texts = result[0].get('rec_texts', [])
            
            full_text = "\n".join(recognized_texts)
            return full_text
        return ""
    except Exception as e:
        print(f"OCR extraction error: {e}")
        return ""

# --- 7. DOCUMENT-SPECIFIC PARSERS ---
def parse_form_data(text: str, doc_type: DocumentType) -> dict:
    """Parse data specific to different document types."""
    base_data = {
        "claimant_name": "Not Found",
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
    
    # Common field extraction
    patterns = {
        "claimant_name": [
            r"(?i)(?:Name of the claimant \(s\)|claimant|name)[\s:-]*(.+)",
            r"(?i)applicant.*name[\s:-]*(.+)",
            r"(?i)श्री[\s]*(.+)",  # Hindi prefix
        ],
        "address": [
            r"(?i)address[\s:-]*(.+)",
            r"(?i)पता[\s:-]*(.+)",  # Hindi
        ],
        "village": [
            r"(?i)village[\s:-]*(.+)",
            r"(?i)गांव[\s:-]*(.+)",  # Hindi
        ],
        "gram_panchayat": [
            r"(?i)gram panchayat[\s:-]*(.+)",
            r"(?i)ग्राम पंचायत[\s:-]*(.+)",  # Hindi
        ],
        "tehsil": [
            r"(?i)(?:tehsil|taluka)[\s:-]*(.+)",
            r"(?i)तहसील[\s:-]*(.+)",  # Hindi
        ],
        "district": [
            r"(?i)district[\s:-]*(.+)",
            r"(?i)जिला[\s:-]*(.+)",  # Hindi
        ],
        "state": [
            r"(?i)state[\s:-]*(.+)",
            r"(?i)राज्य[\s:-]*(.+)",  # Hindi
        ],
        "date_submitted": [
            r"(?i)date[\s:-]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            r"(?i)submitted.*on[\s:-]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        ],
        "scheduled_tribe": [
            r"(?i)scheduled tribe[\s:/\-No]*(Yes|No)",
            r"(?i)st[\s]*category[\s:/\-]*(Yes|No)",
        ]
    }
    
    # Extract common fields
    for field, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, text)
            if match:
                base_data[field] = match.group(1).strip()
                break
    
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
                'claimant_name', 'address', 'village', 'gram_panchayat', 
                'tehsil', 'district', 'state', 'scheduled_tribe'
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
    upload_method: UploadMethod = UploadMethod.SINGLE
):
    """Process a single document with enhanced OCR and document type detection."""
    start_time = datetime.now()
    
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=415, 
                detail=f"Unsupported file type: {file.content_type}. Supported types: {allowed_types}"
            )
        
        # File size validation (increased for better quality)
        MAX_SIZE = 25 * 1024 * 1024  # 25MB
        contents = await file.read()
        if len(contents) > MAX_SIZE:
            raise HTTPException(status_code=413, detail="File size exceeds 25MB limit.")
        
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file received.")
        
        # Extract text
        extracted_text = extract_text_from_image(contents, enhance_image=True)
        
        if not extracted_text:
            return ProcessingResult(
                document_type="UNKNOWN",
                confidence=0.0,
                extracted_data={"error": "No text could be extracted from the image"},
                processing_time=0.0,
                file_name=file.filename or "unknown"
            )
        
        # Detect document type if not provided
        if document_type is None:
            detected_type, confidence = detect_document_type(extracted_text)
        else:
            detected_type = document_type
            confidence = 0.95  # High confidence when manually specified
        
        # Parse data based on document type
        extracted_data = parse_form_data(extracted_text, detected_type)
        
        # Perform health check
        health_check = health_checker.perform_health_check(extracted_data, detected_type)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ProcessingResult(
            document_type=detected_type.value,
            confidence=confidence,
            extracted_data=extracted_data,
            processing_time=processing_time,
            file_name=file.filename or "unknown",
            health_check=health_check
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