/**
 * phone-validation.js
 * Handles phone number validation for ALL phone fields
 *
 * Logic:
 * - Validates ALL phone number fields on the page
 * - Shows real-time feedback as user types
 * - Blocks navigation if any phone number is invalid
 * - Works with any country using simple rules
 */

(function() {
    'use strict';

    console.log('📱 Phone validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        // Default region (change this to your country)
        DEFAULT_REGION: 'BB',  // Barbados
        // Minimum length for any phone number
        MIN_LENGTH: 7,
        // Maximum length for any phone number
        MAX_LENGTH: 15,
        // CSS selector for phone inputs (customize as needed)
        PHONE_SELECTOR: 'input[type="tel"], input[name$="Phone"], input[name$="Contact_Number"], #id_Cell_Phone, #id_Reference1_Contact_Number, #id_Reference2_Contact_Number',
        // Step where phone validation should happen (Step 1 - Personal Information)
        STEP_INDEX_PERSONAL_INFO: 0,
    };

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = null;

    function getElements() {
        if (elements) return elements;

        elements = {
            // All phone inputs on the page
            phoneInputs: document.querySelectorAll(CONFIG.PHONE_SELECTOR),
            form: document.getElementById('applicationForm'),
            nextBtns: document.querySelectorAll('.next-btn'),
            submitBtn: document.getElementById('submit-btn'),
            steps: document.querySelectorAll('.step'),
            errorDiv: document.getElementById('errorMessage'),
        };

        return elements;
    }

    // ============================================================
    // PHONE VALIDATION FUNCTIONS
    // ============================================================

    /**
     * Cleans a phone number by removing non-numeric characters
     * @param {string} phone - The phone number to clean
     * @returns {string} Cleaned phone number (digits only)
     */
    function cleanPhoneNumber(phone) {
        if (!phone) return '';
        return phone.replace(/\D/g, '');
    }

    /**
     * Gets the label for a phone input field
     * @param {HTMLInputElement} input - The input element
     * @returns {string} The field label
     */
    function getFieldLabel(input) {
        if (!input) return 'Phone';

        // Try to find label by for attribute
        const label = document.querySelector(`label[for="${input.id}"]`);
        if (label) {
            return label.textContent.trim().replace(/[:*]/g, '').trim();
        }

        // Try to find label parent
        const parentLabel = input.closest('label');
        if (parentLabel) {
            return parentLabel.textContent.trim().replace(/[:*]/g, '').trim();
        }

        // Use name or id
        const name = input.name || input.id || '';
        return name.replace(/_/g, ' ').replace(/[0-9]/g, '').trim() || 'Phone';
    }

    /**
     * Validates a single phone number - SIMPLIFIED VERSION
     * @param {string} phone - The phone number to validate
     * @param {string} region - The region/country code
     * @returns {Object} { isValid: boolean, message: string, cleaned: string }
     */
    function validateSinglePhone(phone, region = CONFIG.DEFAULT_REGION) {
        if (!phone || phone.trim() === '') {
            return {
                isValid: false,
                message: 'Please enter a phone number.',
                cleaned: ''
            };
        }

        // Remove ALL non-numeric characters
        const cleaned = phone.replace(/\D/g, '');

        // Check if empty after cleaning
        if (!cleaned) {
            return {
                isValid: false,
                message: 'Please enter a valid phone number.',
                cleaned: ''
            };
        }

        // ⭐ SIMPLE RULES:
        // - Minimum 7 digits (local Barbados number)
        // - Maximum 15 digits (international)
        if (cleaned.length < 7) {
            return {
                isValid: false,
                message: 'Phone number is too short (minimum 7 digits).',
                cleaned: cleaned
            };
        }

        if (cleaned.length > 15) {
            return {
                isValid: false,
                message: 'Phone number is too long (maximum 15 digits).',
                cleaned: cleaned
            };
        }

        // ✅ Accept ALL phone numbers between 7-15 digits
        // No need to validate area codes or country codes
        return {
            isValid: true,
            message: '✅ Valid phone number',
            cleaned: cleaned
        };
    }

    /**
     * Validates ALL phone inputs on the page
     * @returns {Object} { isValid: boolean, errors: string[], cleanedNumbers: {} }
     */
    function validateAllPhones() {
        const el = getElements();
        const errors = [];
        const cleanedNumbers = {};
        let isValid = true;

        el.phoneInputs.forEach(input => {
            // Skip hidden inputs
            if (input.type === 'hidden') return;

            const phone = input.value;
            const label = getFieldLabel(input);
            const result = validateSinglePhone(phone);

            // Store cleaned number for potential use
            cleanedNumbers[input.id || input.name] = result.cleaned;

            // Only show error if field has a value OR is required
            const isRequired = input.hasAttribute('required') || input.closest('.form-group')?.querySelector('.required') !== null;

            if (!result.isValid && (phone.trim() !== '' || isRequired)) {
                isValid = false;
                const fieldLabel = label || 'Phone';
                errors.push(`📱 ${fieldLabel}: ${result.message}`);

                // Highlight the invalid input
                input.style.border = '2px solid #ff4444';
                input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
            } else {
                // Clear any previous error styling
                input.style.border = '';
                input.style.backgroundColor = '';
            }
        });

        return { isValid, errors, cleanedNumbers };
    }

    /**
     * Creates or gets the error div for a phone input
     * @param {HTMLInputElement} input - The phone input element
     * @returns {HTMLElement} The error div
     */
    function getPhoneErrorDiv(input) {
        if (!input) return null;

        let errorDiv = input.parentElement.querySelector('.phone-error-message');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'phone-error-message';
            errorDiv.style.fontSize = '13px';
            errorDiv.style.marginTop = '4px';
            input.parentElement.appendChild(errorDiv);
        }
        return errorDiv;
    }

    /**
     * Shows validation message for a phone input
     * @param {HTMLInputElement} input - The phone input element
     * @param {string} message - The message to display
     * @param {boolean} isSuccess - Whether it's a success message
     */
    function showPhoneMessage(input, message, isSuccess = false) {
        if (!input) return;

        const errorDiv = getPhoneErrorDiv(input);
        if (!errorDiv) return;

        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        errorDiv.style.color = isSuccess ? 'green' : 'red';

        // Style the input
        if (isSuccess) {
            input.style.border = '2px solid #28a745';
            input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
        } else {
            input.style.border = '2px solid #ff4444';
            input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
        }
    }

    /**
     * Clears validation message for a phone input
     * @param {HTMLInputElement} input - The phone input element
     */
    function clearPhoneMessage(input) {
        if (!input) return;

        const errorDiv = input.parentElement.querySelector('.phone-error-message');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        // Reset input styling
        input.style.border = '';
        input.style.backgroundColor = '';
    }

    /**
     * Validates a single phone input in real-time
     * @param {HTMLInputElement} input - The phone input element
     */
    function validatePhoneInput(input) {
        if (!input) return;

        const phone = input.value;

        // Skip if empty and not required
        if (phone.trim() === '' && !input.hasAttribute('required')) {
            clearPhoneMessage(input);
            return { isValid: true, message: '', cleaned: '' };
        }

        const result = validateSinglePhone(phone);

        if (!result.isValid) {
            showPhoneMessage(input, `📱 ${result.message}`, false);
        } else if (result.isValid && phone.trim() !== '') {
            showPhoneMessage(input, `✅ Valid phone number`, true);
        } else {
            clearPhoneMessage(input);
        }

        return result;
    }

    // ============================================================
    // EVENT HANDLERS
    // ============================================================

    /**
     * Handles real-time validation for ALL phone inputs
     */
    function handlePhoneInputs() {
        const el = getElements();

        el.phoneInputs.forEach(input => {
            // Skip hidden inputs
            if (input.type === 'hidden') return;

            // Validate on input (as user types)
            input.addEventListener('input', function() {
                validatePhoneInput(this);
            });

            // Validate on blur (when user leaves the field)
            input.addEventListener('blur', function() {
                const result = validatePhoneInput(this);
                // If invalid and has value, show error
                if (!result.isValid && this.value.trim() !== '') {
                    showPhoneMessage(this, `📱 ${result.message}`, false);
                }
            });

            // Clear validation on focus
            input.addEventListener('focus', function() {
                if (this.value.trim() === '') {
                    clearPhoneMessage(this);
                }
            });
        });
    }

    /**
     * Handles "Next" button clicks - validates all phones on Step 1
     */
    function handleNextButton() {
        const el = getElements();

        el.nextBtns.forEach(button => {
            button.addEventListener('click', function(e) {
                console.log('➡️ Next button clicked - validating phones...');

                const stepContainer = this.closest('.step');
                if (!stepContainer) return;

                const steps = document.querySelectorAll('.step');
                const currentStepIndex = Array.from(steps).indexOf(stepContainer);

                // ⭐ If this is Step 1 (Personal Information), validate all phones
                if (currentStepIndex === CONFIG.STEP_INDEX_PERSONAL_INFO) {
                    console.log('🔍 Validating ALL phones on Step 1');

                    const result = validateAllPhones();

                    if (!result.isValid) {
                        console.log('❌ Phone validation failed:', result.errors);

                        // Show main error
                        if (el.errorDiv) {
                            el.errorDiv.textContent = '⚠️ Please fix the phone numbers below.';
                            el.errorDiv.style.display = 'block';
                            el.errorDiv.style.color = 'red';
                        }

                        // Scroll to first invalid phone
                        const firstInvalid = document.querySelector('input[type="tel"][style*="border: 2px solid rgb(255, 68, 68)"], input[name$="Phone"][style*="border: 2px solid rgb(255, 68, 68)"]');
                        if (firstInvalid) {
                            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            firstInvalid.focus();
                        }
                        return; // ⭐ BLOCK navigation
                    }

                    console.log('✅ All phones valid');
                    if (el.errorDiv) {
                        el.errorDiv.style.display = 'none';
                    }
                }
            });
        });
    }

    /**
     * Handles form submission with final validation
     */
    function handleFormSubmit() {
        const el = getElements();

        if (!el.form) return;

        el.form.addEventListener('submit', function(e) {
            console.log('📤 Form submission - validating ALL phones...');

            const result = validateAllPhones();

            if (!result.isValid) {
                console.log('❌ Phone validation failed:', result.errors);
                e.preventDefault();

                if (el.errorDiv) {
                    el.errorDiv.textContent = '⚠️ Please fix the phone numbers below.';
                    el.errorDiv.style.display = 'block';
                    el.errorDiv.style.color = 'red';
                }

                // Scroll to first invalid phone
                const firstInvalid = document.querySelector('input[type="tel"][style*="border: 2px solid rgb(255, 68, 68)"], input[name$="Phone"][style*="border: 2px solid rgb(255, 68, 68)"]');
                if (firstInvalid) {
                    firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstInvalid.focus();
                }
                return false;
            }

            console.log('✅ All phones valid - submitting form');
            if (el.errorDiv) {
                el.errorDiv.style.display = 'none';
            }
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
        console.log('🚀 Initializing phone validation module...');

        const el = getElements();
        if (!el.phoneInputs || el.phoneInputs.length === 0) {
            console.warn('⚠️ No phone inputs found - skipping phone validation');
            return;
        }

        console.log(`📱 Found ${el.phoneInputs.length} phone input(s):`);
        el.phoneInputs.forEach(input => {
            console.log(`  - ${input.id || input.name || 'unnamed'}`);
        });

        // Initialize all event handlers
        handlePhoneInputs();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();

        console.log('✅ Phone validation module initialized successfully');
        console.log(`📍 Personal info step: ${CONFIG.STEP_INDEX_PERSONAL_INFO + 1}`);
    }

    // ============================================================
    // EXPOSE PUBLIC API
    // ============================================================

    window.PhoneValidation = {
        validateSinglePhone: validateSinglePhone,
        validateAllPhones: validateAllPhones,
        cleanPhoneNumber: cleanPhoneNumber,
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

    console.log('📦 Phone validation module ready');

})();