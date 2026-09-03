# services/payroll_service.py
from decimal import Decimal
from .paye_calculator import PAYECalculator
from .nis_calculator import NISCalculator
from .rr_calculator import RRCalculator
import logging

logger = logging.getLogger(__name__)

class PayrollService:
    """
    Complete payroll calculation service.
    Gross_Monthly_Income_AT = Gross_Income - (PAYE + NIS + RR)
    """
    
    @staticmethod
    def calculate_payroll(gross_income: Decimal) -> dict:
        """
        Calculate complete payroll with all deductions.
        
        Args:
            gross_income: Decimal - Monthly gross income
            
        Returns:
            dict: {
                'gross_income': Decimal,
                'gross_annual': Decimal,
                'paye': dict,
                'nis': dict,
                'rr': dict,
                'total_monthly_deductions': Decimal,
                'total_annual_deductions': Decimal,
                'gross_monthly_income_at': Decimal,
                'gross_annual_income_at': Decimal,
            }
        """
        # Ensure gross_income is Decimal
        if not isinstance(gross_income, Decimal):
            gross_income = Decimal(str(gross_income))
        
        # Calculate each deduction
        paye_result = PAYECalculator.calculate_paye(gross_income)
        nis_result = NISCalculator.calculate_nis(gross_income)
        rr_result = RRCalculator.calculate_rr(gross_income)
        
        # Get monthly values
        monthly_paye = paye_result['monthly_paye']
        monthly_nis = nis_result['monthly_nis']
        monthly_rr = rr_result['monthly_rr']
        
        # Total deductions
        total_monthly_deductions = monthly_paye + monthly_nis + monthly_rr
        total_annual_deductions = (
            paye_result['annual_paye'] + 
            nis_result['annual_nis'] + 
            rr_result['annual_rr']
        )
        
        # ⭐ CRITICAL: Calculate Gross_Monthly_Income_AT (Net Income)
        gross_monthly_income_at = gross_income - total_monthly_deductions
        
        return {
            'gross_income': gross_income,
            'gross_annual': gross_income * 12,
            
            # Individual deductions
            'paye': paye_result,
            'nis': nis_result,
            'rr': rr_result,
            
            # Totals
            'total_monthly_deductions': total_monthly_deductions,
            'total_annual_deductions': total_annual_deductions,
            
            # ⭐ THE KEY RESULT - Net Income
            'gross_monthly_income_at': gross_monthly_income_at,
            'gross_annual_income_at': gross_monthly_income_at * 12,
        }