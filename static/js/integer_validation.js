/**
 * integer_validation.js
 * Universal validation for ALL integer/decimal fields
 * BLOCKS "Next" button if any field is invalid
 */

(function() {
    'use strict';

    console.log('🔢 Integer Validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        MAX_DIGITS_DECIMAL: 10,
        MAX_DIGITS_INTEGER: 2,
        MIN_VALUE: 0,
        STEP_MAPPING: {
            'Num_Dependents': 0,
            'Length_at_Address': 0,
            'Gross_Monthly_Income': 1,
            'Purchase_Value': 2,
            'Loan_mortgages_payments': 2,
            'CCPayments': 2,
            'Other_Debt_Payments': 2,
            'Rent': 2,
            'Transportation': 2,
            'Insurance': 2,
            'Other_Living_Expenses': 2,
            'food': 2,
            'utilities': 2,
            'Reference1_Len_Time_Known': 3,
            'Reference2_Len_Time_Known': 3,
        },
        DECIMAL_FIELDS: [
            'Gross_Monthly_Income',
            'Purchase_Value',
            'Loan_mortgages_payments',
            'CCPayments',
            'Other_Debt_Payments',
            'Rent',
            'Transportation',
            'Insurance',
            'Other_Living_Expenses',
            'food',
            'utilities',
        ],
        INTEGER_FIELDS: [
            'Num_Dependents',
            'Length_at_Address',
            'Reference1_Len_Time_Known',
            'Reference2_Len_Time_Known',
        ],
        FIELD_LABELS: {
            'Gross_Monthly_Income': 'Gross Monthly Income',
            'Purchase_Value': 'Purchase Value',
            'Num_Dependents': 'Number of Dependents',
            'Length_at_Address': 'Years at Address',
            'Reference1_Len_Time_Known': 'Years Known (Reference 1)',
            'Reference2_Len_Time_Known': 'Years Known (Reference 2)',
            'Loan_mortgages_payments': 'Loan/Mortgage Payments',
            'CCPayments': 'Credit Card Payments',
            'Other_Debt_Payments': 'Other Debt Payments',
            'Rent': 'Rent',
            'Transportation': 'Transportation',
            'Insurance': 'Insurance',
            'Other_Living_Expenses': 'Other Living Expenses',
            'food': 'Food',
            'utilities': 'Utilities',
        },
    };

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = {};

    function getElements() {
        if (Object.keys(elements).length > 0) return elements;

        const allInputs = document.querySelectorAll('input[type="number"], input[name]');
        
        elements.inputs = [];
        elements.feedback = {};
        elements.steps = document.querySelectorAll('.step');
        elements.nextBtns = document.querySelectorAll('.next-btn');
        elements.submitBtn = document.getElementById('submit-btn');
        elements.confirmCheck = document.getElementById('confirm-check');
        elements.form = document.getElementById('applicationForm');
        elements.errorDiv = document.getElementById('errorMessage');

        allInputs.forEach(input => {
            const name = input.name || input.id;
            const isDecimal = CONFIG.DECIMAL_FIELDS.some(f => name.includes(f));
            const isInteger = CONFIG.INTEGER_FIELDS.some(f => name.includes(f));
            
            if (isDecimal || isInteger) {
                elements.inputs.push(input);
                const feedbackId = (input.id || name) + '-feedback';
                elements.feedback[input.id || name] = document.getElementById(feedbackId);
            }
        });

        return elements;
    }

    // ============================================================
    // TRACKING
    // ============================================================
    let invalidFields = new Set();

    // ============================================================
    // VALIDATION FUNCTIONS
    // ============================================================

    function countDigits(value) {
        if (!value) return 0;
        const str = String(value).replace(/[^0-9]/g, '');
        return str.length;
    }

    function getFieldLabel(name) {
        return CONFIG.FIELD_LABELS[name] || name.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim();
    }

    function getMaxDigits(name) {
        const isDecimal = CONFIG.DECIMAL_FIELDS.some(f => name.includes(f));
        const isInteger = CONFIG.INTEGER_FIELDS.some(f => name.includes(f));
        if (isDecimal) return CONFIG.MAX_DIGITS_DECIMAL;
        if (isInteger) return CONFIG.MAX_DIGITS_INTEGER;
        return CONFIG.MAX_DIGITS_DECIMAL;
    }

    function getStepIndex(name) {
        for (const [key, step] of Object.entries(CONFIG.STEP_MAPPING)) {
            if (name.includes(key) || key.includes(name)) {
                return step;
            }
        }
        return -1;
    }

    function validateField(input) {
        if (!input) return { isValid: true, message: '', value: null };

        const name = input.name || input.id;
        const label = getFieldLabel(name);
        const value = input.value.trim();
        const maxDigits = getMaxDigits(name);
        
        if (value === '') {
            return { isValid: true, message: '', value: null };
        }

        const cleanValue = value.replace(/,/g, '');
        const numValue = parseFloat(cleanValue);

        if (isNaN(numValue)) {
            return { isValid: false, message: `${label} must be a valid number.`, value: null };
        }

        const digitCount = countDigits(cleanValue);

        if (digitCount > maxDigits) {
            return { isValid: false, message: `${label} cannot exceed ${maxDigits} digits. (Current: ${digitCount})`, value: numValue };
        }

        if (numValue < CONFIG.MIN_VALUE) {
            return { isValid: false, message: `${label} cannot be negative.`, value: numValue };
        }

        return { isValid: true, message: `✅ ${label}: ${numValue.toLocaleString()}`, value: numValue };
    }

    function getFeedbackElement(input) {
        if (!input) return null;

        const name = input.name || input.id;
        const feedbackId = (input.id || name) + '-feedback';
        let feedback = document.getElementById(feedbackId);

        if (!feedback) {
            feedback = document.createElement('div');
            feedback.id = feedbackId;
            feedback.style.fontSize = '13px';
            feedback.style.marginTop = '4px';
            feedback.style.display = 'none';
            input.parentElement.appendChild(feedback);
        }

        return feedback;
    }

    function showFieldMessage(input, message, isValid = false) {
        if (!input) return;

        const feedback = getFeedbackElement(input);
        if (!feedback) return;

        feedback.textContent = message;
        feedback.style.display = 'block';
        
        if (isValid) {
            feedback.style.color = '#28a745';
            input.style.border = '2px solid #28a745';
            input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
            invalidFields.delete(input.id || input.name);
        } else {
            feedback.style.color = '#ff4444';
            input.style.border = '2px solid #ff4444';
            input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
            invalidFields.add(input.id || input.name);
        }
    }

    function clearFieldMessage(input) {
        if (!input) return;

        const feedback = getFeedbackElement(input);
        if (feedback) {
            feedback.style.display = 'none';
            feedback.textContent = '';
        }

        input.style.border = '';
        input.style.backgroundColor = '';
        invalidFields.delete(input.id || input.name);
    }

    function validateAndUpdate(input) {
        if (!input) return { isValid: true };

        const value = input.value.trim();
        
        if (value === '') {
            clearFieldMessage(input);
            return { isValid: true };
        }

        const result = validateField(input);

        if (!result.isValid) {
            showFieldMessage(input, result.message, false);
        } else {
            showFieldMessage(input, result.message, true);
        }

        return result;
    }

    function validateAllFields() {
        let allValid = true;
        let firstInvalid = null;

        elements.inputs.forEach(input => {
            if (input.type === 'hidden') return;
            
            const result = validateField(input);
            
            if (!result.isValid && input.value.trim() !== '') {
                allValid = false;
                if (!firstInvalid) firstInvalid = input;
                showFieldMessage(input, result.message, false);
            } else if (result.isValid && input.value.trim() !== '') {
                showFieldMessage(input, result.message, true);
            } else {
                clearFieldMessage(input);
            }
        });

        return { allValid, firstInvalid };
    }

    // ============================================================
    // ✅ UPDATE NEXT BUTTONS (BLOCK IF INVALID)
    // ============================================================

    function updateNextButtons() {
        const el = getElements();
        if (!el.nextBtns) return;

        // Check if ANY field in the CURRENT step is invalid
        const currentStep = getCurrentStep();
        const hasInvalid = hasInvalidFieldsInStep(currentStep);

        el.nextBtns.forEach(btn => {
            // Only disable the button in the current step
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

    function hasInvalidFieldsInStep(stepIndex) {
        const el = getElements();
        let hasInvalid = false;

        el.inputs.forEach(input => {
            const fieldStep = getStepIndex(input.name || input.id);
            if (fieldStep === stepIndex && input.value.trim() !== '') {
                const result = validateField(input);
                if (!result.isValid) {
                    hasInvalid = true;
                }
            }
        });

        return hasInvalid;
    }

    // ============================================================
    // EVENT HANDLERS
    // ============================================================

    function initFieldValidations() {
        const el = getElements();

        el.inputs.forEach(input => {
            input.addEventListener('input', function() {
                validateAndUpdate(this);
                updateNextButtons();
                updateSubmitButton();
            });

            input.addEventListener('blur', function() {
                if (this.value.trim() !== '') {
                    validateAndUpdate(this);
                    updateNextButtons();
                    updateSubmitButton();
                }
            });

            input.addEventListener('focus', function() {
                if (this.value.trim() === '') {
                    clearFieldMessage(this);
                }
            });

            if (input.value.trim() !== '') {
                validateAndUpdate(input);
            }
        });
    }

    function handleNextButton() {
        const el = getElements();

        el.nextBtns.forEach(button => {
            button.addEventListener('click', function(e) {
                const stepContainer = this.closest('.step');
                if (!stepContainer) return;

                const steps = document.querySelectorAll('.step');
                const currentStepIndex = Array.from(steps).indexOf(stepContainer);

                // ✅ Check for invalid fields in current step
                if (hasInvalidFieldsInStep(currentStepIndex)) {
                    e.preventDefault();
                    e.stopPropagation();

                    if (el.errorDiv) {
                        el.errorDiv.textContent = '⚠️ Please fix the highlighted fields before proceeding.';
                        el.errorDiv.style.display = 'block';
                        el.errorDiv.style.color = 'red';
                    }

                    // Scroll to first invalid field
                    let firstInvalid = null;
                    el.inputs.forEach(input => {
                        const fieldStep = getStepIndex(input.name || input.id);
                        if (fieldStep === currentStepIndex && input.value.trim() !== '') {
                            const result = validateField(input);
                            if (!result.isValid && !firstInvalid) {
                                firstInvalid = input;
                            }
                        }
                    });

                    if (firstInvalid) {
                        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        firstInvalid.focus();
                    }

                    return false;
                }

                // ✅ All valid - clear error
                if (el.errorDiv) {
                    el.errorDiv.style.display = 'none';
                }
            });
        });
    }

    function handleFormSubmit() {
        const el = getElements();

        if (!el.form) return;

        el.form.addEventListener('submit', function(e) {
            const result = validateAllFields();

            if (!result.allValid) {
                e.preventDefault();

                if (el.errorDiv) {
                    el.errorDiv.textContent = '⚠️ Please fix the highlighted fields.';
                    el.errorDiv.style.display = 'block';
                    el.errorDiv.style.color = 'red';
                }

                if (result.firstInvalid) {
                    result.firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    result.firstInvalid.focus();
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
            updateNextButtons();
            updateSubmitButton();
        });
    }

    function updateSubmitButton() {
        const el = getElements();
        if (!el.submitBtn) return;

        let allValid = true;
        el.inputs.forEach(input => {
            if (input.value.trim() !== '') {
                const result = validateField(input);
                if (!result.isValid) allValid = false;
            }
        });

        if (el.confirmCheck) {
            allValid = allValid && el.confirmCheck.checked;
        }

        el.submitBtn.disabled = !allValid;
    }

    // ============================================================
    // OBSERVER FOR STEP CHANGES (to update buttons)
    // ============================================================

    function initStepObserver() {
        const el = getElements();
        if (!el.steps) return;

        // Watch for step changes
        el.steps.forEach(step => {
            const observer = new MutationObserver(function() {
                // Update next buttons when step changes
                setTimeout(updateNextButtons, 50);
            });
            observer.observe(step, { attributes: true, attributeFilter: ['class'] });
        });
    }

    // ============================================================
    // INITIALIZATION
    // ============================================================

    function init() {
        console.log('🚀 Initializing Integer Validation module...');

        const el = getElements();
        if (el.inputs.length === 0) {
            console.warn('⚠️ No integer fields found - skipping validation');
            return;
        }

        console.log(`🔢 Found ${el.inputs.length} integer fields`);

        initFieldValidations();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();
        initStepObserver();

        // Initial update
        setTimeout(updateNextButtons, 100);

        console.log('✅ Integer Validation module initialized');
    }

    // ============================================================
    // START
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    console.log('📦 Integer Validation module ready');

})();