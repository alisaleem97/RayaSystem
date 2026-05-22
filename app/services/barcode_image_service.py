# app/services/barcode_image_service.py
# Generates barcode label as a high-DPI PNG image (Pillow + python-barcode).
# Same approach as NaseemPrint (ZXing + System.Drawing) —
# renders directly as a bitmap at thermal printer DPI.

import io
import json
import os
import re
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter

import arabic_reshaper
from bidi.algorithm import get_display
from app.config import STATIC_DIR


PRINTER_DPI = 203  # Standard thermal label printer DPI


def parse_css_to_inches(dim_str):
    """Convert CSS dimension string to inches."""
    if not dim_str:
        return 0
    dim_str = str(dim_str).strip().lower()
    match = re.match(r'^([\d\.]+)\s*([a-z]*)$', dim_str)
    if not match:
        return 0
    val, unit = float(match.group(1)), match.group(2)
    if unit == 'mm':
        return val / 25.4
    elif unit == 'cm':
        return val / 2.54
    elif unit == 'in':
        return val
    elif unit == 'px':
        return val / 96.0
    return val / 96.0  # assume px


def generate_barcode_label_image(patient, tests_by_sample_type, template, visit_id='', visit_date='', dpi=PRINTER_DPI):
    """
    Generate barcode label as a high-DPI PNG image.
    Returns: list of BytesIO objects (one PNG per sample type/page).
    """
    # Label dimensions in pixels at target DPI
    width_in = parse_css_to_inches(template.paper_width) or 4.0
    height_in = parse_css_to_inches(template.paper_height) or 2.0
    img_w = int(width_in * dpi)
    img_h = int(height_in * dpi)

    # Scale factor: template coordinates are in CSS pixels (96 DPI)
    scale = dpi / 96.0

    elements = json.loads(template.elements) if template.elements else []

    # Load font
    font_path = os.path.join(STATIC_DIR, 'vendor', 'fonts', 'Cairo-600.ttf')
    if not os.path.exists(font_path):
        font_path = None

    # Arabic reshaper
    try:
        reshaper_config = arabic_reshaper.config_for_true_type_font(font_path) if font_path else None
    except Exception:
        reshaper_config = None
    reshaper = arabic_reshaper.ArabicReshaper(configuration=reshaper_config) if reshaper_config else arabic_reshaper.ArabicReshaper()

    sample_types = list(tests_by_sample_type.keys()) or ['Unknown']
    pages = []

    for sample_type in sample_types:
        test_names = tests_by_sample_type.get(sample_type, [])
        tests_str = ", ".join(test_names) if test_names else ''

        # Create blank white label
        img = Image.new('1', (img_w, img_h), 1)  # mode='1' = 1-bit B&W, 1=white
        draw = ImageDraw.Draw(img)

        for el in elements:
            el_type = el.get('type', '')
            x = int(el.get('x', 0) * scale)
            y = int(el.get('y', 0) * scale)
            w = int(el.get('width', 100) * scale)
            h = int(el.get('height', 20) * scale)
            font_size = max(6, int(el.get('fontSize', 11) * scale))

            if el_type == 'barcode_image':
                # Generate Code128 barcode — bars only, text drawn separately for full control
                try:
                    show_text = el.get('showBarcodeText', True)
                    code128 = barcode.get('code128', str(patient.patient_id), writer=ImageWriter())
                    bc_buffer = io.BytesIO()
                    code128.write(bc_buffer, options={
                        'module_width': 0.5,  # thick bars
                        'module_height': 20,  # tall bars in mm
                        'write_text': False,
                        'quiet_zone': 1,
                        'dpi': dpi,
                    })
                    bc_buffer.seek(0)
                    bc_img = Image.open(bc_buffer).convert('1')

                    # Crop white padding so bars fill the element properly
                    crop_box = bc_img.getbbox()
                    if crop_box:
                        bc_img = bc_img.crop(crop_box)

                    # Scale to fill element box
                    bc_ratio = min(w / bc_img.width, h / bc_img.height)
                    new_w = int(bc_img.width * bc_ratio)
                    new_h = int(bc_img.height * bc_ratio)
                    bc_img = bc_img.resize((new_w, new_h), Image.NEAREST)

                    # Paste bars centered in element box
                    paste_x = x + (w - new_w) // 2
                    paste_y = y
                    img.paste(bc_img, (paste_x, paste_y))

                    # Draw patient ID text BELOW the element box
                    if show_text:
                        try:
                            id_font = ImageFont.truetype(font_path, max(8, int(7 * scale))) if font_path else ImageFont.load_default()
                        except Exception:
                            id_font = ImageFont.load_default()
                        id_text = str(patient.patient_id)
                        bbox = draw.textbbox((0, 0), id_text, font=id_font)
                        tw = bbox[2] - bbox[0]
                        text_x = x + (w - tw) // 2  # centered under bars
                        text_y = y + h + 0.5  # minimal gap below bars
                        draw.text((text_x, text_y), id_text, fill=0, font=id_font)
                except Exception as e:
                    # Fallback: draw placeholder
                    draw.rectangle([x, y, x + w, y + h], outline=0)
                    draw.text((x + 5, y + 5), f"BC:{patient.patient_id}", fill=0)
                continue

            # Text elements
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

            # Arabic text reshaping
            try:
                reshaped = reshaper.reshape(txt)
                display_txt = get_display(reshaped)
            except Exception:
                display_txt = txt

            # Load font at the correct size
            try:
                pil_font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except Exception:
                pil_font = ImageFont.load_default()

            # Calculate text position based on alignment
            align = el.get('align', 'left')
            bbox = draw.textbbox((0, 0), display_txt, font=pil_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_y = y + (h - text_h) // 2

            if align == 'center':
                text_x = x + (w - text_w) // 2
            elif align == 'right':
                text_x = x + w - text_w
            else:
                text_x = x + 5  # small padding

            draw.text((text_x, text_y), display_txt, fill=0, font=pil_font)

        # Convert to PNG bytes
        buf = io.BytesIO()
        img.save(buf, format='PNG', dpi=(dpi, dpi))
        buf.seek(0)
        pages.append(buf)

    return pages
