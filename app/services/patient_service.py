# app/services/patient_service.py
# Patient-related business logic: query builders, data helpers.

from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.models import Patient, PatientVisit, Order, TestDefinition


def calculate_age(dob: datetime) -> int:
    """Calculate age from date of birth."""
    if dob is None:
        return 0
    today = datetime.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def age_to_days(age, unit: str) -> int:
    """Convert age and unit to days for consistent comparison."""
    if age is None or age == "":
        return 0
    age = int(age)
    u = (unit or "year").lower()
    if "year" in u:
        return age * 365
    elif "month" in u:
        return age * 30
    elif "day" in u:
        return age
    return age * 365


def model_to_dict(model):
    """Convert SQLModel object to dict."""
    if model is None:
        return None
    data = {}
    for column in model.__table__.columns.keys():
        value = getattr(model, column)
        if isinstance(value, datetime):
            data[column] = value.isoformat()
        else:
            data[column] = value
    return data


def build_patient_visit_data(session, request, status_filter=None, defaults_today=True):
    """
    Shared helper to build patient_data list for patient list pages.
    Eliminates N+1 queries by fetching visits directly with eager-loaded orders.
    Supports pagination via ?page= query param.

    Returns: (patient_data, filters, page, total_pages, total_count)
    """
    PAGE_SIZE = 50

    today_str = datetime.today().strftime("%Y-%m-%d") if defaults_today else ""
    start_date = request.query_params.get("start_date", today_str)
    end_date = request.query_params.get("end_date", today_str)
    name = request.query_params.get("name", "")
    patient_id_q = request.query_params.get("patient_id", "")
    test_q = request.query_params.get("test", "")
    status_q = status_filter or request.query_params.get("status", "all")

    # Pagination
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    # Single query: fetch visits with eager-loaded patient and orders
    visit_query = (
        select(PatientVisit)
        .options(
            selectinload(PatientVisit.patient),
            selectinload(PatientVisit.orders).selectinload(Order.test)
        )
        .join(Patient, PatientVisit.patient_id == Patient.id)
        .where(Patient.is_active == True)
    )

    if start_date:
        visit_query = visit_query.where(PatientVisit.visit_date >= datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S"))
    if end_date:
        visit_query = visit_query.where(PatientVisit.visit_date <= datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S"))
    if name:
        visit_query = visit_query.where(Patient.full_name.ilike(f"%{name}%"))
    if patient_id_q:
        visit_query = visit_query.where(Patient.patient_id.ilike(f"%{patient_id_q}%"))

    if test_q:
        visit_query = visit_query.join(Order, Order.visit_id == PatientVisit.id).join(
            TestDefinition, Order.test_id == TestDefinition.id
        ).where(
            (TestDefinition.test_name.ilike(f"%{test_q}%")) |
            (TestDefinition.test_short_name.ilike(f"%{test_q}%"))
        )

    if status_q != "all":
        if not test_q:
            visit_query = visit_query.join(Order, Order.visit_id == PatientVisit.id)
        if status_q == "pending":
            visit_query = visit_query.where(Order.status == "ordered")
        elif status_q in ("received", "resulted"):
            visit_query = visit_query.where(Order.status == "resulted")
        elif status_q in ("authorize", "authorized"):
            visit_query = visit_query.where(Order.status == "authorized")
        elif status_q == "double_authorized":
            visit_query = visit_query.where(Order.status == "double_authorized")
        elif status_q == "AD":
            visit_query = visit_query.where(Order.status.in_(["authorized", "double_authorized"]))

    visits = session.exec(
        visit_query.distinct().order_by(PatientVisit.visit_date.desc())
    ).all()

    # Build one row per visit (no deduplication — each visit is shown separately)
    all_patient_data = []

    for visit in visits:
        patient = visit.patient
        if not patient:
            continue

        # Build tests data from orders
        packages = {}
        standalones = []

        for order in visit.orders:
            if not order.test or order.status == "no_sample":
                continue

            status_color = "red"
            if order.status == "resulted":
                status_color = "blue"
            elif order.status == "authorized":
                status_color = "green"
            elif order.status == "double_authorized":
                status_color = "purple"

            test_info = {"name": order.test.test_name, "color": status_color}

            if order.package_name:
                if order.package_name not in packages:
                    packages[order.package_name] = []
                packages[order.package_name].append(test_info)
            else:
                standalones.append(test_info)

        tests_data = []
        for pkg_name, pkg_tests in packages.items():
            tests_data.append({"is_package": True, "package_name": pkg_name, "tests": pkg_tests})
        for t in standalones:
            tests_data.append({"is_package": False, "test": t})

        all_patient_data.append({
            "patient": patient,
            "visit": visit,
            "registration_date": visit.visit_date,
            "tests": tests_data
        })

    # Pagination
    total_count = len(all_patient_data)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    patient_data = all_patient_data[offset:offset + PAGE_SIZE]

    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "name": name,
        "patient_id": patient_id_q,
        "test": test_q,
        "status": status_q,
    }

    return patient_data, filters, page, total_pages, total_count
