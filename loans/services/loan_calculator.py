# loans/services/loan_calculator.py

from decimal import Decimal

class LoanCalculator:
    """Centralized loan calculation - SINGLE SOURCE OF TRUTH"""
    
    @staticmethod
    def calculate(loan):
        """Calculate all loan totals from payments"""
        payments = loan.payments.filter(
            status='CONFIRMED',
            is_reversed=False
        )
        
        total_paid = Decimal('0.00')
        total_principal_paid = Decimal('0.00')
        total_interest_paid = Decimal('0.00')
        total_deposit_paid = Decimal('0.00')
        
        for payment in payments:
            total_paid += payment.amount
            total_principal_paid += payment.principal_applied
            total_interest_paid += payment.interest_applied
            if payment.category == 'DEPOSIT':
                total_deposit_paid += payment.amount
        
        outstanding = loan.principal_amount - total_principal_paid
        if outstanding < 0:
            outstanding = Decimal('0.00')
        
        deposit_complete = total_deposit_paid >= loan.deposit_target if loan.deposit_target > 0 else False
        
        return {
            'total_paid': total_paid,
            'total_principal_paid': total_principal_paid,
            'total_interest_paid': total_interest_paid,
            'total_deposit_paid': total_deposit_paid,
            'outstanding_balance': outstanding,
            'deposit_complete': deposit_complete,
        }
    
    @staticmethod
    def update_loan(loan):
        """Update loan with calculated values"""
        calc = LoanCalculator.calculate(loan)
        loan.total_paid = calc['total_paid']
        loan.total_principal_paid = calc['total_principal_paid']
        loan.total_interest_paid = calc['total_interest_paid']
        loan.outstanding_balance = calc['outstanding_balance']
        loan.deposit_paid = calc['total_deposit_paid']
        loan.deposit_complete = calc['deposit_complete']
        loan.save()
        return loan