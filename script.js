// Enhanced JavaScript for FRA Document Processing System

class FRADocumentProcessor {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8000';
        this.selectedDocumentType = null;
        this.autoDetect = true;
        this.cameraStream = null;
        this.supportedDocumentTypes = {};
        
        this.init();
    }

    async init() {
        await this.checkApiStatus();
        await this.loadDocumentTypes();
        this.setupEventListeners();
        this.setupDropZones();
    }

    // API Status Check
    async checkApiStatus() {
        const statusIndicator = document.getElementById('apiStatus');
        const statusText = document.getElementById('statusText');

        try {
            console.log('Checking API status...');
            const response = await fetch(`${this.apiBaseUrl}/`);
            const data = await response.json();
            console.log('API response:', data);
            
            if (response.ok) {
                statusIndicator.classList.remove('offline');
                statusText.textContent = `API v${data.version} - Online`;
                this.showToast('API connection established', 'success');
                console.log('✅ API connected successfully');
            } else {
                throw new Error('API responded with error');
            }
        } catch (error) {
            console.error('❌ API connection failed:', error);
            statusIndicator.classList.add('offline');
            statusText.textContent = 'API Offline';
            this.showToast('Unable to connect to API. Please check if the server is running.', 'error');
        }
    }

    // Load Document Types
    async loadDocumentTypes() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/document-types/`);
            const types = await response.json();
            this.supportedDocumentTypes = types;
            this.renderDocumentTypes(types);
        } catch (error) {
            console.error('Failed to load document types:', error);
            this.showToast('Failed to load document types', 'error');
        }
    }

    // Render Document Types
    renderDocumentTypes(types) {
        const grid = document.getElementById('documentTypesGrid');
        grid.innerHTML = '';

        Object.entries(types).forEach(([key, info]) => {
            const card = document.createElement('div');
            card.className = 'document-type-card';
            card.dataset.type = key;
            
            card.innerHTML = `
                <div class="document-type-title">${info.name}</div>
                <div class="document-type-description">${info.description}</div>
            `;

            card.addEventListener('click', () => this.selectDocumentType(key, card));
            grid.appendChild(card);
        });
    }

    // Select Document Type
    selectDocumentType(type, cardElement) {
        // Remove previous selection and any faded/invisible state
        document.querySelectorAll('.document-type-card.selected').forEach(card => {
            card.classList.remove('selected');
            card.classList.remove('invisible');
            card.style.opacity = '';
            card.style.filter = '';
        });

        // Add selection to current card and ensure visible
        cardElement.classList.add('selected');
        cardElement.classList.remove('invisible');
        cardElement.style.opacity = '1';
        cardElement.style.filter = 'none';
        this.selectedDocumentType = type;

        // Disable auto-detect when manually selected
        document.getElementById('autoDetect').checked = false;
        this.autoDetect = false;

        this.showToast(`Selected: ${this.supportedDocumentTypes[type].name}`, 'success');
    }

    // Setup Event Listeners
    setupEventListeners() {
        // Auto-detect checkbox
        document.getElementById('autoDetect').addEventListener('change', (e) => {
            this.autoDetect = e.target.checked;
            if (this.autoDetect) {
                this.selectedDocumentType = null;
                document.querySelectorAll('.document-type-card.selected').forEach(card => {
                    card.classList.remove('selected');
                });
            }
        });

        // File inputs
        document.getElementById('singleFileInput').addEventListener('change', (e) => {
            this.handleSingleFile(e.target.files[0]);
        });

        document.getElementById('bulkFileInput').addEventListener('change', (e) => {
            this.handleBulkFiles(Array.from(e.target.files));
        });

        // Mobile camera
        document.getElementById('mobileDropZone').addEventListener('click', () => {
            this.startCamera();
        });

        document.getElementById('captureBtn').addEventListener('click', () => {
            this.capturePhoto();
        });

        document.getElementById('cancelCameraBtn').addEventListener('click', () => {
            this.stopCamera();
        });
    }

    // Setup Drop Zones
    setupDropZones() {
        console.log('Setting up drop zones...');
        const dropZones = [
            { id: 'singleDropZone', handler: (files) => this.handleSingleFile(files[0]) },
            { id: 'bulkDropZone', handler: (files) => this.handleBulkFiles(files) }
        ];

        dropZones.forEach(({ id, handler }) => {
            const dropZone = document.getElementById(id);
            console.log(`Setting up drop zone: ${id}`, dropZone);
            
            if (!dropZone) {
                console.error(`❌ Drop zone not found: ${id}`);
                return;
            }
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, this.preventDefaults, false);
            });

            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
            });

            dropZone.addEventListener('drop', (e) => {
                console.log(`Files dropped on ${id}:`, e.dataTransfer.files);
                const files = Array.from(e.dataTransfer.files);
                handler(files);
            }, false);

            dropZone.addEventListener('click', () => {
                console.log(`Drop zone clicked: ${id}`);
                const input = dropZone.parentElement.querySelector('.file-input');
                console.log(`Found file input:`, input);
                if (input) {
                    input.click();
                } else {
                    console.error(`❌ File input not found for ${id}`);
                }
            });
        });
        console.log('✅ Drop zones setup complete');
    }

    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Camera Functions
    async startCamera() {
        try {
            this.cameraStream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: 'environment' } // Use back camera on mobile
            });
            
            const video = document.getElementById('cameraVideo');
            video.srcObject = this.cameraStream;
            
            document.getElementById('cameraPreview').style.display = 'block';
            document.getElementById('cameraControls').classList.remove('hidden');
            document.getElementById('mobileDropZone').style.display = 'none';
            
        } catch (error) {
            console.error('Error accessing camera:', error);
            this.showToast('Unable to access camera. Please check permissions.', 'error');
        }
    }

    capturePhoto() {
        const video = document.getElementById('cameraVideo');
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0);

        canvas.toBlob((blob) => {
            const file = new File([blob], 'camera-capture.jpg', { type: 'image/jpeg' });
            this.stopCamera();
            this.handleMobileFile(file);
        }, 'image/jpeg', 0.95);
    }

    stopCamera() {
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach(track => track.stop());
            this.cameraStream = null;
        }
        
        document.getElementById('cameraPreview').style.display = 'none';
        document.getElementById('cameraControls').classList.add('hidden');
        document.getElementById('mobileDropZone').style.display = 'block';
    }

    // File Handling
    // File to Base64 conversion
    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result.split(',')[1]); // Remove data:image/...;base64, prefix
            reader.onerror = error => reject(error);
        });
    }

    async handleSingleFile(file) {
        if (!file) return;
        
        if (!this.validateFile(file)) return;

        this.showProcessingSection();
        this.updateProgress(0);

        try {
            // Convert file to base64 for verification purposes
            const imageBase64 = await this.fileToBase64(file);
            const result = await this.processFile(file, 'single');
            
            // Add the image data to the result for verification
            result.document_image_base64 = imageBase64;
            
            this.displayResults([result]);
            this.updateProgress(100);
        } catch (error) {
            this.handleProcessingError(error, file.name);
        }
    }

    async handleBulkFiles(files) {
        if (!files || files.length === 0) return;

        const validFiles = files.filter(file => this.validateFile(file, false));
        if (validFiles.length === 0) {
            this.showToast('No valid files selected', 'warning');
            return;
        }

        this.showProcessingSection();
        this.updateProgress(0);

        try {
            const results = await this.processBulkFiles(validFiles);
            
            // Add image data for each result in bulk processing
            for (let i = 0; i < results.results.length; i++) {
                if (i < validFiles.length) {
                    try {
                        results.results[i].document_image_base64 = await this.fileToBase64(validFiles[i]);
                    } catch (error) {
                        console.error('Failed to convert file to base64:', error);
                    }
                }
            }
            
            this.displayBulkResults(results);
            this.updateProgress(100);
        } catch (error) {
            this.handleProcessingError(error, 'bulk processing');
        }
    }

    async handleMobileFile(file) {
        if (!file) return;

        this.showProcessingSection();
        this.updateProgress(0);

        try {
            // Get location if available
            let locationData = null;
            if (navigator.geolocation) {
                try {
                    const position = await new Promise((resolve, reject) => {
                        navigator.geolocation.getCurrentPosition(resolve, reject);
                    });
                    locationData = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        timestamp: new Date().toISOString()
                    };
                } catch (error) {
                    console.log('Location not available:', error);
                }
            }

            // Convert file to base64 for verification purposes
            const imageBase64 = await this.fileToBase64(file);
            const result = await this.processFile(file, 'mobile', locationData);
            
            // Add the image data to the result for verification
            result.document_image_base64 = imageBase64;
            
            this.displayResults([result]);
            this.updateProgress(100);
        } catch (error) {
            this.handleProcessingError(error, file.name);
        }
    }

    // File Validation
    validateFile(file, showToast = true) {
        const maxSize = 25 * 1024 * 1024; // 25MB
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];

        if (file.size > maxSize) {
            if (showToast) this.showToast(`File ${file.name} is too large. Maximum size is 25MB.`, 'error');
            return false;
        }

        if (!allowedTypes.includes(file.type)) {
            if (showToast) this.showToast(`File ${file.name} has unsupported format. Please use JPEG, PNG, or PDF.`, 'error');
            return false;
        }

        return true;
    }

    // File Processing
    async processFile(file, method, locationData = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        if (!this.autoDetect && this.selectedDocumentType) {
            formData.append('document_type', this.selectedDocumentType);
        }

        let endpoint = '/process-document/';
        if (method === 'mobile') {
            endpoint = '/process-mobile/';
            if (locationData) {
                formData.append('location_data', JSON.stringify(locationData));
            }
        }

        const response = await fetch(`${this.apiBaseUrl}${endpoint}`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Processing failed');
        }

        return await response.json();
    }

    async processBulkFiles(files) {
        const formData = new FormData();
        files.forEach(file => formData.append('files', file));
        
        if (!this.autoDetect && this.selectedDocumentType) {
            formData.append('document_type', this.selectedDocumentType);
        }

        const response = await fetch(`${this.apiBaseUrl}/process-bulk/`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Bulk processing failed');
        }

        return await response.json();
    }

    // UI Updates
    showProcessingSection() {
        const section = document.getElementById('processingSection');
        section.style.display = 'block';
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
        // Reset results
        document.getElementById('resultsGrid').innerHTML = '';
        document.getElementById('processingStatus').style.display = 'block';
    }

    updateProgress(percentage) {
        document.getElementById('progressFill').style.width = `${percentage}%`;
        
        if (percentage === 100) {
            setTimeout(() => {
                document.getElementById('processingStatus').style.display = 'none';
            }, 500);
        }
    }

    displayResults(results) {
        const grid = document.getElementById('resultsGrid');
        
        results.forEach((result, index) => {
            const card = this.createResultCard(result, index);
            grid.appendChild(card);
        });
    }

    displayBulkResults(bulkResult) {
        const grid = document.getElementById('resultsGrid');
        
        // Add summary card
        const summaryCard = document.createElement('div');
        summaryCard.className = 'result-card';
        summaryCard.innerHTML = `
            <div class="result-header">
                <div class="result-title">Bulk Processing Summary</div>
            </div>
            <div class="extracted-data">
                <div class="data-field">
                    <div class="field-label">Total Files</div>
                    <div class="field-value">${bulkResult.total_files}</div>
                </div>
                <div class="data-field">
                    <div class="field-label">Processed Successfully</div>
                    <div class="field-value text-success">${bulkResult.processed_files}</div>
                </div>
                <div class="data-field">
                    <div class="field-label">Failed</div>
                    <div class="field-value text-danger">${bulkResult.failed_files}</div>
                </div>
            </div>
        `;
        grid.appendChild(summaryCard);

        // Add individual results
        bulkResult.results.forEach((result, index) => {
            const card = this.createResultCard(result, index);
            grid.appendChild(card);
        });

        // Add error cards if any
        bulkResult.errors.forEach(error => {
            const errorCard = document.createElement('div');
            errorCard.className = 'result-card error';
            errorCard.innerHTML = `
                <div class="result-header">
                    <div class="result-title text-danger">${error.file_name} - Error</div>
                </div>
                <div class="field-value text-danger">${error.error}</div>
            `;
            grid.appendChild(errorCard);
        });
    }
    
    renderHealthIssues(healthCheck) {
        if (!healthCheck) {
            return '<div class="health-issues"><p>No health check data available</p></div>';
        }
        
        let html = '';
        
        // Critical Issues
        if (healthCheck.critical_issues && healthCheck.critical_issues.length > 0) {
            html += `
                <div class="health-issues critical">
                    <h5><i class="fas fa-exclamation-triangle"></i> Critical Issues</h5>
                    <ul>
                        ${healthCheck.critical_issues.map(issue => `<li>${issue}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // Failed Checks
        if (healthCheck.failed_checks && healthCheck.failed_checks.length > 0) {
            html += `
                <div class="health-issues failed">
                    <h5><i class="fas fa-times-circle"></i> Failed Checks</h5>
                    <ul>
                        ${healthCheck.failed_checks.map(issue => `<li>${issue}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // Warnings
        if (healthCheck.warnings && healthCheck.warnings.length > 0) {
            html += `
                <div class="health-issues warnings">
                    <h5><i class="fas fa-exclamation-circle"></i> Warnings</h5>
                    <ul>
                        ${healthCheck.warnings.map(warning => `<li>${warning}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        return html;
    }

    renderExtractedData(data) {
        const excludeFields = ['raw_text', 'location_data'];
        let html = '';

        Object.entries(data).forEach(([key, value]) => {
            if (excludeFields.includes(key)) return;

            const isNotFound = value === 'Not Found' || value === '';
            const fieldClass = isNotFound ? 'field-value not-found' : 'field-value';

            html += `
                <div class="data-field">
                    <div class="field-label">${this.formatFieldName(key)}</div>
                    <div class="${fieldClass}">${value || 'Not Found'}</div>
                </div>
            `;
        });

        // Add location data if present
        if (data.location_data && !data.location_data.error) {
            html += `
                <div class="data-field">
                    <div class="field-label">Location</div>
                    <div class="field-value">
                        ${data.location_data.latitude.toFixed(6)}, ${data.location_data.longitude.toFixed(6)}
                        <br><small>Accuracy: ${data.location_data.accuracy}m</small>
                    </div>
                </div>
            `;
        }

        return html;
    }

    formatFieldName(fieldName) {
        return fieldName
            .replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase());
    }

    getDocumentTypeName(type) {
        if (type === 'UNKNOWN') return 'Unknown Document Type';
        return this.supportedDocumentTypes[type]?.name || type;
    }

    handleProcessingError(error, filename) {
        console.error('Processing error:', error);
        this.showToast(`Error processing ${filename}: ${error.message}`, 'error');
        
        const grid = document.getElementById('resultsGrid');
        const errorCard = document.createElement('div');
        errorCard.className = 'result-card error';
        errorCard.innerHTML = `
            <div class="result-header">
                <div class="result-title text-danger">Processing Error</div>
            </div>
            <div class="field-value text-danger">${error.message}</div>
        `;
        grid.appendChild(errorCard);
        
        this.updateProgress(100);
    }



    // Enhanced result card with verification option
    createResultCard(result, index = 0) {
        const card = document.createElement('div');
        card.className = 'result-card';
        
        // Generate a unique session ID for verification
        const sessionId = `session_${Date.now()}_${index}`;
        
        // Get mobile number from form or set default
        const mobileNumber = "Not provided"; // You can get this from the form if needed
        
        card.innerHTML = `
            <div class="result-header">
                <div class="result-title">Document ${index + 1}</div>
                <div class="document-type-badge">${result.document_type}</div>
            </div>
            
            <div class="health-check-section">
                ${result.health_check ? `
                    <div class="health-check-header">
                        <h4>Document Health Check</h4>
                        <div class="health-score ${this.getScoreClass(result.health_check.score)}">
                            ${result.health_check.score}%
                        </div>
                    </div>
                    <div class="health-summary">
                        <div class="health-stat">
                            <i class="fas fa-check-circle" style="color: var(--success-color)"></i>
                            <span>Passed: ${result.health_check.passed_checks || 0}</span>
                        </div>
                        <div class="health-stat">
                            <i class="fas fa-exclamation-triangle" style="color: var(--warning-color)"></i>
                            <span>Warnings: ${result.health_check.warnings?.length || 0}</span>
                        </div>
                        <div class="health-stat">
                            <i class="fas fa-times-circle" style="color: var(--danger-color)"></i>
                            <span>Failed: ${result.health_check.failed_checks?.length || 0}</span>
                        </div>
                    </div>
                    ${this.renderHealthIssues(result.health_check)}
                ` : '<p>No health check data available</p>'}
            </div>

            <div class="extracted-data">
                <h4>Extracted Data</h4>
                ${Object.entries(result.extracted_data).map(([key, value]) => `
                    <div class="field-group">
                        <div class="field-label">${this.formatFieldName(key)}</div>
                        <div class="field-value">${value || 'Not found'}</div>
                    </div>
                `).join('')}
            </div>
            
            <div class="verification-actions" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e5e7eb;">
                <button class="btn btn-primary verification-btn" data-session-id="${sessionId}" data-mobile="${mobileNumber}">
                    <i class="fas fa-user-check"></i>
                    Start Manual Verification
                </button>
            </div>
        `;

        // Store the result data for verification
        card.resultData = result;
        
        // Add event listener for verification button
        const verificationBtn = card.querySelector('.verification-btn');
        if (verificationBtn) {
            verificationBtn.addEventListener('click', () => {
                this.startVerification(result.extracted_data, result.document_image_base64 || '');
            });
        }

        return card;
    }

    // --- MANUAL VERIFICATION METHODS ---
    
    startVerification(extractedData, documentImageBase64) {
        // Handle the extracted data safely - it should already be an object
        const data = extractedData;
        
        // Show verification section
        const verificationSection = document.getElementById('verificationSection');
        if (verificationSection) {
            verificationSection.style.display = 'block';
            verificationSection.scrollIntoView({ behavior: 'smooth' });
            
            // Populate the verification form
            this.populateVerificationForm(data, documentImageBase64);
        } else {
            this.showToast('Verification section not found', 'error');
        }
    }
    
    populateVerificationForm(data, documentImageBase64) {
        // Set the document image
        const documentImage = document.getElementById('verificationDocumentImage');
        if (documentImage && documentImageBase64) {
            documentImage.src = `data:image/jpeg;base64,${documentImageBase64}`;
            
            // Initialize zoom functionality
            this.initializeImageZoom();
        }
        
        // Populate form fields with extracted data
        const fieldMappings = {
            // Basic Information
            'claimantName': ['claimant_name', 'applicant_name', 'name', 'full_name'],
            'claimType': ['claim_type'],
            
            // Address Information
            'address': ['address'],
            'village': ['village'],
            'gramPanchayat': ['gram_panchayat'],
            'tehsil': ['tehsil'],
            'district': ['district'],
            'state': ['state'],
            
            // Claim Details
            'dateSubmitted': ['date_submitted', 'submission_date', 'date'],
            'claimStatus': ['claim_status'],
            'scheduledTribe': ['scheduled_tribe'],
            
            // Land Information
            'surveyNumber': ['survey_number', 'plot_number'],
            'titleNumber': ['title_number'],
            'areaGranted': ['area_granted', 'area', 'land_area'],
            'issueDate': ['issue_date'],
            
            // Verification Information
            'committeeType': ['committee_type'],
            'resolutionNumber': ['resolution_number'],
            'verificationDate': ['verification_date'],
            'recommendation': ['recommendation']
        };

        Object.entries(fieldMappings).forEach(([fieldId, possibleKeys]) => {
            const element = document.getElementById(fieldId);
            if (element) {
                for (const key of possibleKeys) {
                    if (data[key]) {
                        element.value = data[key];
                        break;
                    }
                }
            }
        });
        
        // Store the image data for submission
        this.currentVerificationData = {
            extractedData: data,
            documentImageBase64: documentImageBase64
        };
    }
    
    async submitVerification(status) {
        try {
            const form = document.getElementById('verificationForm');
            const formData = new FormData(form);
            
            // Collect all verified data from form
            const verifiedData = {
                // Basic Information
                claimant_name: formData.get('claimant_name'),
                claim_type: formData.get('claim_type'),
                
                // Address Information
                address: formData.get('address'),
                village: formData.get('village'),
                gram_panchayat: formData.get('gram_panchayat'),
                tehsil: formData.get('tehsil'),
                district: formData.get('district'),
                state: formData.get('state'),
                
                // Claim Details
                date_submitted: formData.get('date_submitted'),
                claim_status: formData.get('claim_status'),
                scheduled_tribe: formData.get('scheduled_tribe'),
                
                // Land Information
                survey_number: formData.get('survey_number'),
                title_number: formData.get('title_number'),
                area_granted: formData.get('area_granted'),
                issue_date: formData.get('issue_date'),
                
                // Verification Information
                committee_type: formData.get('committee_type'),
                resolution_number: formData.get('resolution_number'),
                verification_date: formData.get('verification_date'),
                recommendation: formData.get('recommendation'),
                
                // Contact Information
                mobile_number: formData.get('mobile_number')
            };
            
            // First create verification record
            const createFormData = new FormData();
            createFormData.append('extracted_data', JSON.stringify(this.currentVerificationData.extractedData));
            createFormData.append('mobile_number', formData.get('mobile_number'));
            createFormData.append('document_image', this.currentVerificationData.documentImageBase64);
            
            const createResponse = await fetch(`${this.apiBaseUrl}/create-verification/`, {
                method: 'POST',
                body: createFormData
            });
            
            if (!createResponse.ok) {
                throw new Error('Failed to create verification record');
            }
            
            const createResult = await createResponse.json();
            const sessionId = createResult.session_id;
            
            // Then submit verification
            const submitFormData = new FormData();
            submitFormData.append('verified_data', JSON.stringify(verifiedData));
            submitFormData.append('mobile_number', formData.get('mobile_number'));
            submitFormData.append('official_notes', formData.get('official_notes') || '');
            submitFormData.append('status', status);
            
            const submitResponse = await fetch(`${this.apiBaseUrl}/submit-verification/${sessionId}`, {
                method: 'POST',
                body: submitFormData
            });
            
            if (submitResponse.ok) {
                this.showToast(`Verification ${status.toLowerCase()} successfully`, 'success');
                
                // Reset and hide verification section
                form.reset();
                document.getElementById('verificationSection').style.display = 'none';
            } else {
                throw new Error('Failed to submit verification');
            }
            
        } catch (error) {
            this.showToast(`Error: ${error.message}`, 'error');
        }
    }

    // --- IMAGE ZOOM FUNCTIONALITY ---
    
    initializeImageZoom() {
        const image = document.getElementById('verificationDocumentImage');
        const container = document.getElementById('documentImageContainer');
        const fullscreenImage = document.getElementById('fullscreenImage');
        const fullscreenModal = document.getElementById('fullscreenModal');
        
        if (!image || !container) return;
        
        let scale = 1;
        let fullscreenScale = 1;
        const scaleStep = 0.25;
        const maxScale = 5;
        const minScale = 0.5;
        
        // Variables for panning
        let isPanning = false;
        let startX, startY, scrollLeft, scrollTop;
        
        // Zoom In Button
        document.getElementById('zoomInBtn').onclick = () => {
            if (scale < maxScale) {
                scale += scaleStep;
                image.style.transform = `scale(${scale})`;
                this.updateImageContainer(container, scale);
            }
        };
        
        // Zoom Out Button
        document.getElementById('zoomOutBtn').onclick = () => {
            if (scale > minScale) {
                scale -= scaleStep;
                image.style.transform = `scale(${scale})`;
                this.updateImageContainer(container, scale);
            }
        };
        
        // Reset Zoom Button
        document.getElementById('resetZoomBtn').onclick = () => {
            scale = 1;
            image.style.transform = `scale(${scale})`;
            this.updateImageContainer(container, scale);
            container.scrollTop = 0;
            container.scrollLeft = 0;
        };
        
        // Fullscreen Button
        document.getElementById('fullscreenBtn').onclick = () => {
            fullscreenImage.src = image.src;
            fullscreenModal.classList.add('active');
            fullscreenScale = 1;
            fullscreenImage.style.transform = `scale(${fullscreenScale})`;
        };
        
        // Double-click to toggle zoom
        image.ondblclick = (e) => {
            e.preventDefault();
            if (scale === 1) {
                scale = 2;
                image.style.transform = `scale(${scale})`;
                this.updateImageContainer(container, scale);
            } else {
                scale = 1;
                image.style.transform = `scale(${scale})`;
                this.updateImageContainer(container, scale);
                container.scrollTop = 0;
                container.scrollLeft = 0;
            }
        };
        
        // Mouse wheel zoom
        container.onwheel = (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -scaleStep : scaleStep;
            const newScale = Math.max(minScale, Math.min(maxScale, scale + delta));
            
            if (newScale !== scale) {
                scale = newScale;
                image.style.transform = `scale(${scale})`;
                this.updateImageContainer(container, scale);
            }
        };
        
        // Panning functionality
        container.onmousedown = (e) => {
            if (scale > 1) {
                isPanning = true;
                container.style.cursor = 'grabbing';
                container.classList.add('grabbing');
                startX = e.pageX - container.offsetLeft;
                startY = e.pageY - container.offsetTop;
                scrollLeft = container.scrollLeft;
                scrollTop = container.scrollTop;
            }
        };
        
        container.onmouseleave = () => {
            isPanning = false;
            container.style.cursor = scale > 1 ? 'grab' : 'default';
            container.classList.remove('grabbing');
        };
        
        container.onmouseup = () => {
            isPanning = false;
            container.style.cursor = scale > 1 ? 'grab' : 'default';
            container.classList.remove('grabbing');
        };
        
        container.onmousemove = (e) => {
            if (!isPanning || scale <= 1) return;
            e.preventDefault();
            const x = e.pageX - container.offsetLeft;
            const y = e.pageY - container.offsetTop;
            const walkX = (x - startX) * 2;
            const walkY = (y - startY) * 2;
            container.scrollLeft = scrollLeft - walkX;
            container.scrollTop = scrollTop - walkY;
        };
        
        // Fullscreen controls
        document.getElementById('closeFullscreen').onclick = () => {
            fullscreenModal.classList.remove('active');
        };
        
        document.getElementById('fullscreenZoomIn').onclick = () => {
            if (fullscreenScale < maxScale) {
                fullscreenScale += scaleStep;
                fullscreenImage.style.transform = `scale(${fullscreenScale})`;
            }
        };
        
        document.getElementById('fullscreenZoomOut').onclick = () => {
            if (fullscreenScale > minScale) {
                fullscreenScale -= scaleStep;
                fullscreenImage.style.transform = `scale(${fullscreenScale})`;
            }
        };
        
        document.getElementById('fullscreenReset').onclick = () => {
            fullscreenScale = 1;
            fullscreenImage.style.transform = `scale(${fullscreenScale})`;
        };
        
        // Close fullscreen on escape key
        document.onkeydown = (e) => {
            if (e.key === 'Escape' && fullscreenModal.classList.contains('active')) {
                fullscreenModal.classList.remove('active');
            }
        };
        
        // Close fullscreen on background click
        fullscreenModal.onclick = (e) => {
            if (e.target === fullscreenModal) {
                fullscreenModal.classList.remove('active');
            }
        };
    }
    
    updateImageContainer(container, scale) {
        if (scale > 1) {
            container.style.cursor = 'grab';
        } else {
            container.style.cursor = 'default';
            container.scrollTop = 0;
            container.scrollLeft = 0;
        }
    }



    getScoreClass(score) {
        if (score >= 80) return 'good';
        if (score >= 60) return 'warning';
        return 'critical';
    }

    // Toast Notifications
    showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'exclamation-triangle'}"></i>
                <span>${message}</span>
            </div>
        `;

        document.body.appendChild(toast);

        // Show toast
        setTimeout(() => toast.classList.add('show'), 100);

        // Hide and remove toast
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => document.body.removeChild(toast), 300);
        }, 5000);
    }
}

// Global processor instance for verification access
let processor;

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    processor = new FRADocumentProcessor();
});

// Add some additional utility functions for enhanced UX
document.addEventListener('DOMContentLoaded', () => {
    // Add smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl+U for single upload
        if (e.ctrlKey && e.key === 'u') {
            e.preventDefault();
            document.getElementById('singleFileInput').click();
        }
        
        // Ctrl+B for bulk upload
        if (e.ctrlKey && e.key === 'b') {
            e.preventDefault();
            document.getElementById('bulkFileInput').click();
        }
    });

    // Add intersection observer for animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate__animated', 'animate__fadeInUp');
            }
        });
    }, observerOptions);

    // Observe all cards for animation
    document.querySelectorAll('.upload-method, .document-type-section').forEach(el => {
        observer.observe(el);
    });
});