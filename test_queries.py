import logging
from sqlmodel import Session, select, func
from database import get_session, engine
from models import Patient, Order, Result, ResultDetail, Parameter, TestDefinition

def test_queries():
    with Session(engine) as session:
        print("Testing Critical Value Alerts...")
        # Details
        stmt_critical = select(ResultDetail, Order, Patient, Parameter).join(Result, Result.id == ResultDetail.result_id).join(Order, Order.id == Result.order_id).join(Patient, Patient.id == Order.patient_id).join(Parameter, Parameter.id == ResultDetail.parameter_id).where(ResultDetail.flag == "⚠ PANIC").order_by(Result.entered_at.desc()).limit(10)
        critical_data = session.exec(stmt_critical).all()
        for cd, order, pat, param in critical_data:
            print(pat.full_name, param.parameter_name, cd.result.entered_at)
        
        # Main
        stmt_critical_main = select(Result, Order, Patient, TestDefinition).join(Order, Order.id == Result.order_id).join(Patient, Patient.id == Order.patient_id).join(TestDefinition, TestDefinition.id == Order.test_id).where(Result.flag == "⚠ PANIC").order_by(Result.entered_at.desc()).limit(10)
        critical_main_data = session.exec(stmt_critical_main).all()
        for cm, order, pat, test in critical_main_data:
            print(pat.full_name, test.test_name, cm.entered_at)

        print("Testing Demographics...")
        males = session.exec(select(func.count(Patient.id)).where(Patient.gender == "Male")).one()
        females = session.exec(select(func.count(Patient.id)).where(Patient.gender == "Female")).one()
        print("Males:", males, "Females:", females)

        print("Testing Top Requested Tests...")
        top_tests_stmt = select(TestDefinition.test_name, func.count(Order.id).label("count")).join(Order, Order.test_id == TestDefinition.id).group_by(TestDefinition.test_name).order_by(func.count(Order.id).desc()).limit(5)
        top_tests = session.exec(top_tests_stmt).all()
        print(top_tests)

if __name__ == "__main__":
    test_queries()
