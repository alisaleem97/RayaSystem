# routes/call_centre.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import json
import traceback
from datetime import datetime

from database import get_session
from models import Patient, PatientVisit, Order, Result, TestRange, LabInfo, PrintTemplate
# ✅ NEW: Imported log_audit_action
from routes.helpers import get_current_user, log_audit_action
from routes.whatsapp_utils import generate_report_pdf, send_ultramsg_pdf

# --- Google Gemini AI Setup ---
import google.generativeai as genai
genai.configure(api_key="AIzaSyBjeyiRZzUqyVHLa7CsWrg861E5pyP0t4U")

class AIRequest(BaseModel):
    prompt: str

router = APIRouter(tags=["Call Centre"])

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

@router.get("/call-centre", response_class=HTMLResponse)
def call_centre_list(
    request: Request, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    name: Optional[str] = None,
    patient_id: Optional[str] = None,
    test: Optional[str] = None,
    status_filter: Optional[str] = "All", # Added toggle filter
    session: Session = Depends(get_session)
):
    # 1. Default dates to TODAY if not provided
    today_str = datetime.now().strftime('%Y-%m-%d')
    if not start_date:
        start_date = today_str
    if not end_date:
        end_date = today_str

    # Ensure Order.result is loaded to check authorization levels
    query = select(PatientVisit).options(
        selectinload(PatientVisit.patient), 
        selectinload(PatientVisit.orders).selectinload(Order.test),
        selectinload(PatientVisit.orders).selectinload(Order.result)
    )
    
    # Date Filtering (Appending 23:59:59 ensures the entire end_date is included)
    query = query.where(PatientVisit.visit_date >= start_date)
    query = query.where(PatientVisit.visit_date <= f"{end_date} 23:59:59")
    
    if patient_id:
        query = query.where(PatientVisit.visit_id.like(f"%{patient_id}%"))
    if name:
        query = query.join(Patient).where(Patient.full_name.like(f"%{name}%"))
        
    visits = session.exec(query.order_by(PatientVisit.visit_date.desc())).all()
    
    patient_data = []
    for v in visits:
        test_list = [o.test.test_name for o in v.orders if o.test]
        if test and test.lower() not in " ".join(test_list).lower():
            continue
            
        total_tests = len(v.orders)
        
        # 2. Strict Status Logic
        has_pending = False
        all_double_auth = True
        
        if total_tests == 0:
            has_pending = True
            all_double_auth = False
        else:
            for o in v.orders:
                res = o.result
                if not res or not res.authorized:
                    has_pending = True
                    all_double_auth = False
                    break
                else:
                    # Safely check for double auth status (handles different possible column names)
                    is_da = getattr(res, 'double_authorized', getattr(res, 'is_double_authorized', False))
                    if not is_da:
                        all_double_auth = False
        
        if has_pending:
            status_text = "Pending"
            status_color = "amber"
        elif all_double_auth:
            status_text = "Double Auth"
            status_color = "emerald"
        else:
            status_text = "Authorize" # Authorized, but not double authorized yet
            status_color = "blue"

        # 3. Apply Toggle Filters
        if status_filter == "Pending":
            # Show if ANY test is pending OR it's only single 'Authorize' (Not Double Auth)
            if status_text == "Double Auth":
                continue
        elif status_filter == "Not Done":
            # Show ONLY if all are Double Auth, but the patient hasn't been called yet
            if status_text != "Double Auth" or v.is_called:
                continue
        elif status_filter == "Call done":
            # Show ONLY if the call is completed
            if not v.is_called:
                continue

        patient_data.append({
            "registration_date": v.visit_date,
            "patient": v.patient,
            "visit": v,
            "tests_names": ", ".join(test_list[:3]) + ("..." if len(test_list) > 3 else ""),
            "status": status_text,
            "status_color": status_color,
            "is_called": v.is_called
        })
    
    return templates.TemplateResponse("call_centre.html", {
        "request": request,
        "patient_data": patient_data,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "name": name or "",
            "patient_id": patient_id or "",
            "test": test or "",
            "status_filter": status_filter
        }
    })

@router.get("/view-call-centre/{visit_id}", response_class=HTMLResponse)
def view_call_centre_patient(visit_id: str, request: Request, session: Session = Depends(get_session)):
    visit = session.exec(
        select(PatientVisit)
        .options(
            selectinload(PatientVisit.patient),
            selectinload(PatientVisit.orders).selectinload(Order.test),
            selectinload(PatientVisit.orders).selectinload(Order.result).selectinload(Result.details)
        )
        .where(PatientVisit.visit_id == visit_id)
    ).first()
    
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
        
    patient = visit.patient
    visit_user_name = "System"
    if visit and visit.created_by:
        from models import User
        user = session.get(User, visit.created_by)
        if user:
            visit_user_name = user.full_name or user.username
            
    return templates.TemplateResponse("call_centre_view.html", {
        "request": request,
        "patient": patient,
        "visit": visit,
        "visit_user_name": visit_user_name
    })

