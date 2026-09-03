// static/js/id-validation.js

(function() {
    'use strict';

    console.log('🪪 ID validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        STEP_INDEX_PERSONAL_INFO: 0,
        ID_SELECTOR: 'input[name$="ID_number"], input[name$="ID_Number"], #id_ID_number, #id_ID_Number, input[id$="ID_number"]',
        ID_TYPE_SELECTOR: '#id_ID_Type, select[name="ID_Type"], select[name="IDType"]',
        MAX_LENGTH_OTHER: 20,
        MIN_AGE: 18,
        DATE_FORMAT: 'YYMMDD',
    };

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = null;

    function getElements() {
        if (elements) return elements;

        elements = {
            idInputs: document.querySelectorAll(CONFIG.ID_SELECTOR),
            idTypeSelect: document.querySelector(CONFIG.ID_TYPE_SELECTOR),
            form: document.getElementById('applicationForm'),
            nextBtns: document.querySelectorAll('.next-btn'),
            submitBtn: document.getElementById('submit-btn'),
            confirmCheck: document.getElementById('confirm-check'),
            steps: document.querySelectorAll('.step'),
            errorDiv: document.getElementById('errorMessage'),
            dobInput: document.getElementById('id_DOB'),
        };

        return elements;
    }

    // ============================================================
    // HELPER FUNCTIONS
    // ============================================================

    function isNationalID() {
        const el = getElements();
        if (!el.idTypeSelect) return true;
        return el.idTypeSelect.value === 'National ID card';
    }

    function getFieldLabel(input) {
        if (!input) return 'ID Number';
        const label = document.querySelector(`label[for="${input.id}"]`);
        if (label) {
            return label.textContent.trim().replace(/[:*]/g, '').trim();
        }
        const name = input.name || input.id || '';
        return name.replace(/_/g, ' ').replace(/[0-9]/g, '').trim() || 'ID Number';
    }

    function formatIDNumber(value) {
        if (!isNationalID()) {
            return value;
        }
        let cleaned = value.replace(/\D/g, '');
        if (cleaned.length > 11) {
            cleaned = cleaned.slice(0, 11);
        }
        if (cleaned.length > 6) {
            return cleaned.slice(0, 6) + '-' + cleaned.slice(6);
        }
        return cleaned;
    }

    // ✅ FIX: Make validateIDFormat available globally within this module
    function validateIDFormat(idNumber, idType) {
        if (!idNumber || idNumber.trim() === '') {
            return {
                isValid: false,
                message: '🪪 Please enter your ID number.',
                cleaned: ''
            };
        }

        const trimmed = idNumber.trim();
        const cleaned = trimmed.replace(/[^\d-]/g, '');

        if (idType !== 'National ID card') {
            if (cleaned.length > CONFIG.MAX_LENGTH_OTHER) {
                return {
                    isValid: false,
                    message: `🪪 ID number cannot exceed ${CONFIG.MAX_LENGTH_OTHER} characters.`,
                    cleaned: cleaned
                };
            }
            return {
                isValid: true,
                message: `✅ Valid (${cleaned.length} characters)`,
                cleaned: cleaned
            };
        }

        if (!/^\d{6}-\d{4}$/.test(cleaned)) {
            return {
                isValid: false,
                message: '🪪 Format must be YYMMDD-XXXX (e.g., 940827-0017)',
                cleaned: cleaned
            };
        }

        const datePart = cleaned.split('-')[0];
        const month = parseInt(datePart.slice(2, 4));
        const day = parseInt(datePart.slice(4, 6));

        if (month < 1 || month > 12) {
            return {
                isValid: false,
                message: '🪪 Invalid month in ID number',
                cleaned: cleaned
            };
        }

        const daysInMonth = new Date(2000, month, 0).getDate();
        if (day < 1 || day > daysInMonth) {
            return {
                isValid: false,
                message: '🪪 Invalid day in ID number',
                cleaned: cleaned
            };
        }

        return {
            isValid: true,
            message: '✅ Valid National ID format',
            cleaned: cleaned
        };
    }

    // ✅ FIX: Make validateIDInput available globally within this module
    function validateIDInput(input) {
        if (!input) return;

        const el = getElements();
        const idType = el.idTypeSelect ? el.idTypeSelect.value : 'National ID card';
        const value = input.value;

        if (value.trim() === '') {
            clearIDMessage(input);
            return { isValid: true, message: '', cleaned: '' };
        }

        const result = validateIDFormat(value, idType);

        if (!result.isValid) {
            showIDMessage(input, result.message, false);
        } else if (result.isValid && value.trim() !== '') {
            showIDMessage(input, result.message, true);
        } else {
            clearIDMessage(input);
        }

        return result;
    }

    function validateAllIDs() {
        const el = getElements();
        const errors = [];
        const ids = {};
        let isValid = true;
        const idType = el.idTypeSelect ? el.idTypeSelect.value : 'National ID card';

        el.idInputs.forEach(input => {
            if (input.type === 'hidden') return;

            const value = input.value;
            const label = getFieldLabel(input);

            if (value.trim() === '') {
                clearIDMessage(input);
                return;
            }

            const result = validateIDFormat(value, idType);

            ids[input.id || input.name] = result.cleaned;

            if (!result.isValid) {
                isValid = false;
                const fieldLabel = label || 'ID Number';
                errors.push(`🪪 ${fieldLabel}: ${result.message}`);

                input.style.border = '2px solid #ff4444';
                input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
            } else if (result.isValid) {
                input.style.border = '2px solid #28a745';
                input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
            } else {
                input.style.border = '';
                input.style.backgroundColor = '';
            }
        });

        return { isValid, errors, ids };
    }

    function getIDErrorDiv(input) {
        if (!input) return null;

        let errorDiv = input.parentElement.querySelector('.id-error-message');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'id-error-message';
            errorDiv.style.fontSize = '13px';
            errorDiv.style.marginTop = '4px';
            input.parentElement.appendChild(errorDiv);
        }
        return errorDiv;
    }

    function showIDMessage(input, message, isSuccess = false) {
        if (!input) return;

        const errorDiv = getIDErrorDiv(input);
        if (!errorDiv) return;

        errorDiv.textContent = message;
        errorDiv.style.display = 'block';

        if (isSuccess) {
            errorDiv.style.color = 'green';
            input.style.border = '2px solid #28a745';
            input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
        } else {
            errorDiv.style.color = 'red';
            input.style.border = '2px solid #ff4444';
            input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
        }
    }

    function clearIDMessage(input) {
        if (!input) return;

        const errorDiv = input.parentElement.querySelector('.id-error-message');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        input.style.border = '';
        input.style.backgroundColor = '';
    }

    function updateNextButtons() {
        const el = getElements();
        if (!el.nextBtns) return;

        const currentStep = getCurrentStep();

        if (currentStep !== CONFIG.STEP_INDEX_PERSONAL_INFO) {
            el.nextBtns.forEach(btn => {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            });
            return;
        }

        const result = validateAllIDs();
        const hasInvalid = !result.isValid;

        el.nextBtns.forEach(btn => {
            const btnStep = btn.closest('.step');
            if (btnStep) {
                const btnStepIndex = Array.from(el.steps).indexOf(btnStep);
                if (btnStepIndex === currentStep) {
                    btn.disabled = hasInvalid;
                    btn.style.opacity = hasInvalid ? '0.5' : '1';
                    btn.style.cursor = hasInvalid ? 'not-allowed' : 'pointer';
                }
            }
        });
    }

    function getCurrentStep() {
        const el = getElements();
        let currentStep = 0;
        el.steps.forEach((step, index) => {
            if (step.classList.contains('active')) {
                currentStep = index;
            }
        });
        return currentStep;
    }

    function handleIDInputs() {
        const el = getElements();

        el.idInputs.forEach(input => {
            if (input.type === 'hidden') return;

            input.addEventListener('input', function() {
                const cursorPosition = this.selectionStart;
                const oldValue = this.value;

                const formatted = formatIDNumber(this.value);

                if (formatted !== this.value) {
                    this.value = formatted;
                    const newPosition = cursorPosition + (formatted.length - oldValue.length);
                    this.setSelectionRange(newPosition, newPosition);
                }

                // ✅ Now validateIDInput is defined
                validateIDInput(this);
                updateNextButtons();
                updateSubmitButton();
            });

            input.addEventListener('blur', function() {
                const result = validateIDInput(this);
                if (!result.isValid && this.value.trim() !== '') {
                    showIDMessage(this, result.message, false);
                }
                updateNextButtons();
                updateSubmitButton();
            });

            input.addEventListener('focus', function() {
                if (this.value.trim() === '') {
                    clearIDMessage(this);
                }
            });

            if (input.value.trim() !== '') {
                validateIDInput(input);
            }
        });

        if (el.idTypeSelect) {
            el.idTypeSelect.addEventListener('change', function() {
                el.idInputs.forEach(input => {
                    if (input.value.trim() !== '') {
                        validateIDInput(input);
                    }
                });
                updateNextButtons();
                updateSubmitButton();
            });
        }
    }

    function handleNextButton() {
        const el = getElements();

        el.nextBtns.forEach(button => {
            button.addEventListener('click', function(e) {
                const stepContainer = this.closest('.step');
                if (!stepContainer) return;

                const steps = document.querySelectorAll('.step');
                const currentStepIndex = Array.from(steps).indexOf(stepContainer);

                if (currentStepIndex === CONFIG.STEP_INDEX_PERSONAL_INFO) {
                    console.log('🔍 Validating ALL IDs on Step 1');

                    const result = validateAllIDs();

                    if (!result.isValid) {
                        e.preventDefault();
                        e.stopPropagation();

                        console.log('❌ ID validation failed:', result.errors);

                        if (el.errorDiv) {
                            el.errorDiv.textContent = '⚠️ Please fix the ID numbers below.';
                            el.errorDiv.style.display = 'block';
                            el.errorDiv.style.color = 'red';
                        }

                        const firstInvalid = document.querySelector('input[name$="ID_number"][style*="border: 2px solid rgb(255, 68, 68)"]');
                        if (firstInvalid) {
                            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            firstInvalid.focus();
                        }
                        return false;
                    }

                    console.log('✅ All IDs valid');
                    if (el.errorDiv) {
                        el.errorDiv.style.display = 'none';
                    }
                }
            });
        });
    }

    function handleFormSubmit() {
        const el = getElements();

        if (!el.form) return;

        el.form.addEventListener('submit', function(e) {
            const result = validateAllIDs();

            if (!result.isValid) {
                e.preventDefault();

                if (el.errorDiv) {
                    el.errorDiv.textContent = '⚠️ Please fix the ID numbers below.';
                    el.errorDiv.style.display = 'block';
                    el.errorDiv.style.color = 'red';
                }

                const firstInvalid = document.querySelector('input[name$="ID_number"][style*="border: 2px solid rgb(255, 68, 68)"]');
                if (firstInvalid) {
                    firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstInvalid.focus();
                }
                return false;
            }

            if (el.errorDiv) {
                el.errorDiv.style.display = 'none';
            }
            return true;
        });
    }

    function handleConfirmCheckbox() {
        const el = getElements();

        if (!el.confirmCheck || !el.submitBtn) return;

        el.confirmCheck.addEventListener('change', function() {
            updateSubmitButton();
        });
    }

    function updateSubmitButton() {
        const el = getElements();
        if (!el.submitBtn) return;

        let allValid = true;

        const currentStep = getCurrentStep();
        if (currentStep === CONFIG.STEP_INDEX_PERSONAL_INFO) {
            const result = validateAllIDs();
            if (!result.isValid) allValid = false;
        }

        if (el.confirmCheck && !el.confirmCheck.checked) {
            allValid = false;
        }

        el.submitBtn.disabled = !allValid;
    }

    function initStepObserver() {
        const el = getElements();
        if (!el.steps) return;

        el.steps.forEach(step => {
            const observer = new MutationObserver(function() {
                setTimeout(() => {
                    updateNextButtons();
                    updateSubmitButton();
                }, 50);
            });
            observer.observe(step, { attributes: true, attributeFilter: ['class'] });
        });
    }

    // ============================================================
    // INITIALIZATION
    // ============================================================

    function init() {
        console.log('🚀 Initializing ID validation module...');

        const el = getElements();
        if (!el.idInputs || el.idInputs.length === 0) {
            console.warn('⚠️ No ID inputs found - skipping ID validation');
            return;
        }

        console.log(`🪪 Found ${el.idInputs.length} ID input(s):`);
        el.idInputs.forEach(input => {
            console.log(`  - ${input.id || input.name || 'unnamed'}`);
        });

        if (el.idTypeSelect) {
            console.log(`📋 ID Type detected: "${el.idTypeSelect.value}"`);
            console.log(`   National ID format: ${isNationalID() ? 'ENABLED' : 'DISABLED (max ${CONFIG.MAX_LENGTH_OTHER} chars)'}`);
        }

        handleIDInputs();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();
        initStepObserver();

        setTimeout(() => {
            updateNextButtons();
            updateSubmitButton();
        }, 100);

        console.log('✅ ID validation module initialized successfully');
        console.log(`📋 Format: YYMMDD-XXXX (e.g., 940827-0017) - National ID only`);
        console.log(`📋 Other ID types: Max ${CONFIG.MAX_LENGTH_OTHER} characters`);
    }

    // ============================================================
    // EXPOSE PUBLIC API
    // ============================================================

    window.IDValidation = {
        validateIDFormat: validateIDFormat,
        validateAllIDs: validateAllIDs,
        formatIDNumber: formatIDNumber,
        isNationalID: isNationalID,
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

    console.log('📦 ID validation module ready');

})();