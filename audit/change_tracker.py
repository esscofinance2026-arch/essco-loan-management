# audit/change_tracker.py
import logging
from decimal import Decimal
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ChangeTracker:
    """
    Service for tracking changes between original and updated model instances.
    """
    
    # Define which fields to track and how to display them
    FIELD_MAPPINGS = {
        'Fname': {'label': 'First Name', 'type': 'string'},
        'Lname': {'label': 'Last Name', 'type': 'string'},
        'ID_number': {'label': 'ID Number', 'type': 'string'},
        'Gross_Monthly_Income': {'label': 'Income', 'type': 'currency'},
        'Purchase_Value': {'label': 'Purchase Value', 'type': 'currency'},
        'Approval_Status': {'label': 'Approval Status', 'type': 'string'},
        'Final_Approval': {'label': 'Final Approval', 'type': 'string'},
        'Employer_Type': {'label': 'Employer Type', 'type': 'string'},
        'Term': {'label': 'Term', 'type': 'string'},
        'Total_Credit_Allowed': {'label': 'Credit Allowed', 'type': 'currency'},
        'Deposit': {'label': 'Deposit', 'type': 'currency'},
        'Six': {'label': '6-month Payment', 'type': 'currency'},
        'Twelve': {'label': '12-month Payment', 'type': 'currency'},
        'Eighteen': {'label': '18-month Payment', 'type': 'currency'},
        'Twenty_Four': {'label': '24-month Payment', 'type': 'currency'},
        'Thirty': {'label': '30-month Payment', 'type': 'currency'},
        'Thirty_Six': {'label': '36-month Payment', 'type': 'currency'},
        'Notes': {'label': 'Notes', 'type': 'text'},
        'Address': {'label': 'Address', 'type': 'string'},
        'Cell_Phone': {'label': 'Cell Phone', 'type': 'string'},
        'email': {'label': 'Email', 'type': 'string'},
        'Employer_Name': {'label': 'Employer Name', 'type': 'string'},
        'Job_Title': {'label': 'Job Title', 'type': 'string'},
        'Len_Employ': {'label': 'Length Employed', 'type': 'string'},
        'Residential_Status': {'label': 'Residential Status', 'type': 'string'},
        'Marital_Status': {'label': 'Marital Status', 'type': 'string'},
        'Num_Dependents': {'label': 'Dependents', 'type': 'integer'},
    }
    
    @staticmethod
    def get_original_values(instance) -> Dict[str, Any]:
        """
        Extract all tracked field values from an instance.
        """
        values = {}
        for field in ChangeTracker.FIELD_MAPPINGS.keys():
            if hasattr(instance, field):
                values[field] = getattr(instance, field)
        return values
    
    @staticmethod
    def format_value(value, field_type: str) -> str:
        """
        Format a value for display based on its type.
        """
        if value is None:
            return "None"
        
        if field_type == 'currency':
            try:
                return f"${float(value):,.2f}"
            except:
                return str(value)
        elif field_type == 'integer':
            return str(value)
        elif field_type == 'text':
            return "Updated"  # Just show "Updated" for text fields (Notes)
        else:
            return str(value)
    
    @staticmethod
    def track_changes(original_instance, updated_instance) -> List[str]:
        """
        Compare two instances and return a list of changes.
        """
        changes = []
        original_values = ChangeTracker.get_original_values(original_instance)
        
        for field, mapping in ChangeTracker.FIELD_MAPPINGS.items():
            old_value = original_values.get(field)
            new_value = getattr(updated_instance, field, None)
            
            # Skip if both are None or both are empty strings
            if (old_value is None or old_value == '') and (new_value is None or new_value == ''):
                continue
            
            # Compare values
            if old_value != new_value:
                label = mapping['label']
                field_type = mapping['type']
                
                # Special handling for text fields (Notes)
                if field_type == 'text':
                    changes.append(f"{label} updated")
                else:
                    old_display = ChangeTracker.format_value(old_value, field_type)
                    new_display = ChangeTracker.format_value(new_value, field_type)
                    changes.append(f"{label}: {old_display} → {new_display}")
        
        return changes
    
    @staticmethod
    def get_change_summary(original_instance, updated_instance) -> str:
        """
        Get a formatted summary of all changes.
        """
        changes = ChangeTracker.track_changes(original_instance, updated_instance)
        
        if changes:
            return f" | Changes: {'; '.join(changes)}"
        else:
            return " | No changes made"
    
    @staticmethod
    def get_change_description(original_instance, updated_instance, location: str) -> str:
        """
        Get a complete description for the audit log.
        """
        summary = ChangeTracker.get_change_summary(original_instance, updated_instance)
        
        return (
            f"Application updated for {updated_instance.Fname} {updated_instance.Lname} "
            f"(ID: {updated_instance.ID_number}) from {location}{summary}"
        )


# =============================================================
# ✅ SHORTCUT FUNCTION
# =============================================================

def get_change_summary(original_instance, updated_instance) -> str:
    """
    Quick function to get change summary.
    """
    return ChangeTracker.get_change_summary(original_instance, updated_instance)