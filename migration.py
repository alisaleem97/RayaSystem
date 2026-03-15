# migration.py
# Run ONCE to add new columns for price snapshot audit compliance

from sqlmodel import SQLModel, create_engine, Session, select
from models import Order, LabInfo

# Database connection
engine = create_engine("sqlite:///./database.db")

print("🔍 Starting database migration...")

with Session(engine) as session:
    from sqlalchemy import text
    
    # ===========================
    # ADD COLUMNS TO ORDER TABLE
    # ===========================
    print("📝 Adding columns to 'order' table...")
    
    try:
        session.exec(text("ALTER TABLE [order] ADD COLUMN unit_price FLOAT DEFAULT 0.0"))
        print("✅ Added unit_price column")
    except Exception as e:
        print(f"⚠️ unit_price column may already exist: {e}")
    
    try:
        session.exec(text("ALTER TABLE [order] ADD COLUMN discount_amount FLOAT DEFAULT 0.0"))
        print("✅ Added discount_amount column")
    except Exception as e:
        print(f"⚠️ discount_amount column may already exist: {e}")
    
    try:
        session.exec(text("ALTER TABLE [order] ADD COLUMN final_price FLOAT DEFAULT 0.0"))
        print("✅ Added final_price column")
    except Exception as e:
        print(f"⚠️ final_price column may already exist: {e}")
    
    # ===========================
    # ADD COLUMN TO LABINFO TABLE
    # ===========================
    print("📝 Adding column to 'labinfo' table...")
    
    try:
        session.exec(text("ALTER TABLE labinfo ADD COLUMN lab_currency TEXT DEFAULT '$'"))
        print("✅ Added lab_currency column")
    except Exception as e:
        print(f"⚠️ lab_currency column may already exist: {e}")
    
    session.commit()
    
    # ===========================
    # BACKFILL EXISTING ORDERS
    # ===========================
    print("📝 Backfilling existing orders with current test prices...")
    
    orders = session.exec(select(Order)).all()
    updated_count = 0
    
    for order in orders:
        test = session.get(LabInfo, 1)  # Get test definition
        from models import TestDefinition
        test = session.get(TestDefinition, order.test_id)
        if test:
            order.unit_price = test.price
            order.final_price = test.price
            updated_count += 1
    
    session.commit()
    print(f"✅ Backfilled {updated_count} existing orders")
    
    print("\n✅✅✅ DATABASE MIGRATION COMPLETED SUCCESSFULLY! ✅✅✅\n")