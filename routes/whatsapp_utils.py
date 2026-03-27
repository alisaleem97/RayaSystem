# routes/whatsapp_utils.py
import io
import json
import base64
import requests
from xhtml2pdf import pisa
from fastapi.templating import Jinja2Templates
from datetime import datetime
import os
import traceback
import arabic_reshaper
from bidi.algorithm import get_display

templates = Jinja2Templates(directory="templates")

def reshape_text(text):
    if not text: return ""
    # Reshape Arabic characters
    reshaped_text = arabic_reshaper.reshape(str(text))
    # Handle Right-to-Left display
    bidi_text = get_display(reshaped_text)
    return bidi_text

def generate_report_pdf(patient, visit, results, lab_info, template_elements):
    """Generates a basic PDF using xhtml2pdf for maximum stability and recovery"""
    
    # Load Cairo font to base64 for embedding (Common Arabic font)
    font_path = os.path.abspath("uploads/Cairo.ttf")
    font_base64 = ""
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            font_base64 = base64.b64encode(f.read()).decode('utf-8')

    # Simple HTML structure for stability
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @font-face {{
                font-family: 'CairoFont';
                src: url(data:font/truetype;charset=utf-8;base64,{font_base64});
            }}
            body {{
                font-family: 'CairoFont', Arial, sans-serif;
                margin: 20px;
                color: #333;
                direction: rtl; /* For Arabic support */
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #000;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .lab-name {{
                font-size: 24px;
                font-weight: bold;
            }}
            .patient-info {{
                width: 100%;
                margin-bottom: 20px;
            }}
            .patient-info td {{
                padding: 5px;
            }}
            .results-table {{
                width: 100%;
                border-collapse: collapse;
            }}
            .results-table th, .results-table td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: center;
            }}
            .results-table th {{
                background-color: #f2f2f2;
            }}
            .parent-row {{
                background-color: #f9f9f9;
                font-weight: bold;
                text-align: right !important;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="lab-name">{reshape_text(lab_info.get('lab_name', 'NexLab'))}</div>
            <div>{reshape_text(lab_info.get('lab_title', 'Laboratory Report'))}</div>
        </div>
        
        <table class="patient-info">
            <tr>
                <td><strong>Name:</strong> {reshape_text(patient.get('full_name', ''))}</td>
                <td><strong>Patient ID:</strong> {patient.get('patient_id', '')}</td>
            </tr>
            <tr>
                <td><strong>Age:</strong> {patient.get('age', '')} {patient.get('age_unit', 'Y')}</td>
                <td><strong>Gender:</strong> {reshape_text(patient.get('gender', ''))}</td>
            </tr>
            <tr>
                <td><strong>Date:</strong> {visit.get('visit_date', '').split('T')[0] if visit.get('visit_date') else ''}</td>
                <td><strong>Visit ID:</strong> {visit.get('visit_id', '')}</td>
            </tr>
        </table>
        
        <table class="results-table">
            <thead>
                <tr>
                    <th>Test</th>
                    <th>Result</th>
                    <th>Unit</th>
                    <th>Ref. Range</th>
                </tr>
            </thead>
            <tbody>
    """

    for row in results:
        if row.get('type') == 'parent':
            html += f"""
                <tr class="parent-row">
                    <td colspan="4">{reshape_text(row.get('test_name', ''))}</td>
                </tr>
            """
        else:
            style ="color:red; font-weight:bold;" if row.get('flag') and row.get('flag') != 'N' else ""
            html += f"""
                <tr>
                    <td>{reshape_text(row.get('parameter_name') or row.get('test_name', ''))}</td>
                    <td><span style="{style}">{reshape_text(row.get('result_value', ''))}</span></td>
                    <td>{reshape_text(row.get('unit', ''))}</td>
                    <td>{reshape_text(row.get('range', ''))}</td>
                </tr>
            """

    html += """
            </tbody>
        </table>
    </body>
    </html>
    """

    try:
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer, encoding='utf-8')
        
        if pisa_status.err:
            raise Exception("PDF generation failed")
            
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()
        
        # Save a copy for debugging
        try:
            with open("tmp/last_whatsapp_report.pdf", "wb") as f:
                f.write(pdf_bytes)
        except: pass
            
        return pdf_bytes
    except Exception as e:
        print(f"PDF ERROR: {str(e)}")
        traceback.print_exc()
        raise e

def send_ultramsg_pdf(to_phone, pdf_bytes, filename, instance_id, token):
    url = f"https://api.ultramsg.com/{instance_id}/messages/document"
    base64_data = base64.b64encode(pdf_bytes).decode('utf-8')
    # to_phone must be in international format with '+'
    payload = {
        "token": token,
        "to": to_phone,
        "filename": filename,
        "document": base64_data
    }
    headers = {"content-type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    try:
        return response.json()
    except:
        return {"success": False, "message": f"API Error ({response.status_code})"}
