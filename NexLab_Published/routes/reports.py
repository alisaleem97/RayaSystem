# routes/reports.py
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from datetime import datetime, timedelta
from typing import Optional

from database import get_session
from models import PatientVisit, Expense, User, Order, TestDefinition, Device
from routes.helpers import templates, require_permission

router = APIRouter()

# ===========================
# DETAILED INCOME REPORT
# ===========================
@router.get("/reports/detailed-income", response_class=HTMLResponse)
def detailed_income_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "detailed_income"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
        
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/detailed-income?error=Invalid date format", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Fetch Visits for the selected date
    visits = session.exec(
        select(PatientVisit)
        .where(PatientVisit.visit_date >= start_date)
        .where(PatientVisit.visit_date <= end_date)
    ).all()
    
    # 2. Fetch Expenses for the selected date
    expenses = session.exec(
        select(Expense)
        .where(Expense.expense_date >= start_date)
        .where(Expense.expense_date <= end_date)
    ).all()

    # Calculate Totals
    total_received = sum((v.received_amount or 0.0) for v in visits)
    total_discount = sum((v.discount_amount or 0.0) for v in visits)
    total_tax = sum((v.tax_amount or 0.0) for v in visits)
    total_remain = sum((v.remaining_amount or 0.0) for v in visits)
    
    total_amount_without_discount = total_received + total_remain + total_discount - total_tax
    
    total_expense = sum((e.amount or 0.0) for e in expenses)

    # Net Formulas
    net_amount_1 = total_amount_without_discount - (total_discount + total_expense + total_remain)
    net_amount_2 = total_amount_without_discount - (total_discount + total_expense + total_remain + total_tax)

    return templates.TemplateResponse("detailed_income.html", {
        "request": request,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_amount_without_discount": round(total_amount_without_discount, 2),
        "total_discount": round(total_discount, 2),
        "total_expense": round(total_expense, 2),
        "total_tax": round(total_tax, 2),
        "total_remain": round(total_remain, 2),
        "total_received": round(total_received, 2),
        "net_amount_1": round(net_amount_1, 2),
        "net_amount_2": round(net_amount_2, 2)
    })

# ===========================
# NET AMOUNTS REPORT
# ===========================
@router.get("/reports/net-amounts", response_class=HTMLResponse)
def net_amounts_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "net_amounts"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
    
    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
        
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/net-amounts?error=Invalid date format", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Fetch Visits
    visits = session.exec(
        select(PatientVisit)
        .where(PatientVisit.visit_date >= start_date)
        .where(PatientVisit.visit_date <= end_date)
    ).all()
    
    # 2. Fetch Expenses
    expenses = session.exec(
        select(Expense)
        .where(Expense.expense_date >= start_date)
        .where(Expense.expense_date <= end_date)
    ).all()

    # Group by date
    from collections import defaultdict
    daily_data = defaultdict(lambda: {
        "received": 0.0, "discount": 0.0, "tax": 0.0, "remain": 0.0, "expense": 0.0
    })

    for v in visits:
        d_str = v.visit_date.strftime("%d-%m-%Y")
        daily_data[d_str]["received"] += (v.received_amount or 0.0)
        daily_data[d_str]["discount"] += (v.discount_amount or 0.0)
        daily_data[d_str]["tax"] += (v.tax_amount or 0.0)
        daily_data[d_str]["remain"] += (v.remaining_amount or 0.0)

    for e in expenses:
        d_str = e.expense_date.strftime("%d-%m-%Y")
        daily_data[d_str]["expense"] += (e.amount or 0.0)

    rows = []
    total_net_with_tax = 0.0
    total_net_without_tax = 0.0

    # Ensure dates are sorted chronologically
    all_dates = sorted(list(daily_data.keys()), key=lambda x: datetime.strptime(x, "%d-%m-%Y"))

    for d_str in all_dates:
        data = daily_data[d_str]
        
        tot_recv = data["received"]
        tot_disc = data["discount"]
        tot_tax = data["tax"]
        tot_rem = data["remain"]
        tot_exp = data["expense"]
        
        tot_amt_without_disc = tot_recv + tot_rem + tot_disc - tot_tax
        
        net_with = tot_amt_without_disc - (tot_disc + tot_exp + tot_rem)
        net_without = tot_amt_without_disc - (tot_disc + tot_exp + tot_rem + tot_tax)
        
        rows.append({
            "date": d_str,
            "net_with_tax": net_with,
            "net_without_tax": net_without
        })
        
        total_net_with_tax += net_with
        total_net_without_tax += net_without

    return templates.TemplateResponse("net_amounts.html", {
        "request": request,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "rows": rows,
        "total_net_with_tax": total_net_with_tax,
        "total_net_with_tax": total_net_with_tax,
        "total_net_without_tax": total_net_without_tax
    })

