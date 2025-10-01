# Forest Rights Atlas - OCR Document Intelligence System

## Overview
Advanced OCR system for Forest Rights Act (FRA) document processing with automated health checking and manual verification workflows.

## Features

### 🔍 Document Processing
- **8 Document Types**: FORM_A, FORM_B, FORM_C, VERIFICATION, INDIVIDUAL_PATTA, COMMUNITY_PATTA, CFR_PATTA, SHAPEFILE
- **Advanced OCR**: PaddleOCR with multi-language support
- **Auto Detection**: Smart document type recognition

### 📤 Upload Methods
- **Single Document**: Direct file upload with drag & drop
- **Bulk Processing**: Multiple file processing
- **Mobile Camera**: Real-time camera capture with GPS location

### 🏥 Document Health Check
- **Automated Pre-Scrutiny**: FRA Act compliance validation
- **5-Category Validation**: Mandatory fields, supporting evidence, format compliance
- **Health Scoring**: 0-100% score with actionable recommendations
- **Issue Detection**: Critical, failed, and warning categories

### ✅ Manual Verification
- **Human-in-the-loop**: Official review workflow
- **Session Management**: Track verification progress
- **Side-by-side Interface**: Document image + editable form
- **Approval Workflow**: Approve, flag, or reject with notes

## Project Structure

```
ocr/
├── main.py              # FastAPI backend server
├── index.html           # Main frontend interface
├── script.js            # Frontend JavaScript logic
├── requirements.txt     # Python dependencies
├── fra_documents.db     # SQLite database
├── .gitignore          # Git ignore rules
└── venv/               # Virtual environment
```

## Installation

1. **Create Virtual Environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # or
   source venv/bin/activate  # Linux/Mac
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Server**
   ```bash
   python main.py
   ```

4. **Access Application**
   Open browser to: http://localhost:8000

## API Endpoints

### Core Processing
- `GET /` - API health check
- `GET /document-types/` - Available document types
- `POST /process-single-document/` - Process single file
- `POST /process-bulk-documents/` - Process multiple files

### Manual Verification
- `POST /create-verification-session/` - Create verification session
- `GET /get-verification-session/{id}` - Retrieve session details
- `POST /submit-verification/` - Submit verification results
- `GET /get-verification-sessions/` - List all sessions

## Usage

### Document Processing
1. Select document type or enable auto-detection
2. Choose upload method (Single, Bulk, or Mobile Camera)
3. Upload files or capture photos
4. Review OCR results and health check scores
5. Access manual verification if needed

### Health Check System
The system automatically validates documents against FRA Act requirements:
- **Mandatory Fields**: Ensures all required information is present
- **Supporting Evidence**: Validates Rule 13 compliance
- **Format Compliance**: Checks document structure
- **Data Quality**: Assesses information accuracy
- **Completeness**: Verifies submission requirements

### Manual Verification
For documents requiring official review:
1. Click "Start Manual Verification" on processed documents
2. Review extracted data in editable form
3. Compare with original document image
4. Add official notes and approve/flag/reject
5. Submit verification decision

## Technical Specifications

- **Backend**: FastAPI 2.0.0 with Python 3.13
- **OCR Engine**: PaddleOCR with multiple model support
- **Frontend**: Vanilla JavaScript with modern UI
- **Database**: SQLite for verification sessions
- **File Support**: JPEG, PNG, PDF (max 25MB)
- **Processing**: Real-time OCR with health scoring

## Development

### Server Development
- Main application logic in `main.py`
- Document type detection and health checking
- Verification session management
- API endpoint definitions

### Frontend Development
- Modern responsive design in `index.html`
- Interactive functionality in `script.js`
- Glass-morphism UI with animations
- Real-time status updates

## License
This project is developed for Forest Rights Act document processing and compliance.

## Support
For technical support or feature requests, please contact the development team.