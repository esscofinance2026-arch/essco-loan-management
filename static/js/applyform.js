document.addEventListener('DOMContentLoaded', function() {
    // ============================================================
    // DOM ELEMENT REFERENCES
    // Store references to frequently used HTML elements.
    // ============================================================

    const steps = document.querySelectorAll(".step");
    const nextBtns = document.querySelectorAll(".next-btn");
    const prevBtns = document.querySelectorAll(".prev-btn");
    const progressFill = document.getElementById("progress-fill");
    const currentStepText = document.getElementById("current-step");
    const confirmCheck = document.getElementById("confirm-check");
    const submitBtn = document.getElementById("submit-btn");
    const lessThanSix = document.getElementById("id_less_than_six");
    const LenEmploy = document.getElementById("id_Len_Employ");
    const previousEmployer = document.getElementById("previous-employer-group");
    const previousEmployerfield = document.getElementById("id_Previous_Employer");
    //const lessThanSixOption = document.querySelector('#id_Len_Employ option[value="Less than 6 months"]');
    const dob = document.getElementById("id_DOB");

    // Makes sure the user is 18 years or older
    if (dob)
    {
        const maxDOB = new Date();
        maxDOB.setFullYear(maxDOB.getFullYear() - 18);

        dob.max = maxDOB.toISOString().split("T")[0];
    }

    // ============================================================
    // DEBUGGING
    // Verify that important elements were found.
    // Remove these console logs in production if no longer needed.
    // ============================================================

    console.log('Checkbox found:', confirmCheck);
    console.log('Submit button found:', submitBtn);

    if (confirmCheck && submitBtn) {
        confirmCheck.addEventListener("change", function () {
            submitBtn.disabled = !this.checked;
            console.log('Checkbox changed. Checked:', this.checked);
            console.log('Submit disabled:', submitBtn.disabled);
        });
    } else {
        console.error('Checkbox or submit button not found!');
    }

    let currentStep = 0;

    // ============================================================
    // Field Checker
    // Verify that the customer has not selected both "No" to the uestion "is your emplyment less than six months?"
    // and at the same time selecting the option "Less than six months"
    // ============================================================

    function isEmploymentValid() {

        if (!lessThanSix || !LenEmploy) return true;

        if (lessThanSix.value === "No" && LenEmploy.value === "Less than 6 months") {
            return false;
        }

        return true;
    }



    function updateEmploymentFields() {

        const option = Array.from(LenEmploy.options)
        .find(opt => opt.value === "Less than 6 months");

        if (lessThanSix.value === "Yes")
        {
            LenEmploy.value = "Less than 6 months";

            // LOCK UI (but still submits to Django)
            LenEmploy.style.pointerEvents = "none";
            LenEmploy.style.backgroundColor = "#e9ecef";

            previousEmployer.style.display = "block";
            previousEmployerfield.value = "Previous Employer";
        }
        else
        {
            LenEmploy.style.pointerEvents = "auto";
            LenEmploy.style.backgroundColor = "";

            previousEmployer.style.display = "none";

            // Add your value here
            previousEmployerfield.value = "N/A"; // 👈 Replace with your desired value

            // ❗ make it unselectable
            //if (option) {option.disabled = true;}
            // remove invalid value if it exists
            if (LenEmploy.value === "Less than 6 months") {
                LenEmploy.value = "2 + Years";
            }
        }
    }

    // Run when page loads
    updateEmploymentFields();

    // Run whenever selection changes
    if (lessThanSix) { lessThanSix.addEventListener("change", updateEmploymentFields);}
    //lessThanSix.addEventListener("change", updateEmploymentFields);


    // ============================================================
    // Function: isStepValid()
    // Purpose:
    // Validates all required fields on the current step before the
    // user is allowed to continue to the next section.
    //
    // Returns:
    // true  - All required fields are completed.
    // false - One or more required fields are missing.
    // ============================================================
    function isStepValid(stepIndex) {
        const currentStepEl = steps[stepIndex];
        if (!currentStepEl) return true;

        const inputs = currentStepEl.querySelectorAll('input, select, textarea');
        let isValid = true;

        inputs.forEach(input => {
            // Skip hidden fields, buttons, and checkboxes
            if (input.type === 'hidden' || input.type === 'submit' || input.type === 'button') {
                return;
            }

            // Check if field is required
            if (input.hasAttribute('required') || input.dataset.required === 'true') {
                let fieldIsValid = true;

                if (input.type === 'checkbox') {
                    fieldIsValid = input.checked;
                } else if (input.type === 'select-one' || input.type === 'select-multiple') {
                    fieldIsValid = input.value && input.value !== '';
                } else {
                    fieldIsValid = input.value && input.value.trim() !== '';
                }

                if (!fieldIsValid) {
                    isValid = false;
                    input.style.border = '2px solid #ff4444';
                    input.style.backgroundColor = 'rgba(255, 68, 68, 0.1)';

                    // Add error message
                    let errorMsg = input.parentElement.querySelector('.error-message');
                    if (!errorMsg) {
                        errorMsg = document.createElement('small');
                        errorMsg.className = 'error-message';
                        errorMsg.style.color = '#ff4444';
                        errorMsg.style.display = 'block';
                        errorMsg.textContent = 'This field is required';
                        input.parentElement.appendChild(errorMsg);
                    }
                } else {
                    input.style.border = '';
                    input.style.backgroundColor = '';
                    const errorMsg = input.parentElement.querySelector('.error-message');
                    if (errorMsg) {
                        errorMsg.remove();
                    }
                }
            }
        });

        return isValid;
    }

    // Check if steps exist before running
    if (steps.length > 0) {
        showStep(currentStep);
    } else {
        console.log('No steps found - single page form');
        if (progressFill) {
            progressFill.style.width = "100%";
        }
        if (currentStepText) {
            currentStepText.textContent = "1";
        }
    }

    // ============================================================
    // Function: showStep()
    // Purpose:
    // Displays the requested step, hides all others, updates the
    // progress bar, updates the current step indicator and builds
    // the review page when the user reaches the final step.
    // ============================================================

    function showStep(step) {
        steps.forEach((section, index) => {
            section.classList.toggle("active", index === step);
        });

        if (currentStepText) {
            currentStepText.textContent = step + 1;
        }

        if (progressFill) {
            const percentage = ((step + 1) / steps.length) * 100;
            progressFill.style.width = percentage + "%";
        }

        // Build review only on last step
        if (step === steps.length - 1) {
            buildReview();
        }
    }

    // ✅ SINGLE next button handler with validation
    nextBtns.forEach(button => {
        button.addEventListener("click", () => {
            // Check if current step is valid
            if (!isStepValid(currentStep)) {
                alert('Please fill in all required fields before proceeding.');
                return; // ✅ Stops advancement
            }
            //Check if the length of emloyement has valid selections
            if (!isEmploymentValid()) {
                alert("Invalid selection: You cannot choose 'Less than 6 months' when employment is No.");
                return; // 🚨 STOP HERE — do NOT move forward
            }
            // Only advance if validation passed
            if (currentStep < steps.length - 1) {
                currentStep++;
                showStep(currentStep);
            }
        });
    });

    // Previous button handler
    prevBtns.forEach(button => {
        button.addEventListener("click", () => {
            if (currentStep > 0) {
                currentStep--;
                showStep(currentStep);
            }
        });
    });

    // ============================================================
    // Function: buildReview()
    // Purpose:
    // Creates a summary of all information entered by the applicant.
    // The information is grouped into logical sections before being
    // displayed on the review page prior to submission.
    // ============================================================

    function buildReview() {
        const review = document.getElementById("review-content");
        if (!review) return;

        const form = document.querySelector(".application-container form");
        if (!form) return;

        const fields = form.querySelectorAll("input[name], select[name], textarea[name]");

        const sections = {
            "Personal Information": [],
            "Employment": [],
            "Financial": [],
            "References": []
        };

        function getLabel(field) {
            const label = document.querySelector(`label[for="${field.id}"]`);
            return label ? label.textContent.trim() : field.name.replaceAll("_", " ");
        }

        fields.forEach(field => {
            // Skip system / irrelevant inputs
            if (
                field.name === "csrfmiddlewaretoken" ||
                field.type === "hidden" ||
                field.type === "submit" ||
                field.id === "confirm-check"
            ) {
                return;
            }

            let value = field.value;

            if (field.type === "checkbox") {
                value = field.checked ? "Yes" : "No";
            }

            if (value === null || value === undefined || value === "") {
                return;
            }

            const label = getLabel(field);

            // Section logic
            if (field.name.includes("Reference")) {
                sections["References"].push({ label, value });
            }
            else if (
                field.name.includes("Employer") ||
                field.name.includes("Job") ||
                field.name.includes("Income") ||
                field.name.includes("Len_Employ") ||
                field.name.includes("less_than_two_years")
            ) {
                sections["Employment"].push({ label, value });
            }
            else if (
                field.name.includes("Purchase") ||
                field.name.includes("Rent") ||
                field.name.includes("Debt") ||
                field.name.includes("Payment") ||
                field.name.includes("Insurance") ||
                field.name.includes("food") ||
                field.name.includes("utilities")
            ) {
                sections["Financial"].push({ label, value });
            }
            else {
                sections["Personal Information"].push({ label, value });
            }
        });

        // Build output
        let html = `<h3>Application Summary</h3>`;

        for (const section in sections) {
            html += `
                <div class="review-section">
                    <h4>${section}</h4>
            `;

            if (sections[section].length === 0) {
                html += `<p class="no-data">No information provided.</p>`;
            } else {
                html += `<div class="review-grid">`;
                sections[section].forEach(item => {
                    html += `
                        <div class="review-row">
                            <div class="review-label">${item.label}</div>
                            <div class="review-value">${item.value}</div>
                        </div>
                    `;
                });
                html += `</div>`;
            }

            html += `</div>`;
        }

        review.innerHTML = html;
    }

}); // End of DOMContentLoaded