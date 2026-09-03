import json
from decimal import Decimal
from constance import config
import logging

logger = logging.getLogger(__name__)

class PAYECalculator:
    """PAYE (Income Tax) calculation service"""

    @staticmethod
    def calculate_paye(gross_income: Decimal) -> dict:
        """
        Calculate PAYE using progressive brackets.
        """
        # Check if PAYE is enabled
        if not getattr(config, 'PAYE_ENABLED', True):
            return {
                'monthly_paye': Decimal('0.00'),
                'annual_paye': Decimal('0.00'),
                'effective_rate': Decimal('0.00'),
                'breakdown': []
            }

        annual_income = gross_income * 12

        # ✅ Get brackets from constance, with default fallback
        brackets = getattr(config, 'PAYE_BRACKETS', None)

        # ✅ Convert JSON string to list of dictionaries
        if isinstance(brackets, str):
            brackets = json.loads(brackets)
        elif not brackets:
            brackets = [
                {'from': 0, 'to': 25000, 'rate': 0, 'label': 'Tax-Free'},
                {'from': 25000.01, 'to': 75000, 'rate': 11.5, 'label': 'Basic Rate'},
                {'from': 75000.01, 'to': 100000, 'rate': 27.5, 'label': 'Higher Rate'},
                {'from': 100000.01, 'to': None, 'rate': 27.5, 'label': 'Additional Rate'},
            ]

        remaining = annual_income
        total_annual_tax = Decimal('0.00')
        breakdown = []

        for bracket in brackets:
            if remaining <= 0:
                break

            from_amt = Decimal(str(bracket['from']))
            to_amt = Decimal(str(bracket['to'])) if bracket['to'] is not None else None
            rate = Decimal(str(bracket['rate']))

            if to_amt is None:
                taxable = remaining
            else:
                bracket_range = to_amt - from_amt
                taxable = min(remaining, bracket_range)

            # Ensure taxable is not negative
            if taxable < 0:
                taxable = Decimal('0.00')

            tax = taxable * (rate / Decimal('100'))
            total_annual_tax += tax

            if taxable > 0:
                breakdown.append({
                    'label': bracket['label'],
                    'rate': float(rate),
                    'taxable': float(taxable),
                    'tax': float(tax),
                })

            remaining -= taxable

        monthly_paye = total_annual_tax / 12
        effective_rate = (total_annual_tax / annual_income * Decimal('100')) if annual_income > 0 else Decimal('0.00')

        return {
            'monthly_paye': monthly_paye,
            'annual_paye': total_annual_tax,
            'effective_rate': effective_rate,
            'breakdown': breakdown,
        }