# ===========================
# PAYMENT RECORDS REPORT
# ===========================
@router.get("/reports/payment-records", response_class=HTMLResponse)
def payment_records_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "payment_records"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
        
    start_date_str = request.query_params.get("start_date")
    start_time_str = request.query_params.get("start_time", "00:00")
    end_date_str = request.query_params.get("end_date")
    end_time_str = request.query_params.get("end_time", "23:59")
    
    record_type = request.query_params.get("record_type", "all")
    user_filter = request.query_params.get("user_id", "all")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_datetime = datetime.strptime(f"{start_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{end_date_str} {end_time_str}", "%Y-%m-%d %H:%M").replace(second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/payment-records?error=Invalid datetime format", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch users for dropdown
    users = session.exec(select(User)).all()
    user_dict = {u.id: u.full_name for u in users}

    records = []

    if record_type in ["all", "receive"]:
        query = select(PatientVisit).where(PatientVisit.visit_date >= start_datetime, PatientVisit.visit_date <= end_datetime)
        if user_filter != "all":
            query = query.where(PatientVisit.created_by == int(user_filter))
        
        visits = session.exec(query).all()
        for v in visits:
            if v.received_amount and v.received_amount > 0:
                user_name = user_dict.get(v.created_by, "Unknown")
                records.append({
                    "datetime": v.visit_date,
                    "date_str": v.visit_date.strftime("%d-%m-%Y %H:%M"),
                    "user": user_name,
                    "patient_name": v.patient.full_name if v.patient else "-",
                    "type": "Receive",
                    "price": v.received_amount,
                    "id": f"visit_{v.id}"
                })

    if record_type in ["all", "expense"]:
        query = select(Expense).where(Expense.expense_date >= start_datetime, Expense.expense_date <= end_datetime)
        if user_filter != "all":
            query = query.where(Expense.created_by == int(user_filter))
            
        expenses = session.exec(query).all()
        for e in expenses:
            if e.amount and e.amount > 0:
                user_name = user_dict.get(e.created_by, "Unknown")
                records.append({
                    "datetime": e.expense_date,
                    "date_str": e.expense_date.strftime("%d-%m-%Y %H:%M"),
                    "user": user_name,
                    "patient_name": "-",
                    "type": "Expense",
                    "price": e.amount,
                    "id": f"expense_{e.id}"
                })

    # Sort descending by datetime
    records.sort(key=lambda x: x["datetime"], reverse=True)

    # Add NO (1, 2, ...)
    for i, r in enumerate(records):
        r["no"] = i + 1

    total_price = sum(r["price"] for r in records)

    return templates.TemplateResponse("payment_records.html", {
        "request": request,
        "start_date": start_date_str,
        "start_time": start_time_str,
        "end_date": end_date_str,
        "end_time": end_time_str,
        "record_type": record_type,
        "user_filter": user_filter,
        "users": users,
        "records": records,
        "total_price": total_price
    })

# ===========================
# PATIENTS NUMBER REPORT
# ===========================
@router.get("/reports/patients-number", response_class=HTMLResponse)
def patients_number_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "patients_number"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
        
    start_date_str = request.query_params.get("start_date")
    start_time_str = request.query_params.get("start_time", "00:00")
    end_date_str = request.query_params.get("end_date")
    end_time_str = request.query_params.get("end_time", "23:59")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_datetime = datetime.strptime(f"{start_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{end_date_str} {end_time_str}", "%Y-%m-%d %H:%M").replace(second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/patients-number?error=Invalid datetime format", status_code=status.HTTP_303_SEE_OTHER)

    query = select(PatientVisit).where(PatientVisit.visit_date >= start_datetime, PatientVisit.visit_date <= end_datetime)
    visits = session.exec(query).all()
    
    # Group by date
    from collections import defaultdict
    daily_data = defaultdict(set)

    for v in visits:
        # Check if the visit has at least one order, and ALL its orders have results that are double_authorized
        if len(v.orders) > 0 and all((o.result and o.result.double_authorized) for o in v.orders):
            d_str = v.visit_date.strftime("%d-%m-%Y")
            daily_data[d_str].add(v.patient_id)

    rows = []
    total_patients = 0
    
    all_dates = sorted(list(daily_data.keys()), key=lambda x: datetime.strptime(x, "%d-%m-%Y"))
    
    for d_str in all_dates:
        p_count = len(daily_data[d_str])
        if p_count > 0:
            rows.append({
                "date": d_str,
                "patient_count": p_count
            })
            total_patients += p_count

    return templates.TemplateResponse("patients_number.html", {
        "request": request,
        "start_date": start_date_str,
        "start_time": start_time_str,
        "end_date": end_date_str,
        "end_time": end_time_str,
        "rows": rows,
        "total_patients": total_patients
    })

# ===========================
# TESTS NUMBER REPORT
# ===========================
@router.get("/reports/tests-number", response_class=HTMLResponse)
def tests_number_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "tests_number"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
        
    start_date_str = request.query_params.get("start_date")
    start_time_str = request.query_params.get("start_time", "00:00")
    end_date_str = request.query_params.get("end_date")
    end_time_str = request.query_params.get("end_time", "23:59")
    
    test_filter = request.query_params.get("test_id", "all")
    device_filter = request.query_params.get("device_id", "all")
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_datetime = datetime.strptime(f"{start_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{end_date_str} {end_time_str}", "%Y-%m-%d %H:%M").replace(second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/tests-number?error=Invalid datetime format", status_code=status.HTTP_303_SEE_OTHER)

    tests_list = session.exec(select(TestDefinition).where(TestDefinition.deleted_at == None)).all()
    devices_list = session.exec(select(Device).where(Device.deleted_at == None)).all()

    query = select(Order).where(Order.order_date >= start_datetime, Order.order_date <= end_datetime)
    
    if test_filter != "all":
        query = query.where(Order.test_id == int(test_filter))
        
    orders = session.exec(query).all()
    
    # Group by date and test name
    from collections import defaultdict
    daily_data = defaultdict(int)

    for o in orders:
        if o.result and o.result.double_authorized:
            if device_filter != "all" and str(o.result.device_id) != device_filter:
                continue
            
            d_str = o.order_date.strftime("%d-%m-%Y")
            test_name = o.test.test_name if o.test else "Unknown"
            daily_data[(d_str, test_name)] += 1

    rows = []
    total_tests = 0
    
    all_keys = sorted(list(daily_data.keys()), key=lambda x: (datetime.strptime(x[0], "%d-%m-%Y"), x[1]))
    
    for k in all_keys:
        d_str, test_name = k
        t_count = daily_data[k]
        if t_count > 0:
            rows.append({
                "date": d_str,
                "test_name": test_name,
                "test_count": t_count
            })
            total_tests += t_count

    return templates.TemplateResponse("tests_number.html", {
        "request": request,
        "start_date": start_date_str,
        "start_time": start_time_str,
        "end_date": end_date_str,
        "end_time": end_time_str,
        "test_filter": test_filter,
        "device_filter": device_filter,
        "tests": tests_list,
        "devices": devices_list,
        "rows": rows,
        "total_tests": total_tests
    })

# ===========================
# DISCOUNT REPORT
# ===========================
@router.get("/reports/discount", response_class=HTMLResponse)
def discount_report_page(request: Request, session: Session = Depends(get_session)):
    if not require_permission(request, session, "discount_report"):
        return RedirectResponse(url="/dashboard?error=Permission Denied", status_code=status.HTTP_303_SEE_OTHER)
        
    start_date_str = request.query_params.get("start_date")
    start_time_str = request.query_params.get("start_time", "00:00")
    end_date_str = request.query_params.get("end_date")
    end_time_str = request.query_params.get("end_time", "23:59")
    
    user_filter = request.query_params.get("user_id", "all")
    patient_id_filter = request.query_params.get("patient_id", "").strip()
    patient_name_filter = request.query_params.get("patient_name", "").strip()
    
    if not start_date_str:
        start_date_str = datetime.now().strftime("%Y-%m-%d")
    if not end_date_str:
        end_date_str = start_date_str
        
    try:
        start_datetime = datetime.strptime(f"{start_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{end_date_str} {end_time_str}", "%Y-%m-%d %H:%M").replace(second=59, microsecond=999999)
    except ValueError:
        return RedirectResponse(url="/reports/discount?error=Invalid datetime format", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch users for dropdown
    users = session.exec(select(User)).all()
    user_dict = {u.id: u.full_name for u in users}

    # Query PatientVisit where discount_amount > 0 and within date range
    from models import Patient
    query = select(PatientVisit).where(
        PatientVisit.discount_amount > 0,
        PatientVisit.visit_date >= start_datetime, 
        PatientVisit.visit_date <= end_datetime
    )
    
    if patient_id_filter or patient_name_filter:
        query = query.join(Patient)
        if patient_id_filter:
            query = query.where(Patient.patient_id.ilike(f"%{patient_id_filter}%"))
        if patient_name_filter:
            query = query.where(Patient.full_name.ilike(f"%{patient_name_filter}%"))
            
    if user_filter != "all":
        # Check if the user either created or edited the visit
        query = query.where((PatientVisit.created_by == int(user_filter)) | (PatientVisit.edited_by == int(user_filter)))

    visits = session.exec(query.order_by(PatientVisit.visit_date.desc())).all()
    
    records = []
    total_discount = 0.0

    for i, v in enumerate(visits, 1):
        # Determine the user responsible for the discount.
        # Use edited_by if available (since discount could be added on edit), otherwise created_by.
        action_user_id = v.edited_by if v.edited_by else v.created_by
        user_name = user_dict.get(action_user_id, "Unknown")
        
        discount_amount = float(v.discount_amount) if v.discount_amount else 0.0
        
        records.append({
            "no": i,
            "datetime": v.visit_date.strftime("%d-%m-%Y %H:%M"),
            "patient_code": v.patient.patient_id if v.patient else "-",
            "patient_name": v.patient.full_name if v.patient else "-",
            "user": user_name,
            "discount_amount": discount_amount,
            "discount_note": v.discount_note or ""
        })
        total_discount += discount_amount

    return templates.TemplateResponse("discount_report.html", {
        "request": request,
        "start_date": start_date_str,
        "start_time": start_time_str,
        "end_date": end_date_str,
        "end_time": end_time_str,
        "user_filter": user_filter,
        "patient_id_filter": patient_id_filter,
        "patient_name_filter": patient_name_filter,
        "users": users,
        "records": records,
        "total_discount": total_discount
    })