# ✅ NEW: Added request dependency to track WHO marked the patient as called
@router.post("/api/mark-called/{visit_id}")
def mark_called(visit_id: str, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    visit = session.exec(select(PatientVisit).where(PatientVisit.visit_id == visit_id)).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    
    visit.is_called = True
    session.add(visit)

    # ---------------------------------------------------------
    # ✅ NEW: INJECT AUDIT LOG HERE (Tracking Call Centre mark)
    # ---------------------------------------------------------
    log_audit_action(
        session=session,
        table_name="patientvisit",
        record_id=visit.id,
        action="UPDATE",
        current_user=current_user,
        new_values={"action": "Patient marked as Called"}
    )
    # ---------------------------------------------------------

    session.commit()
    return {"success": True}

# ✅ NEW: Added request dependency to track WHO sent the WhatsApp message
@router.post("/api/send-whatsapp/{visit_id}")
def send_whatsapp_results(visit_id: str, request: Request, session: Session = Depends(get_session)):
    current_user = get_current_user(request, session)
    visit = session.exec(select(PatientVisit).where(PatientVisit.visit_id == visit_id)).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    
    patient = session.get(Patient, visit.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    orders = session.exec(
        select(Order).options(selectinload(Order.test), selectinload(Order.result).selectinload(Result.details))
        .where(Order.visit_id == visit.id, Order.status != "no_sample")
    ).all()
    
    structured_results = []
    for order in orders:
        test = order.test
        res = order.result
        if not test: continue
        
        if test.test_parameters:
            structured_results.append({"type": "parent", "test_name": test.test_name})
            for tp in test.test_parameters:
                p = tp.parameter
                d = next((dt for dt in res.details if dt.parameter_id == p.id), None) if res else None
                structured_results.append({
                    "type": "child", "parameter_name": p.parameter_name, "result_value": d.result_value if d else "-",
                    "unit": "", "range": "", "flag": d.flag if d else ""
                })
        else:
            structured_results.append({
                "type": "standalone", "test_name": test.test_name, "result_value": res.result_value if res else "-",
                "unit": "", "range": "", "flag": res.flag if res else ""
            })

    lab_info = session.exec(select(LabInfo).limit(1)).first() or LabInfo(lab_name="NexLab")
    template_obj = session.exec(select(PrintTemplate).where(PrintTemplate.template_name == "result_report")).first()
    
    template_data = {
        "elements": [],
        "paperSize": "A4"
    }
    if template_obj:
        try:
            elements = template_obj.elements
            if isinstance(elements, str):
                elements = json.loads(elements)
            if isinstance(elements, dict):
                template_data = elements
            else:
                template_data["elements"] = elements
        except:
            pass

    from routes.helpers import generate_barcode_base64
    barcode_data = generate_barcode_base64(patient.patient_id)
    if "base64," in barcode_data:
        barcode_data = barcode_data.split("base64,")[1]

    try:
        pdf_bytes = generate_report_pdf(
            jsonable_encoder(patient), 
            jsonable_encoder(visit), 
            structured_results, 
            jsonable_encoder(lab_info), 
            template_data,
            barcode_data
        )
        
        to_phone = patient.phone_number
        if not to_phone:
            raise HTTPException(status_code=400, detail="Patient phone number not found")
        
        to_phone = to_phone.strip().replace(" ", "")
        if not to_phone.startswith('+'):
            to_phone = "+" + (to_phone if to_phone.startswith('964') else '964' + to_phone.lstrip('0'))

        safe_name = "".join(c for c in patient.full_name if c.isalnum() or c in (' ', '_', '-')).strip()
        filename = f"{safe_name}.pdf"
        caption = f"{patient.full_name}"
        
        # Using dynamic lab_info credentials!
        report = send_ultramsg_pdf(to_phone, pdf_bytes, filename, caption, jsonable_encoder(lab_info))
        
        if report.get('sent') == 'true' or report.get('id') or report.get('success'):
            visit.is_whatsapp_sent = True
            session.add(visit)

            # ---------------------------------------------------------
            # ✅ NEW: INJECT AUDIT LOG HERE (Tracking WhatsApp Dispatch)
            # ---------------------------------------------------------
            log_audit_action(
                session=session,
                table_name="patientvisit",
                record_id=visit.id,
                action="DISPATCH",
                current_user=current_user,
                new_values={"action": "Results sent to patient via WhatsApp", "phone": to_phone}
            )
            # ---------------------------------------------------------

            session.commit()
            return {"success": True, "message": "Result sent successfully"}
        else:
            return {"success": False, "error": report.get('message', 'WhatsApp API Error')}
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ==========================================
# 🤖 FREE AI ANALYSIS ROUTE
# ==========================================
@router.post("/api/ai-analyse")
async def ai_analyse_results(req: AIRequest):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(req.prompt)
        return {"success": True, "analysis": response.text}
    except Exception as e:
        print(f"AI Error: {e}")
        return {"success": False, "error": str(e)}