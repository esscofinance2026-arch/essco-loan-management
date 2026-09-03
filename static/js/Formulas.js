function calculateLoan() {
    // Get values
    const loanAmount = parseFloat(document.getElementById('loanAmount').value) || 0;
    const months = parseInt(document.getElementById('months').value) || 1;
    const annualRate = parseFloat(document.getElementById('interestRate').value) || 0;
    
    // Calculate monthly interest rate
    const monthlyRate = annualRate / 100 / 12;
    
    // Calculate monthly payment
    let monthlyPayment = 0;
    if (monthlyRate === 0) {
        monthlyPayment = loanAmount / months;
    } else {
        monthlyPayment = loanAmount * (monthlyRate * Math.pow(1 + monthlyRate, months)) / (Math.pow(1 + monthlyRate, months) - 1);
    }
    
    // Update summary
    document.getElementById('summaryAmount').textContent = `$${loanAmount.toFixed(2)}`;
    document.getElementById('summaryRate').textContent = `${annualRate}%`;
    document.getElementById('summaryMonths').textContent = months;
    
    // Update monthly payment
    document.getElementById('monthlyPayment').textContent = `$${monthlyPayment.toFixed(2)}`;
}

// Auto-calculate on input change
document.addEventListener('DOMContentLoaded', function() {
    const inputs = ['loanAmount', 'months', 'interestRate'];
    inputs.forEach(id => {
        const el = document.getElementById(id);
        el.addEventListener('input', calculateLoan);
        el.addEventListener('change', calculateLoan);
    });
    
    // Initial calculation
    calculateLoan();
});