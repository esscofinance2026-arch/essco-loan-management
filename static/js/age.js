/**
 * age.js
 * Handles age validation with instant feedback
 * BLOCKS "Next" button if age is invalid
 * 
 * Validates that the user is at least 18 years old
 * Shows real-time feedback as user selects date of birth
 */

(function() {
    'use strict';

    console.log('🎂 Age validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        STEP_INDEX_PERSONAL_INFO: 0,
        MIN_AGE: 18,
        DOB_SELECTOR: '#id_DOB, input[name="DOB"], input[name="dob"]',
        FEEDBACK_ID: 'age-feedback',
    };

    // ============================================================
    // TRACKING
    // ============================================================
    let isAgeValid = true;
    let currentAge = 0;

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = null;

    function getElements() {
        if (elements) return elements;

        elements = {
            dobInput: document.querySelector(CONFIG.DOB_SELECTOR),
            feedback: document.getElementById(CONFIG.FEEDBACK_ID),
            form: document.getElementById('applicationForm'),
            nextBtns: document.querySelectorAll('.next-btn'),
            submitBtn: document.getElementById('submit-btn'),
            confirmCheck: document.getElementById('confirm-check'),
            steps: document.querySelectorAll('.step'),
            errorDiv: document.getElementById('errorMessage'),
        };

        return elements;
    }

    // ============================================================
    // AGE VALIDATION FUNCTIONS
    // ============================================================

    function validateAge(dobValue) {
        if (!dobValue || dobValue.trim() === '') {
            return {
                isValid: false,
                age: 0,
                message: '📅 Please enter your date of birth.',
                isRequired: true
            };
        }

        const birthDate = new Date(dobValue);
        const today = new Date();
        
        if (isNaN(birthDate.getTime())) {
            return {
                isValid: false,
                age: 0,
                message: '📅 Please enter a valid date of birth.',
                isRequired: true
            };
        }

        if (birthDate > today) {
            return {
                isValid: false,
                age: 0,
                message: '📅 Date of birth cannot be in the future.',
                isRequired: true
            };
        }

        let age = today.getFullYear() - birthDate.getFullYear();
        const monthDiff = today.getMonth() - birthDate.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
            age--;
        }

        if (age < CONFIG.MIN_AGE) {
            return {
                isValid: false,
                age: age,
                message: `❌ You must be at least ${CONFIG.MIN_AGE} years old to apply. (You are ${age})`,
                isRequired: true
            };
        }

        return {
            isValid: true,
            age: age,
            message: `✅ Age: ${age} years (Eligible)`,
            isRequired: false
        };
    }

    function getFeedbackDiv() {
        const el = getElements();
        
        if (el.feedback) {
            return el.feedback;
        }

        const dobInput = el.dobInput;
        if (!dobInput) return null;

        let feedback = document.getElementById(CONFIG.FEEDBACK_ID);
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.id = CONFIG.FEEDBACK_ID;
            feedback.style.fontSize = '13px';
            feedback.style.marginTop = '4px';
            dobInput.parentElement.appendChild(feedback);
            elements.feedback = feedback;
        }

        return feedback;
    }

    function showDOBMessage(input, message, isValid = false, age = 0) {
        if (!input) return;

        const feedback = getFeedbackDiv();
        if (!feedback) return;

        feedback.textContent = message;
        feedback.style.display = 'block';
        isAgeValid = isValid;
        currentAge = age;
        
        if (isValid) {
            feedback.style.color = '#28a745';
            input.style.border = '2px solid #28a745';
            input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
        } else {
            feedback.style.color = '#ff4444';
            input.style.border = '2px solid #ff4444';
            input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
        }
        
        // ✅ Update next buttons state
        updateNextButtons();
        updateSubmitButton();
    }

    function clearDOBMessage(input) {
        if (!input) return;

        const feedback = getFeedbackDiv();
        if (feedback) {
            feedback.style.display = 'none';
            feedback.textContent = '';
        }

        input.style.border = '';
        input.style.backgroundColor = '';
        isAgeValid = true;
        
        // ✅ Update next buttons state
        updateNextButtons();
        updateSubmitButton();
    }

    function validateDOBInput(input) {
        if (!input) return { isValid: false, age: 0 };

        const value = input.value;
        
        if (value.trim() === '') {
            const isRequired = input.hasAttribute('required');
            if (isRequired) {
                showDOBMessage(input, '📅 Please enter your date of birth.', false);
            } else {
                clearDOBMessage(input);
            }
            return { isValid: false, age: 0 };
        }

        const result = validateAge(value);

        if (!result.isValid) {
            showDOBMessage(input, result.message, false, result.age);
        } else {
            showDOBMessage(input, result.message, true, result.age);
        }

        return result;
    }

    function getMaxDate() {
        const maxDOB = new Date();
        maxDOB.setFullYear(maxDOB.getFullYear() - CONFIG.MIN_AGE);
        return maxDOB.toISOString().split('T')[0];
    }

    // ============================================================
    // ✅ UPDATE NEXT BUTTONS (BLOCK IF INVALID)
    // ============================================================

    function updateNextButtons() {
        const el = getElements();
        if (!el.nextBtns) return;

        const dobInput = el.dobInput;
        if (!dobInput) return;

        const result = validateAge(dobInput.value);
        const isValid = result.isValid || dobInput.value.trim() === '';

        // Enable/disable all next buttons
        el.nextBtns.forEach(btn => {
            // Only disable if DOB has a value AND it's invalid
            if (dobInput.value.trim() !== '' && !result.isValid) {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.style.cursor = 'not-allowed';
            } else {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            }
        });
    }

    function updateSubmitButton() {
        const el = getElements();
        if (!el.submitBtn) return;

        const dobInput = el.dobInput;
        if (!dobInput) return;

        const result = validateAge(dobInput.value);
        let allValid = true;

        // Check DOB
        if (dobInput.value.trim() !== '' && !result.isValid) {
            allValid = false;
        }

        // Check confirm checkbox
        if (el.confirmCheck && !el.confirmCheck.checked) {
            allValid = false;
        }

        el.submitBtn.disabled = !allValid;
    }

    // ============================================================
    // ✅ HAS INVALID AGE IN STEP
    // ============================================================

    function hasInvalidAgeInStep(stepIndex) {
        if (stepIndex !== CONFIG.STEP_INDEX_PERSONAL_INFO) return false;

        const el = getElements();
        const dobInput = el.dobInput;
        if (!dobInput) return false;

        const result = validateAge(dobInput.value);
        return !result.isValid && dobInput.value.trim() !== '';
    }

    // ============================================================
    // EVENT HANDLERS
    // ============================================================

    function handleDOBInput() {
        const el = getElements();
        const dobInput = el.dobInput;

        if (!dobInput) return;

        dobInput.max = getMaxDate();

        dobInput.addEventListener('change', function() {
            validateDOBInput(this);
        });

        dobInput.addEventListener('input', function() {
            const result = validateDOBInput(this);
            updateNextButtons();
            updateSubmitButton();
        });

        dobInput.addEventListener('focus', function() {
            if (this.value.trim() === '') {
                clearDOBMessage(this);
            }
        });

        dobInput.addEventListener('blur', function() {
            if (this.value.trim() !== '') {
                validateDOBInput(this);
            }
        });

        if (dobInput.value.trim() !== '') {
            validateDOBInput(dobInput);
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

                // ✅ Block if age is invalid on Step 1
                if (hasInvalidAgeInStep(currentStepIndex)) {
                    e.preventDefault();
                    e.stopPropagation();

                    if (el.errorDiv) {
                        el.errorDiv.textContent = '⚠️ You must be at least 18 years old to apply.';
                        el.errorDiv.style.display = 'block';
                        el.errorDiv.style.color = 'red';
                    }

                    const dobInput = el.dobInput;
                    if (dobInput) {
                        dobInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        dobInput.focus();
                    }
                    return false;
                }

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
            const dobInput = el.dobInput;
            if (!dobInput) return;

            const result = validateDOBInput(dobInput);

            if (!result.isValid && dobInput.value.trim() !== '') {
                e.preventDefault();

                if (el.errorDiv) {
                    el.errorDiv.textContent = '⚠️ You must be at least 18 years old to apply.';
                    el.errorDiv.style.display = 'block';
                    el.errorDiv.style.color = 'red';
                }

                dobInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                dobInput.focus();
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

    // ============================================================
    // INITIALIZATION
    // ============================================================

    function init() {
        console.log('🚀 Initializing Age validation module...');

        const el = getElements();
        if (!el.dobInput) {
            console.warn('⚠️ No DOB input found - skipping age validation');
            return;
        }

        console.log('🎂 DOB input found:', el.dobInput.id || el.dobInput.name);

        handleDOBInput();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();

        console.log('✅ Age validation module initialized successfully');
        console.log(`📋 Minimum age: ${CONFIG.MIN_AGE} years`);
    }

    // ============================================================
    // EXPOSE PUBLIC API
    // ============================================================

    window.AgeValidation = {
        validateAge: validateAge,
        validateDOBInput: validateDOBInput,
        getMaxDate: getMaxDate,
        hasInvalidAgeInStep: hasInvalidAgeInStep,
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

    console.log('📦 Age validation module ready');

})();