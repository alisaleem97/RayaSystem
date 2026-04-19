import os
import base64
import requests
import traceback
from fastapi.templating import Jinja2Templates
from playwright.sync_api import sync_playwright

# Setup Jinja2 to point to your templates folder
templates = Jinja2Templates(directory="templates")

def send_wati_pdf(phone_number, pdf_bytes, filename, caption, lab_info_dict):
    """Sends the generated PDF via Wati API using dynamic database credentials."""
    try:
        # Dynamically fetch from the LabInfo dictionary
        wati_endpoint = lab_info_dict.get("whatsapp_api", "") if lab_info_dict else ""
        token = lab_info_dict.get("whatsapp_token", "") if lab_info_dict else ""
        
        # Clean token just in case user pasted 'Bearer ' with it
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
            
        # If no credentials exist in the database, abort and return a clear error
        if not wati_endpoint or not token:
            print("⚠️ Wati credentials missing from LabInfo database.")
            return {"status": "error", "message": "WhatsApp API credentials are not configured in settings."}

        # Ensure the endpoint does not end with a slash and has https://
        wati_endpoint = wati_endpoint.strip()
        if wati_endpoint and not wati_endpoint.startswith("http"):
            wati_endpoint = f"https://{wati_endpoint}"
            
        # If the user included /api/v1 in the URL, strip it to prevent duplication
        if "/api/v1" in wati_endpoint:
            wati_endpoint = wati_endpoint.split("/api/v1")[0]
            
        base_url = wati_endpoint.rstrip("/")
        
        # Wati API expects the phone number without the '+' sign
        clean_phone = phone_number.replace("+", "")

        url = f"{base_url}/api/v1/sendSessionFile/{clean_phone}"
        
        headers = {
            "Authorization": f"Bearer {token}"
            # Requests will set Content-Type correctly for multipart/form-data
        }
        
        files = {
            'file': (filename, pdf_bytes, 'application/pdf')
        }
        
        # Wati generally expects caption as a query parameter for sendSessionFile
        params = {
            "caption": caption
        }

        response = requests.post(url, headers=headers, params=params, files=files)
        
        print("WATI API RESPONSE CODE:", response.status_code)
        print("WATI API RESPONSE TEXT:", response.text)
        
        res_json = {}
        try:
            res_json = response.json()
        except Exception:
            res_json = {"status": "success" if response.status_code in [200, 201] else "error", "message": response.text}
            
        if response.status_code not in [200, 201] or str(res_json.get("result", "")).lower() == "error" or res_json.get("error"):
            res_json["status"] = "error"
            
        return res_json
    except Exception as e:
        print(f"WhatsApp sending failed: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

def generate_report_pdf(patient, visit, results, lab_info, template_data, barcode_data=None):
    """
    Optimized Playwright PDF generator for maximum speed.
    """
    print("🚀🚀🚀 PLAYWRIGHT ENGINE IS STARTING (OPTIMIZED)! 🚀🚀🚀")
    try:
        # Fetch formatted results quickly
        try:
            patient_id = patient.get("patient_id")
            api_url = f"http://127.0.0.1:8000/api/double-authorized-tests/{patient_id}"
            
            api_resp = requests.get(api_url, timeout=3)
            if api_resp.status_code == 200:
                api_data = api_resp.json()
                if api_data.get("success"):
                    results = api_data.get("results", [])
        except Exception as api_err:
            print(f"⚠️ Local API fetch failed: {api_err}")

        # Render Template
        template = templates.get_template("print_report.html")
        html_content = template.render({
            "patient": patient,
            "visit": visit,
            "lab_info": lab_info,
            "template": template_data,
            "barcode_data": barcode_data,
            "results": results 
        })
        
        paper_size = template_data.get('paperSize', 'A4').upper()
        os.makedirs("tmp", exist_ok=True)
        html_content = html_content.replace("<head>", "<head><base href='http://127.0.0.1:8000/'>")
        
        # Fire up Headless Chrome with Speed Optimizations
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-sandbox',
                    '--single-process'
                ]
            )
            page = browser.new_page()
            
            page.set_content(html_content, wait_until="load")
            page.evaluate("document.fonts.ready")
            
            pdf_bytes = page.pdf(
                format=paper_size,
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}
            )
            browser.close()
            
        with open("tmp/last_whatsapp_report.pdf", "wb") as f: 
            f.write(pdf_bytes)
            
        return pdf_bytes
        
    except Exception as e:
        traceback.print_exc()
        raise e