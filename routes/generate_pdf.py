import io
import os
import json
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import code128
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

def parse_pt(dim_str):
    """Convert CSS dimension to Document points"""
    if not dim_str: return 0
    dim_str = str(dim_str).strip().lower()
    import re
    match = re.match(r'^([\d\.]+)\s*([a-z]*)$', dim_str)
    if not match: return 0
    val, unit = float(match.group(1)), match.group(2)
    if unit == 'mm': return val * 2.83465
    elif unit == 'cm': return val * 28.3465
    elif unit == 'in': return val * 72.0
    elif unit == 'px': return val * 0.75
    return val

def generate_native_barcode_pdf(patient, tests_by_sample_type, template):
    """
    Generate a pure vector PDF using ReportLab natively.
    Returns: BytesIO object containing the PDF.
    """
    buffer = io.BytesIO()
    
    # 1. Canvas Dimensions
    width_pt = parse_pt(template.paper_width) or (2.0 * 72.0)
    height_pt = parse_pt(template.paper_height) or (1.0 * 72.0)
    
    c = canvas.Canvas(buffer, pagesize=(width_pt, height_pt))
    
    # 2. Font Registry
    # Use Cairo-600.ttf available in the project for Arabic shaping
    font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'vendor', 'fonts', 'Cairo-600.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
        font_name = 'ArabicFont'
    else:
        font_name = 'Helvetica-Bold'
        
    # 3. Preparation
    if template.elements:
        elements = json.loads(template.elements)
    else:
        elements = []
        
    reshaper_config = arabic_reshaper.config_for_true_type_font(font_path) if os.path.exists(font_path) else None
    if reshaper_config:
        reshaper = arabic_reshaper.ArabicReshaper(configuration=reshaper_config)
    else:
        reshaper = arabic_reshaper.ArabicReshaper()

    # Create one page per sample type
    sample_types = list(tests_by_sample_type.keys())
    if not sample_types:
        sample_types = ['Blood']
        
    for index, sample_type in enumerate(sample_types):
        test_names = tests_by_sample_type.get(sample_type, [])
        tests_str = ", ".join([t for t in test_names]) if test_names else "No tests"
        
        for el in elements:
            # HTML Coordinates (X: 0->Right, Y: 0->Down) to PDF Coordinates (X: 0->Right, Y: 0->Up)
            # The HTML coordinate maps to the TOP-LEFT of the `div`.
            # Reportlab coordinates map to the BOTTOM-LEFT baseline of the text.
            x = el.get('x', 0) * 0.75 # px to pt
            y = el.get('y', 0) * 0.75 # px to pt
            el_h = el.get('height', 20) * 0.75
            
            # PDF Y is (canvas height - top y position - element height factor)
            # We add a slight baseline bump for natural text
            pdf_y = height_pt - y - el_h + 4 
            
            el_type = el.get('type')
            
            if el_type == 'barcode_image':
                # Draw native Code128 Barcode vector!
                # Provide a fixed barcode height of roughly 75% of element box
                b_height = el_h * 0.8
                barcode = code128.Code128(patient.patient_id, barHeight=b_height, barWidth=1.1)
                barcode.drawOn(c, x, height_pt - y - b_height)
                continue
                
            # Determine Text content
            txt = ""
            if el_type == 'patient_name': txt = patient.full_name
            elif el_type == 'patient_id': txt = patient.patient_id
            elif el_type == 'patient_gender': txt = str(patient.gender or '')
            elif el_type == 'patient_age': txt = f"{patient.age or 0} {patient.age_unit or 'year'}"
            elif el_type == 'sample_type': txt = sample_type
            elif el_type == 'test_list': txt = tests_str
            elif getattr(el, 'label', ''): txt = el.label
                
            if not txt: continue
                
            # Arabic shaping
            res_txt = reshaper.reshape(str(txt))
            bidi_txt = get_display(res_txt)
            
            # Draw Text
            font_size = el.get('fontSize', 11) * 0.75
            c.setFont(font_name, font_size)
            
            # If the design is heavily RTL forced right, we could use right anchoring,
            # but standard UI X coordinates represent the left bound.
            c.drawString(x, pdf_y, bidi_txt)
            
        c.showPage() # End page for this sample type

    c.save()
    buffer.seek(0)
    return buffer
