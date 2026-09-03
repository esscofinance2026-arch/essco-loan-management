/**
 * file-validation.js
 * Handles file upload validation for ALL file inputs
 * 
 * Logic:
 * - Only required fields show red border when empty
 * - Optional fields show no error when empty
 * - Any uploaded file (required or optional) gets size validation
 * - Short, clear error messages
 */

(function() {
    'use strict';

    console.log('🔍 File validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        MAX_FILE_SIZE: 2 * 1024 * 1024, // 2 MB
        STEP_INDEX_DOCUMENT_UPLOAD: 4,   // Step 5 (0-indexed)
    };

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = null;

    function getElements() {
        if (elements) return elements;

        elements = {
            fileInputs: document.querySelectorAll('input[type="file"]'),
            errorDiv: document.getElementById('errorMessage'),
            form: document.getElementById('applicationForm'),
            nextBtns: document.querySelectorAll('.next-btn'),
            submitBtn: document.getElementById('submit-btn'),
            confirmCheck: document.getElementById('confirm-check'),
            steps: document.querySelectorAll('.step'),
            progressFill: document.getElementById('progress-fill'),
            currentStepText: document.getElementById('current-step'),
        };

        return elements;
    }

    // ============================================================
    // CORE VALIDATION FUNCTIONS
    // ============================================================

    /**
     * Validates a single file input
     * @param {HTMLInputElement} input - The file input element
     * @param {number} maxSize - Maximum file size in bytes (optional)
     * @returns {Object} { isValid: boolean, errorMessage: string, file: File|null }
     */
    function validateSingleFile(input, maxSize = CONFIG.MAX_FILE_SIZE) {
        if (!input) {
            return { isValid: true, errorMessage: '', file: null };
        }

        // Get the field name for better error messages
        const fieldName = input.id || input.name || 'File';
        const label = document.querySelector(`label[for="${input.id}"]`);
        const fieldLabel = label ? label.textContent.trim().replace(/[:*]/g, '').trim() : fieldName.replace(/_/g, ' ');

        // Check if a file is selected
        if (input.files.length === 0) {
            // ⭐ ONLY require if field has 'required' attribute
            if (input.hasAttribute('required')) {
                return {
                    isValid: false,
                    errorMessage: `📄 ${fieldLabel} is required.`,
                    file: null
                };
            }
            // Optional field - no file selected, skip validation
            return { isValid: true, errorMessage: '', file: null };
        }

        // ⭐ IF A FILE IS SELECTED - ALWAYS validate its size
        const file = input.files[0];
        const maxSizeMB = (maxSize / (1024 * 1024)).toFixed(0);

        if (file.size > maxSize) {
            const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
            return {
                isValid: false,
                errorMessage: `📄 ${fieldLabel} This file is ${sizeInMB}MB (max ${maxSizeMB}MB).`,
                file: file
            };
        }

        return {
            isValid: true,
            errorMessage: '',
            file: file
        };
    }

    /**
     * Validates ALL file inputs on the page
     * @returns {Object} { isValid: boolean, errors: string[], files: File[] }
     */
    function validateAllFiles() {
        const el = getElements();
        const errors = [];
        const validFiles = [];
        let isValid = true;

        el.fileInputs.forEach(input => {
            const result = validateSingleFile(input);

            // ⭐ Only show red border if:
            // 1. Field is required AND empty, OR
            // 2. File is selected AND too large
            const shouldShowError = (!result.isValid && input.hasAttribute('required')) || 
                                   (input.files.length > 0 && !result.isValid);

            if (!result.isValid) {
                isValid = false;
                errors.push(result.errorMessage);
                
                // ⭐ Only highlight if it's a required field OR has a file
                if (shouldShowError) {
                    input.style.border = '2px solid #ff4444';
                    input.style.backgroundColor = 'rgba(255, 68, 68, 0.1)';
                }
            } else {
                // Clear any previous error styling
                input.style.border = '';
                input.style.backgroundColor = '';
            }
        });

        return { isValid, errors, files: validFiles };
    }

    /**
     * Shows an error message for a specific file input
     * @param {HTMLInputElement} input - The file input element
     * @param {string} message - The error message
     */
    function showFieldError(input, message) {
        // Only show error if field is required
        if (!input.hasAttribute('required') && input.files.length === 0) {
            return; // Don't show errors for optional empty fields
        }

        // Highlight the input
        input.style.border = '2px solid #ff4444';
        input.style.backgroundColor = 'rgba(255, 68, 68, 0.1)';

        // Find or create error div
        let errorDiv = input.parentElement.querySelector('.field-error-message');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'field-error-message';
            errorDiv.style.color = 'red';
            errorDiv.style.fontSize = '13px';
            errorDiv.style.marginTop = '4px';
            input.parentElement.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    /**
     * Clears error message for a specific file input
     * @param {HTMLInputElement} input - The file input element
     */
    function clearFieldError(input) {
        input.style.border = '';
        input.style.backgroundColor = '';

        const errorDiv = input.parentElement.querySelector('.field-error-message');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
        
        // Also hide success messages
        const successDiv = input.parentElement.querySelector('.field-success-message');
        if (successDiv) {
            successDiv.style.display = 'none';
        }
    }

    /**
     * Shows success message for a valid file
     * @param {HTMLInputElement} input - The file input element
     * @param {string} message - The success message
     */
    function showFieldSuccess(input, message) {
        // Only show success if file is selected
        if (input.files.length === 0) return;
        
        let successDiv = input.parentElement.querySelector('.field-success-message');
        if (!successDiv) {
            successDiv = document.createElement('div');
            successDiv.className = 'field-success-message';
            successDiv.style.color = 'green';
            successDiv.style.fontSize = '13px';
            successDiv.style.marginTop = '4px';
            input.parentElement.appendChild(successDiv);
        }
        successDiv.textContent = message;
        successDiv.style.display = 'block';
    }

    /**
     * Shows the main error message (for Step 5 validation)
     * @param {string} message - The error message
     */
    function showMainError(message) {
        const el = getElements();
        if (el.errorDiv) {
            // ⭐ Shorten the message - just show "Please fix the highlighted fields"
            el.errorDiv.textContent = '⚠️ Please fix the highlighted fields below.';
            el.errorDiv.style.display = 'block';
            el.errorDiv.style.color = 'red';
        }
    }

    /**
     * Hides the main error message
     */
    function hideMainError() {
        const el = getElements();
        if (el.errorDiv) {
            el.errorDiv.style.display = 'none';
        }
    }

    /**
     * Gets file info for display
     * @param {File} file - The file object
     * @returns {string} Formatted file info
     */
    function getFileInfo(file) {
        const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
        return `${file.name} (${sizeInMB} MB)`;
    }

    // ============================================================
    // NAVIGATION HELPERS
    // ============================================================

    function goToStep(stepIndex) {
        const el = getElements();
        const steps = el.steps || document.querySelectorAll('.step');

        if (!steps.length) return;

        steps.forEach(s => s.classList.remove('active'));
        if (steps[stepIndex]) {
            steps[stepIndex].classList.add('active');
        }

        const progressFill = el.progressFill || document.getElementById('progress-fill');
        const currentStepText = el.currentStepText || document.getElementById('current-step');

        if (progressFill) {
            const percentage = ((stepIndex + 1) / steps.length) * 100;
            progressFill.style.width = percentage + '%';
        }

        if (currentStepText) {
            currentStepText.textContent = stepIndex + 1;
        }
    }

    // ============================================================
    // EVENT HANDLERS
    // ============================================================

    /**
     * Handles real-time validation for ALL file inputs
     */
    function handleFileSelections() {
        const el = getElements();

        el.fileInputs.forEach(input => {
            input.addEventListener('change', function() {
                console.log(`📁 File selection changed: ${this.id || this.name}`);

                const result = validateSingleFile(this);

                // Clear previous messages
                clearFieldError(this);
                
                if (!result.isValid) {
                    // ⭐ Only show error for required fields or invalid files
                    if (this.hasAttribute('required') || this.files.length > 0) {
                        showFieldError(this, result.errorMessage);
                        // Clear invalid file
                        if (this.files.length > 0 && !result.isValid) {
                            this.value = '';
                        }
                    }
                } else if (result.isValid && result.file) {
                    // Show success message
                    const sizeInMB = (result.file.size / (1024 * 1024)).toFixed(2);
                    showFieldSuccess(this, `✅ ${result.file.name} (${sizeInMB} MB)`);
                    
                    // ⭐ Remove red border if it was there
                    this.style.border = '';
                    this.style.backgroundColor = '';
                }
            });
        });
    }

    /**
     * Handles "Next" button clicks - validates all files on Step 5
     */
    function handleNextButton() {
        const el = getElements();

        el.nextBtns.forEach(button => {
            button.addEventListener('click', function(e) {
                console.log('➡️ Next button clicked');

                const stepContainer = this.closest('.step');
                if (!stepContainer) return;

                const steps = document.querySelectorAll('.step');
                const currentStepIndex = Array.from(steps).indexOf(stepContainer);

                // ⭐ If this is Step 5 (Document Upload), validate ALL files
                if (currentStepIndex === CONFIG.STEP_INDEX_DOCUMENT_UPLOAD) {
                    console.log('🔍 Validating ALL files on Step 5');

                    const result = validateAllFiles();

                    if (!result.isValid) {
                        console.log('❌ File validation failed');
                        showMainError('Please fix the highlighted fields below.');
                        
                        // Remove the main error after 5 seconds
                        setTimeout(() => {
                            hideMainError();
                        }, 5000);

                        // Scroll to first invalid file
                        const firstInvalid = document.querySelector('input[type="file"][style*="border: 2px solid rgb(255, 68, 68)"]');
                        if (firstInvalid) {
                            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            firstInvalid.focus();
                        }
                        return; // ⭐ BLOCK navigation
                    }

                    console.log('✅ All files valid');
                    hideMainError();
                }
            });
        });
    }

    /**
     * Handles form submission with final validation of ALL files
     */
    function handleFormSubmit() {
        const el = getElements();

        if (!el.form) return;

        el.form.addEventListener('submit', function(e) {
            console.log('📤 Form submission - validating ALL files');

            const result = validateAllFiles();

            if (!result.isValid) {
                console.log('❌ File validation failed');
                e.preventDefault();

                showMainError('Please fix the highlighted fields below.');
                
                setTimeout(() => {
                    hideMainError();
                }, 5000);

                // Navigate to Step 5
                goToStep(CONFIG.STEP_INDEX_DOCUMENT_UPLOAD);

                // Scroll to first invalid file
                const firstInvalid = document.querySelector('input[type="file"][style*="border: 2px solid rgb(255, 68, 68)"]');
                if (firstInvalid) {
                    firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstInvalid.focus();
                }
                return false;
            }

            console.log('✅ All validation passed - submitting form');
            hideMainError();
            return true;
        });
    }

    /**
     * Handles checkbox to enable/disable submit button
     */
    function handleConfirmCheckbox() {
        const el = getElements();

        if (!el.confirmCheck || !el.submitBtn) return;

        el.confirmCheck.addEventListener('change', function() {
            el.submitBtn.disabled = !this.checked;
        });
    }

    // ============================================================
    // INITIALIZATION
    // ============================================================

    function init() {
        console.log('🚀 Initializing file validation module...');

        const el = getElements();
        if (!el.fileInputs || el.fileInputs.length === 0) {
            console.warn('⚠️ No file inputs found - skipping file validation');
            return;
        }

        console.log(`📁 Found ${el.fileInputs.length} file input(s)`);

        // Initialize all event handlers
        handleFileSelections();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();

        console.log('✅ File validation module initialized successfully');
        console.log(`📋 Configuration: Max file size = ${(CONFIG.MAX_FILE_SIZE / (1024 * 1024)).toFixed(0)} MB`);
        console.log(`📍 Document upload step = ${CONFIG.STEP_INDEX_DOCUMENT_UPLOAD + 1}`);
    }

    // ============================================================
    // EXPOSE PUBLIC API
    // ============================================================

    window.FileValidation = {
        validateSingleFile: validateSingleFile,
        validateAllFiles: validateAllFiles,
        CONFIG: CONFIG,
        reinit: function() {
            elements = null;
            init();
        }
    };

    // ============================================================
    // START
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    console.log('📦 File validation module ready');

})();