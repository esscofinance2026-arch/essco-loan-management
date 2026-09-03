/**
 * email-validation.js
 * Handles email validation with instant feedback
 * 
 * Logic:
 * - Validates email format using RFC 5322 compliant regex
 * - Shows real-time feedback as user types
 * - Blocks navigation if email is invalid
 * - Works with all email fields on the page
 */

(function() {
    'use strict';

    console.log('📧 Email validation module loaded');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    const CONFIG = {
        // Step where email validation should happen (Step 1 - Personal Information)
        STEP_INDEX_PERSONAL_INFO: 0,
        // CSS selector for email inputs
        EMAIL_SELECTOR: 'input[type="email"], input[name$="email"], input[name$="Email"], #id_email, #id_Reference1_Email, #id_Reference2_Email',
        // Allowed domains (optional - leave empty to allow all)
        ALLOWED_DOMAINS: [], // e.g., ['gmail.com', 'yahoo.com', 'hotmail.com']
        // Blocked domains (optional)
        BLOCKED_DOMAINS: ['tempmail.com', '10minutemail.com', 'guerrillamail.com'],
        // Minimum length for email
        MIN_LENGTH: 5,
        // Maximum length for email (RFC 5322 standard)
        MAX_LENGTH: 254,
    };

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    let elements = null;

    function getElements() {
        if (elements) return elements;

        elements = {
            // All email inputs on the page
            emailInputs: document.querySelectorAll(CONFIG.EMAIL_SELECTOR),
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
    // EMAIL VALIDATION FUNCTIONS
    // ============================================================

    /**
     * Gets the label for an email input field
     * @param {HTMLInputElement} input - The input element
     * @returns {string} The field label
     */
    function getFieldLabel(input) {
        if (!input) return 'Email';
        
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
        return name.replace(/_/g, ' ').replace(/[0-9]/g, '').trim() || 'Email';
    }

    /**
     * Validates an email address
     * RFC 5322 compliant regex pattern
     * @param {string} email - The email address to validate
     * @returns {Object} { isValid: boolean, message: string, cleaned: string }
     */
    function validateEmail(email) {
        if (!email || email.trim() === '') {
            return {
                isValid: false,
                message: '📧 Please enter your email address.',
                cleaned: ''
            };
        }

        const trimmed = email.trim();
        
        // Check minimum length
        if (trimmed.length < CONFIG.MIN_LENGTH) {
            return {
                isValid: false,
                message: `📧 Email is too short (minimum ${CONFIG.MIN_LENGTH} characters).`,
                cleaned: trimmed
            };
        }

        // Check maximum length
        if (trimmed.length > CONFIG.MAX_LENGTH) {
            return {
                isValid: false,
                message: `📧 Email is too long (maximum ${CONFIG.MAX_LENGTH} characters).`,
                cleaned: trimmed
            };
        }

        // RFC 5322 compliant regex pattern
        // This pattern validates most email formats including:
        // - user@domain.com
        // - user.name@domain.co.uk
        // - user+filter@domain.com
        const pattern = /^(?![.])[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
        
        if (!pattern.test(trimmed)) {
            return {
                isValid: false,
                message: '📧 Please enter a valid email address (e.g., user@example.com).',
                cleaned: trimmed
            };
        }

        // Extract domain for additional validation
        const domain = trimmed.split('@')[1].toLowerCase();
        
        // Check if domain is blocked
        if (CONFIG.BLOCKED_DOMAINS.includes(domain)) {
            return {
                isValid: false,
                message: '📧 Please use a permanent email address (no temporary/disposable emails).',
                cleaned: trimmed
            };
        }

        // Check if domain is allowed (if ALLOWED_DOMAINS is set)
        if (CONFIG.ALLOWED_DOMAINS.length > 0 && !CONFIG.ALLOWED_DOMAINS.includes(domain)) {
            return {
                isValid: false,
                message: `📧 Only ${CONFIG.ALLOWED_DOMAINS.join(', ')} domains are allowed.`,
                cleaned: trimmed
            };
        }

        // Check for common typos
        const commonTypos = {
            'gmail.com': ['gmai.com', 'gmial.com', 'gamil.com', 'gmal.com', 'gmail.co'],
            'yahoo.com': ['yaho.com', 'yahooo.com', 'yhoo.com', 'yahoo.co'],
            'hotmail.com': ['hotmai.com', 'hotmail.co', 'hotmial.com', 'hotmal.com'],
            'outlook.com': ['outlok.com', 'outook.com', 'outllok.com'],
            'icloud.com': ['iclud.com', 'iclod.com', 'icloud.co'],
        };

        // Check for typos
        for (const [correctDomain, typos] of Object.entries(commonTypos)) {
            if (typos.includes(domain)) {
                return {
                    isValid: true, // Still considered valid but with a warning
                    message: `✉️ Did you mean ${correctDomain}?`,
                    cleaned: trimmed,
                    isWarning: true
                };
            }
        }

        return {
            isValid: true,
            message: '✅ Valid email address',
            cleaned: trimmed,
            isWarning: false
        };
    }

    /**
     * Validates ALL email inputs on the page
     * @returns {Object} { isValid: boolean, errors: string[], emails: {} }
     */
    function validateAllEmails() {
        const el = getElements();
        const errors = [];
        const emails = {};
        let isValid = true;

        el.emailInputs.forEach(input => {
            // Skip hidden inputs
            if (input.type === 'hidden') return;
            
            const email = input.value;
            const label = getFieldLabel(input);
            const result = validateEmail(email);

            // Store cleaned email for potential use
            emails[input.id || input.name] = result.cleaned;

            // Only show error if field has a value OR is required
            const isRequired = input.hasAttribute('required') || 
                              input.closest('.form-group')?.querySelector('.required') !== null;
            
            if (!result.isValid && (email.trim() !== '' || isRequired)) {
                isValid = false;
                const fieldLabel = label || 'Email';
                errors.push(`📧 ${fieldLabel}: ${result.message}`);
                
                // Highlight the invalid input
                input.style.border = '2px solid #ff4444';
                input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
            } else if (result.isValid && email.trim() !== '') {
                // Clear error styling for valid emails
                input.style.border = '2px solid #28a745';
                input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
            } else {
                // Reset styling
                input.style.border = '';
                input.style.backgroundColor = '';
            }
        });

        return { isValid, errors, emails };
    }

    /**
     * Creates or gets the error div for an email input
     * @param {HTMLInputElement} input - The input element
     * @returns {HTMLElement} The error div
     */
    function getEmailErrorDiv(input) {
        if (!input) return null;

        let errorDiv = input.parentElement.querySelector('.email-error-message');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'email-error-message';
            errorDiv.style.fontSize = '13px';
            errorDiv.style.marginTop = '4px';
            input.parentElement.appendChild(errorDiv);
        }
        return errorDiv;
    }

    /**
     * Shows validation message for an email input
     * @param {HTMLInputElement} input - The email input element
     * @param {string} message - The message to display
     * @param {boolean} isSuccess - Whether it's a success message
     * @param {boolean} isWarning - Whether it's a warning message
     */
    function showEmailMessage(input, message, isSuccess = false, isWarning = false) {
        if (!input) return;

        const errorDiv = getEmailErrorDiv(input);
        if (!errorDiv) return;

        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        
        if (isWarning) {
            errorDiv.style.color = '#ff9800'; // Orange warning
            input.style.border = '2px solid #ff9800';
            input.style.backgroundColor = 'rgba(255, 152, 0, 0.05)';
        } else if (isSuccess) {
            errorDiv.style.color = 'green';
            input.style.border = '2px solid #28a745';
            input.style.backgroundColor = 'rgba(40, 167, 69, 0.05)';
        } else {
            errorDiv.style.color = 'red';
            input.style.border = '2px solid #ff4444';
            input.style.backgroundColor = 'rgba(255, 68, 68, 0.05)';
        }
    }

    /**
     * Clears validation message for an email input
     * @param {HTMLInputElement} input - The email input element
     */
    function clearEmailMessage(input) {
        if (!input) return;

        const errorDiv = input.parentElement.querySelector('.email-error-message');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        // Reset input styling
        input.style.border = '';
        input.style.backgroundColor = '';
    }

    /**
     * Validates a single email input in real-time
     * @param {HTMLInputElement} input - The email input element
     */
    function validateEmailInput(input) {
        if (!input) return;

        const email = input.value;
        
        // Skip if empty and not required
        if (email.trim() === '' && !input.hasAttribute('required')) {
            clearEmailMessage(input);
            return { isValid: true, message: '', cleaned: '' };
        }

        const result = validateEmail(email);

        if (!result.isValid) {
            showEmailMessage(input, result.message, false, false);
        } else if (result.isValid && email.trim() !== '') {
            showEmailMessage(input, result.message, true, result.isWarning || false);
        } else {
            clearEmailMessage(input);
        }

        return result;
    }

    // ============================================================
    // EVENT HANDLERS
    // ============================================================

    /**
     * Handles real-time validation for ALL email inputs
     */
    function handleEmailInputs() {
        const el = getElements();

        el.emailInputs.forEach(input => {
            // Skip hidden inputs
            if (input.type === 'hidden') return;

            // Validate on input (as user types)
            input.addEventListener('input', function() {
                validateEmailInput(this);
            });

            // Validate on blur (when user leaves the field)
            input.addEventListener('blur', function() {
                const result = validateEmailInput(this);
                // If invalid and has value, show error
                if (!result.isValid && this.value.trim() !== '') {
                    showEmailMessage(this, result.message, false, false);
                }
            });

            // Clear validation on focus
            input.addEventListener('focus', function() {
                if (this.value.trim() === '') {
                    clearEmailMessage(this);
                }
            });
        });
    }

    /**
     * Handles "Next" button clicks - validates all emails on Step 1
     */
    function handleNextButton() {
        const el = getElements();

        el.nextBtns.forEach(button => {
            button.addEventListener('click', function(e) {
                console.log('➡️ Next button clicked - validating emails...');

                const stepContainer = this.closest('.step');
                if (!stepContainer) return;

                const steps = document.querySelectorAll('.step');
                const currentStepIndex = Array.from(steps).indexOf(stepContainer);

                // ⭐ If this is Step 1 (Personal Information), validate all emails
                if (currentStepIndex === CONFIG.STEP_INDEX_PERSONAL_INFO) {
                    console.log('🔍 Validating ALL emails on Step 1');

                    const result = validateAllEmails();

                    if (!result.isValid) {
                        console.log('❌ Email validation failed:', result.errors);
                        
                        // Show main error
                        if (el.errorDiv) {
                            el.errorDiv.textContent = '⚠️ Please fix the email addresses below.';
                            el.errorDiv.style.display = 'block';
                            el.errorDiv.style.color = 'red';
                        }

                        // Scroll to first invalid email
                        const firstInvalid = document.querySelector('input[type="email"][style*="border: 2px solid rgb(255, 68, 68)"]');
                        if (firstInvalid) {
                            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            firstInvalid.focus();
                        }
                        return; // ⭐ BLOCK navigation
                    }

                    console.log('✅ All emails valid');
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
            console.log('📤 Form submission - validating ALL emails...');

            const result = validateAllEmails();

            if (!result.isValid) {
                console.log('❌ Email validation failed:', result.errors);
                e.preventDefault();

                if (el.errorDiv) {
                    el.errorDiv.textContent = '⚠️ Please fix the email addresses below.';
                    el.errorDiv.style.display = 'block';
                    el.errorDiv.style.color = 'red';
                }

                // Scroll to first invalid email
                const firstInvalid = document.querySelector('input[type="email"][style*="border: 2px solid rgb(255, 68, 68)"]');
                if (firstInvalid) {
                    firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstInvalid.focus();
                }
                return false;
            }

            console.log('✅ All emails valid - submitting form');
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
        console.log('🚀 Initializing email validation module...');

        const el = getElements();
        if (!el.emailInputs || el.emailInputs.length === 0) {
            console.warn('⚠️ No email inputs found - skipping email validation');
            return;
        }

        console.log(`📧 Found ${el.emailInputs.length} email input(s):`);
        el.emailInputs.forEach(input => {
            console.log(`  - ${input.id || input.name || 'unnamed'}`);
        });

        // Initialize all event handlers
        handleEmailInputs();
        handleNextButton();
        handleFormSubmit();
        handleConfirmCheckbox();

        console.log('✅ Email validation module initialized successfully');
        console.log(`📍 Personal info step: ${CONFIG.STEP_INDEX_PERSONAL_INFO + 1}`);
    }

    // ============================================================
    // EXPOSE PUBLIC API
    // ============================================================

    window.EmailValidation = {
        validateEmail: validateEmail,
        validateAllEmails: validateAllEmails,
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

    console.log('📦 Email validation module ready');

})();