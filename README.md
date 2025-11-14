# Forest Rights Atlas - OCR Document Intelligence System

## Overview
Advanced OCR system for Forest Rights Act (FRA) document processing with automated health checking and manual verification workflows.

## Technology Stack

### Backend Technologies
- **FastAPI** - Modern, high-performance Python web framework for building APIs
- **Uvicorn** - Lightning-fast ASGI server implementation
- **PaddleOCR** (v3.2.0+) - Advanced OCR engine with multi-language support
- **PaddlePaddle** (v3.2.0+) - Deep learning framework powering OCR models
- **OpenCV** (cv2) - Computer vision library for image preprocessing
- **NumPy** - Numerical computing for array operations
- **Pillow (PIL)** - Python Imaging Library for image manipulation
- **Pydantic** (v2.0+) - Data validation using Python type annotations
- **SQLite** - Lightweight database for document storage

### Frontend Technologies
- **HTML5** - Modern semantic markup
- **CSS3** - Advanced styling with CSS Variables and Flexbox/Grid
- **Vanilla JavaScript (ES6+)** - Native browser JavaScript without frameworks
- **Font Awesome** (v6.4.0) - Icon library for UI elements
- **Animate.css** (v4.1.1) - CSS animation library

### Image Processing Pipeline
- **cv2.medianBlur** - Noise removal from scanned documents
- **CLAHE** (Contrast Limited Adaptive Histogram Equalization) - Image enhancement
- **Grayscale conversion** - Preprocessing for better OCR accuracy
- **Base64 encoding** - Image data transmission

### APIs & Communication
- **RESTful API** - Standard HTTP methods (GET, POST)
- **CORS Middleware** - Cross-Origin Resource Sharing support
- **JSON** - Data interchange format
- **Multipart Form Data** - File upload handling

### Development Tools
- **Python 3.8+** - Core programming language
- **pip** - Package management
- **Virtual Environment (venv)** - Isolated Python environment
- **Git** - Version control system

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

## Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git (for cloning the repository)

### Step-by-Step Installation

1. **Clone the Repository**
   ```powershell
   git clone https://github.com/divyansh357/Digitiztion.git
   cd Digitiztion
   ```

2. **Create Virtual Environment**
   ```powershell
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment (Windows PowerShell)
   .\venv\Scripts\Activate.ps1
   
   # If you encounter execution policy error, run:
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

3. **Install Dependencies**
   ```powershell
   # Upgrade pip first
   python -m pip install --upgrade pip
   
   # Install all required packages
   pip install -r requirements.txt
   ```

4. **Start the Server**
   ```powershell
   # Run the FastAPI server
   python main.py
   # Go live with index.html(actual interface)
   
   # Server will start on http://localhost:8000
   # You should see: "Uvicorn running on http://0.0.0.0:8000"
   ```

5. **Access the Application**
   - Open your web browser
   - Navigate to: **http://localhost:8000**
   - The main interface will load automatically

6. # To exit the virtual environment
     deactivate

### Troubleshooting

**Virtual Environment Activation Issues:**
```powershell
# If .\venv\Scripts\Activate.ps1 doesn't work, try:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

**Port Already in Use:**
```powershell
# If port 8000 is busy, modify main.py or kill the process:
netstat -ano | findstr :8000
taskkill /PID <process_id> /F
```

**Missing Dependencies:**
```powershell
# Reinstall all dependencies
pip install --upgrade -r requirements.txt
```

### Quick Start (All-in-One)
```powershell
# Clone, setup, and run in one go
git clone https://github.com/divyansh357/Digitiztion.git; cd Digitiztion; python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt; python main.py
```

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
