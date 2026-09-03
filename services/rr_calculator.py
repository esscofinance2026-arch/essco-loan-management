# services/rr_calculator.py
from decimal import Decimal
from constance import config
import logging

logger = logging.getLogger(__name__)

class RRCalculator:
    """Resilience & Regeneration contribution calculation service"""
    
    @staticmethod
    def calculate_rr(gross_income: Decimal) -> dict:
        """Calculate RR: 0.25% of gross income (0.0025 × gross)"""
        
        if not getattr(config, 'RR_ENABLED', True):
            return {
                'monthly_rr': Decimal('0.00'),
                'annual_rr': Decimal('0.00'),
                'ceiling_applied': False,
                'rate': Decimal('0.00'),
                'ceiling_amount': None,
            }
        
        rr_rate = Decimal(str(getattr(config, 'RR_RATE', '0.0025')))
        annual_income = gross_income * 12
        
        rr_ceiling = getattr(config, 'RR_CEILING', None)
        ceiling_applied = False
        
        if rr_ceiling:
            rr_ceiling = Decimal(str(rr_ceiling))
            if annual_income > rr_ceiling:
                annual_income_for_rr = rr_ceiling
                ceiling_applied = True
            else:
                annual_income_for_rr = annual_income
        else:
            annual_income_for_rr = annual_income
        
        annual_rr = annual_income_for_rr * rr_rate
        monthly_rr = annual_rr / 12
        
        return {
            'monthly_rr': monthly_rr,
            'annual_rr': annual_rr,
            'ceiling_applied': ceiling_applied,
            'rate': rr_rate,
            'ceiling_amount': rr_ceiling,
        }