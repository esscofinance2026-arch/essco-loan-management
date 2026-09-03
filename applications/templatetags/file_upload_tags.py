# templatetags/file_upload_tags.py

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag
def file_upload_field(field, label=None, required=False):
    """
    Renders a file upload field with clear button
    """
    label_html = f'<label for="{field.id_for_label}">{label or field.label}</label>' if label or field.label else ''
    
    html = f'''
    <div class="form-group">
        {label_html}
        <div class="file-upload-wrapper">
            {field.as_widget()}
            <button type="button" class="btn-clear-file" onclick="clearFileInput(this)" style="display: none;">
                <i class="fas fa-times"></i> Clear
            </button>
            <span class="file-name">No file chosen</span>
        </div>
        {field.errors}
    </div>
    '''
    return mark_safe(html)