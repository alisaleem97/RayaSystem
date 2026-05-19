# app/services/pdf_service.py
# Native PDF generation for barcode labels using ReportLab.

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

from app.config import STATIC_DIR


def parse_pt(dim_str):
    """Convert CSS dimension to PDF points."""
    if not dim_str:
        return 0
    dim_str = str(dim_str).strip().lower()
    import re
    match = re.match(r'^([\d\.]+)\s*([a-z]*)$', dim_str)
    if not match:
        return 0
    val, unit = float(match.group(1)), match.group(2)
    if unit == 'mm':
        return val * 2.83465
    elif unit == 'cm':
        return val * 28.3465
    elif unit == 'in':
        return val * 72.0
    elif unit == 'px':
        return val * 0.75
    return val


def generate_native_barcode_pdf(patient, tests_by_sample_type, template, visit_id='', visit_date=''):
    """
    Generate a pure vector PDF using ReportLab natively.
    Coordinates are converted from CSS screen pixels (96dpi) to PDF points (72dpi).
    Returns: BytesIO object containing the PDF.
    """
    buffer = io.BytesIO()

    width_pt = parse_pt(template.paper_width) or (2.0 * 72.0)
    height_pt = parse_pt(template.paper_height) or (1.0 * 72.0)
    margin_pt = parse_pt(template.margin) if template.margin else 0

    c = canvas.Canvas(buffer, pagesize=(width_pt, height_pt))

    # Font registry
    font_path = os.path.join(STATIC_DIR, 'vendor', 'fonts', 'Cairo-600.ttf')
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
            font_name = 'ArabicFont'
        except Exception:
            font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'

    elements = json.loads(template.elements) if template.elements else []

    # Arabic reshaper
    try:
        reshaper_config = arabic_reshaper.config_for_true_type_font(font_path) if os.path.exists(font_path) else None
    except Exception:
        reshaper_config = None
    reshaper = arabic_reshaper.ArabicReshaper(configuration=reshaper_config) if reshaper_config else arabic_reshaper.ArabicReshaper()

    PX_TO_PT = 72.0 / 96.0

    sample_types = list(tests_by_sample_type.keys()) or ['Unknown']

    for sample_type in sample_types:
        test_names = tests_by_sample_type.get(sample_type, [])
        tests_str = ", ".join(test_names) if test_names else ''

        for el in elements:
            el_type = el.get('type', '')

            x_pt = el.get('x', 0) * PX_TO_PT + margin_pt
            y_top_pt = el.get('y', 0) * PX_TO_PT + margin_pt
            el_w_pt = el.get('width', 100) * PX_TO_PT
            el_h_pt = el.get('height', 20) * PX_TO_PT
            font_size_pt = el.get('fontSize', 11) * PX_TO_PT
            align = el.get('align', 'left')
            color_hex = el.get('color', '#000000').lstrip('#')

            try:
                r = int(color_hex[0:2], 16) / 255.0
                g = int(color_hex[2:4], 16) / 255.0
                b = int(color_hex[4:6], 16) / 255.0
                c.setFillColorRGB(r, g, b)
            except Exception:
                c.setFillColorRGB(0, 0, 0)

            pdf_y = height_pt - y_top_pt - el_h_pt

            if el_type == 'barcode_image':
                bc_height = el_h_pt * 0.85
                show_text = el.get('showBarcodeText', True)
                bc = code128.Code128(
                    str(patient.patient_id),
                    barHeight=bc_height,
                    barWidth=max(0.5, el.get('barcodeScale', 3) * 0.2),
                    humanReadable=bool(show_text)
                )
                bc_width = bc.width
                if align == 'center':
                    draw_x = x_pt + (el_w_pt - bc_width) / 2
                elif align == 'right':
                    draw_x = x_pt + el_w_pt - bc_width
                else:
                    draw_x = x_pt
                bc.drawOn(c, draw_x, height_pt - y_top_pt - bc_height)
                continue

            txt = ''
            if el_type == 'patient_name':
                txt = str(patient.full_name or '')
            elif el_type == 'patient_id':
                txt = str(patient.patient_id or '')
            elif el_type == 'patient_gender':
                txt = str(patient.gender or '')
            elif el_type == 'patient_age':
                txt = f"{patient.age or 0} {patient.age_unit or 'year'}"
            elif el_type == 'patient_phone':
                txt = f"{patient.phone_key or ''} {patient.phone_number or ''}".strip()
            elif el_type == 'sample_type':
                txt = sample_type
            elif el_type == 'test_list':
                txt = tests_str
            elif el_type == 'test_name':
                txt = test_names[0] if test_names else ''
            elif el_type == 'visit_id':
                txt = str(visit_id or '')
            elif el_type == 'visit_date':
                txt = str(visit_date or '')
            elif el_type == 'lab_name':
                txt = el.get('label', '')
            elif el_type == 'custom_text':
                txt = el.get('customText', el.get('label', ''))
            else:
                txt = el.get('label', '')

            if not txt:
                continue

            try:
                reshaped = reshaper.reshape(txt)
                display_txt = get_display(reshaped)
            except Exception:
                display_txt = txt

            c.setFont(font_name, max(4, font_size_pt))
            text_y = pdf_y + (el_h_pt - font_size_pt) / 2

            if align == 'center':
                c.drawCentredString(x_pt + el_w_pt / 2, text_y, display_txt)
            elif align == 'right':
                c.drawRightString(x_pt + el_w_pt, text_y, display_txt)
            else:
                c.drawString(x_pt, text_y, display_txt)

        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer
