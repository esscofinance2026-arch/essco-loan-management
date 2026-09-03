// static/js/form_handler.js - MINIMAL FIXED VERSION

document.addEventListener('DOMContentLoaded', function() {
    console.log('🔧 Form handler loaded');
    
    const form = document.getElementById('applicationForm');
    const submitBtn = document.getElementById('submit-btn');
    
    if (!form) {
        console.error('❌ Form not found');
        return;
    }
    
    if (!submitBtn) {
        console.error('❌ Submit button not found');
        return;
    }
    
    console.log('✅ Form and submit button found');
    
    // ✅ Simple version - just disable button on submit
    form.addEventListener('submit', function(e) {
        console.log('🔄 Form submitted');
        
        // ✅ Disable button
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
        
        // ✅ Allow form to submit normally
        // The browser will handle the redirect
    });
});