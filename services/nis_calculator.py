# services/nis_calculator.py
from decimal import Decimal
from constance import config
import logging

logger = logging.getLogger(__name__)

class NISCalculator:
    """NIS contribution calculation service"""

    @staticmethod
    def calculate_nis(gross_income: Decimal) -> dict:
        """Calculate NIS: 11% of gross income (or configured rate)"""

        if not getattr(config, 'NIS_ENABLED', True):
            return {
                'monthly_nis': Decimal('0.00'),
                'annual_nis': Decimal('0.00'),
                'ceiling_applied': False,
                'rate': Decimal('0.00'),
                'ceiling_amount': None,
            }

        nis_rate = Decimal(str(getattr(config, 'NIS_RATE', '0.11')))

        annual_income = gross_income * 12

        # ✅ Convert monthly ceiling to annual (multiply by 12)
        nis_ceiling = getattr(config, 'NIS_CEILING', None)
        if nis_ceiling:
            nis_ceiling = Decimal(str(nis_ceiling)) * 12  # ✅ THIS IS THE FIX

        ceiling_applied = False

        if nis_ceiling:
            if annual_income > nis_ceiling:
                annual_income_for_nis = nis_ceiling
                ceiling_applied = True
            else:
                annual_income_for_nis = annual_income
        else:
            annual_income_for_nis = annual_income

        annual_nis = annual_income_for_nis * nis_rate
        monthly_nis = annual_nis / 12

        return {
            'monthly_nis': monthly_nis,
            'annual_nis': annual_nis,
            'ceiling_applied': ceiling_applied,
            'rate': nis_rate,
            'ceiling_amount': nis_ceiling,
        }