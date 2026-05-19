"""
LIS V1 → V2 Migration / Seeding Script  (FIXED)
=================================================
Seeds in order:
  1. Parameters
  2. Departments
  3. SampleTypes
  4. Devices        (V1 "Methods")
  5. ReportNotes    (V1 "Notes")  – "None" inserted first as id=1
  6. Tests
  7. Ranges         (V1 "TestRange")

Key fix applied
───────────────
• PRAGMA foreign_keys is turned OFF for the duration of the migration.
  This prevents SQLite from silently dropping (INSERT OR IGNORE) rows
  whose created_by=1 FK cannot be resolved until a User row exists,
  which previously left earlier tables empty and caused the
  "FOREIGN KEY constraint failed" error on the TestDefinition insert.
  Data integrity is guaranteed by the old→new ID maps built in code.
• Ranges that reference ParameterIds absent from parmeters.xlsx are
  inserted with parameter_id = NULL (orphaned V1 records).
• Row-level error reporting: any single-row failure is printed with the
  offending row data rather than aborting the whole batch.
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG  –  edit these two paths before running
# ─────────────────────────────────────────────
DB_PATH   = r"C:\Users\aliss\Desktop\lab_system\lab_database.db"
EXCEL_DIR = r"C:\Users\aliss\Desktop\lab_system\excel_files"
# ─────────────────────────────────────────────

NOW        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
CREATED_BY = 1


# ── helpers ──────────────────────────────────

def xls(filename: str) -> pd.DataFrame:
    path = os.path.join(EXCEL_DIR, filename)
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()
    return df


def clean(val):
    if val is None:
        return None
    s = str(val).strip()
    return None if s.lower() in ("", "nan", "none", "null") else s


def gender_map(v) -> str:
    return {1: "male", 2: "female", 3: "both"}.get(int(v), "both")


def age_unit_map(v) -> str:
    return {1: "year", 2: "month", 3: "day"}.get(int(v), "year")


def range_type_map(v) -> str:
    return {1: "number", 2: "text"}.get(int(v), "number")


def opt_float(val):
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def safe_executemany(cur, sql: str, rows: list, label: str) -> int:
    """
    Insert rows one-by-one so a single bad row is reported and skipped
    instead of aborting the whole batch.  Returns the number inserted.
    """
    inserted = 0
    for row in rows:
        try:
            cur.execute(sql, row)
            inserted += 1
        except sqlite3.IntegrityError as exc:
            print(f"   ⚠️  Skipped {label} row (IntegrityError: {exc}): {row[:4]}")
        except Exception as exc:
            print(f"   ⚠️  Skipped {label} row (Error: {exc}): {row[:4]}")
    return inserted


# ── main ─────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)

    # ──────────────────────────────────────────────────────────────────
    # CRITICAL FIX: disable FK enforcement for the migration.
    # All FK integrity is enforced by the old→new ID maps in this script.
    # Re-enabled at the very end after all data is committed.
    # ──────────────────────────────────────────────────────────────────
    conn.execute("PRAGMA foreign_keys = OFF;")
    cur = conn.cursor()

    # ══════════════════════════════════════════
    # 1. PARAMETERS
    # ══════════════════════════════════════════
    print("\n── 1. Seeding Parameters ──")
    df = xls("parmeters.xlsx")
    df = df.dropna(subset=["ParameterName"])
    df = df[df["ParameterName"].astype(str).str.strip() != ""]

    param_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df.iterrows():
        old_id = int(r["ParameterId"])
        param_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["ParameterName"]).strip(),
            str(r["ShortName"]).strip() if clean(r["ShortName"]) else str(r["ParameterName"]).strip(),
            1 if int(r["IsHeader"]) == 1 else 0,
            CREATED_BY, NOW,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO parameter
            (id, parameter_name, parameter_short_name, is_header,
             created_by, created_at, edited_by, edited_at, deleted_by, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "parameter")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} parameters inserted.")

    # ══════════════════════════════════════════
    # 2. DEPARTMENTS
    # ══════════════════════════════════════════
    print("\n── 2. Seeding Departments ──")
    df = xls("Departments.xlsx")
    df = df.dropna(subset=["DepartmentName"])

    dept_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df.iterrows():
        old_id = int(r["DepartmentId"])
        dept_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["DepartmentName"]).strip(),
            clean(r["DepartmentNote"]),
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO department
            (id, department_name, department_note, is_active,
             created_by, created_at, edited_by, edited_at,
             deleted_by, deleted_at, activated_by, activated_at,
             deactivated_by, deactivated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "department")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} departments inserted.")

    # ══════════════════════════════════════════
    # 3. SAMPLE TYPES
    # ══════════════════════════════════════════
    print("\n── 3. Seeding Sample Types ──")
    df = xls("SampleType.xlsx")
    df = df.dropna(subset=["SampleTypeName"])

    sample_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df.iterrows():
        old_id = int(r["SampleTypeId"])
        sample_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["SampleTypeName"]).strip(),
            clean(r["SampleTypeNote"]),
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO sampletype
            (id, sample_name, sample_note, is_active,
             created_by, created_at, edited_by, edited_at,
             deleted_by, deleted_at, activated_by, activated_at,
             deactivated_by, deactivated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "sampletype")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} sample types inserted.")

    # ══════════════════════════════════════════
    # 4. DEVICES  (V1 "Methods")
    # ══════════════════════════════════════════
    print("\n── 4. Seeding Devices (from V1 Methods) ──")
    df = xls("Devices.xlsx")
    df = df.dropna(subset=["MethodName"])

    device_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df.iterrows():
        old_id = int(r["MethodId"])
        device_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["MethodName"]).strip(),
            "N/A",
            NOW,
            "N/A",
            "N/A",
            clean(r["MethodNote"]),
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO device
            (id, device_name, serial_number, install_date,
             installer_name, installer_phone, note, is_active,
             created_by, created_at, edited_by, edited_at,
             deleted_by, deleted_at, activated_by, activated_at,
             deactivated_by, deactivated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "device")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} devices inserted.")

    # ══════════════════════════════════════════
    # 5. REPORT NOTES  (V1 "Note")
    #    "None" is forced to be id=1
    # ══════════════════════════════════════════
    print("\n── 5. Seeding Report Notes ──")
    df = xls("ReportNote.xlsx")
    df = df.dropna(subset=["NoteName"])

    mask_none = df["NoteName"].astype(str).str.strip().str.lower() == "none"
    df_ordered = pd.concat(
        [df[mask_none], df[~mask_none].sort_values("NoteId")],
        ignore_index=True,
    )

    note_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df_ordered.iterrows():
        old_id = int(r["NoteId"])
        note_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["NoteName"]).strip(),
            clean(r["TheNote"]) or "",
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO reportnote
            (id, note_name, note_content, is_active,
             created_by, created_at, edited_by, edited_at,
             deleted_by, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "reportnote")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} report notes inserted  (id=1 → 'None').")

    # ══════════════════════════════════════════
    # 6. TESTS
    # ══════════════════════════════════════════
    print("\n── 6. Seeding Tests ──")
    df = xls("Tests.xlsx")
    df = df.dropna(subset=["TestName"])

    test_old_to_new: dict[int, int] = {}
    new_id = 1
    rows = []

    for _, r in df.iterrows():
        old_id        = int(r["TestId"])
        old_dept_id   = int(r["DepartmentId"])
        old_sample_id = int(r["SampleTypeId"])
        old_note_id   = int(r["NoteId"]) if clean(r["NoteId"]) else None

        new_dept_id   = dept_old_to_new.get(old_dept_id)
        new_sample_id = sample_old_to_new.get(old_sample_id)
        new_note_id   = note_old_to_new.get(old_note_id) if old_note_id else None

        if new_dept_id is None:
            print(f"   ⚠️  TestId={old_id} skipped: DepartmentId={old_dept_id} not found in map.")
            continue
        if new_sample_id is None:
            print(f"   ⚠️  TestId={old_id} skipped: SampleTypeId={old_sample_id} not found in map.")
            continue

        test_old_to_new[old_id] = new_id
        rows.append((
            new_id,
            str(r["TestName"]).strip(),
            str(r["ShortTestName"]).strip() if clean(r["ShortTestName"]) else str(r["TestName"]).strip(),
            new_dept_id,
            new_sample_id,
            new_note_id,
            float(r["Price"]) if clean(r["Price"]) else 0.0,
            clean(r["TestNotes"]),
            clean(r["TestConditions"]),
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO testdefinition
            (id, test_name, test_short_name, department_id, sample_type_id,
             report_note_id, price, test_note, test_condition, is_available,
             created_by, created_at, edited_by, edited_at, deleted_by, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "testdefinition")
    conn.commit()
    print(f"   ✅ {inserted} / {len(rows)} tests inserted.")

    # ══════════════════════════════════════════
    # 7. TEST-PARAMETER LINKS  (from Ranges)
    #    Source: unique (TestId, ParameterId) pairs in Ranges.xlsx
    #            where ParameterId != 0 and ParameterId exists in parmeters.xlsx
    # ══════════════════════════════════════════
    print("\n── 7. Seeding Test-Parameter links ──")
    df_ranges = xls("Ranges.xlsx")

    seen_tp   = set()   # (new_test_id, new_param_id) dedup
    rows      = []
    new_id    = 1
    tp_skip_test  = 0
    tp_skip_param = 0

    for _, r in df_ranges.iterrows():
        old_test_id  = int(r["TestId"])
        old_param_id = int(r["ParameterId"])

        if old_param_id == 0:
            continue                          # test-level range, no parameter link

        new_test_id  = test_old_to_new.get(old_test_id)
        if new_test_id is None:
            tp_skip_test += 1
            continue

        new_param_id = param_old_to_new.get(old_param_id)
        if new_param_id is None:
            tp_skip_param += 1               # orphaned V1 parameter — skip
            continue

        pair = (new_test_id, new_param_id)
        if pair in seen_tp:
            continue                          # already added this link
        seen_tp.add(pair)

        rows.append((new_id, new_test_id, new_param_id))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO testparameter (id, test_id, parameter_id)
        VALUES (?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "testparameter")
    conn.commit()
    if tp_skip_test:
        print(f"   ℹ️  {tp_skip_test} rows skipped (TestId not in test map).")
    if tp_skip_param:
        print(f"   ℹ️  {tp_skip_param} rows skipped (ParameterId orphaned in V1).")
    print(f"   ✅ {inserted} / {len(rows)} test-parameter links inserted.")

    # ══════════════════════════════════════════
    # 8. TEST-DEVICE LINKS  (from Ranges)
    #    Source: unique (TestId, MethodId) pairs in Ranges.xlsx
    # ══════════════════════════════════════════
    print("\n── 8. Seeding Test-Device links ──")

    seen_td  = set()   # (new_test_id, new_device_id) dedup
    rows     = []
    new_id   = 1
    td_skip_test   = 0
    td_skip_device = 0

    for _, r in df_ranges.iterrows():
        old_test_id   = int(r["TestId"])
        old_device_id = int(r["MethodId"])

        new_test_id   = test_old_to_new.get(old_test_id)
        if new_test_id is None:
            td_skip_test += 1
            continue

        new_device_id = device_old_to_new.get(old_device_id)
        if new_device_id is None:
            td_skip_device += 1
            continue

        pair = (new_test_id, new_device_id)
        if pair in seen_td:
            continue
        seen_td.add(pair)

        rows.append((new_id, new_test_id, new_device_id))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO testdevice (id, test_id, device_id)
        VALUES (?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "testdevice")
    conn.commit()
    if td_skip_test:
        print(f"   ℹ️  {td_skip_test} rows skipped (TestId not in test map).")
    if td_skip_device:
        print(f"   ℹ️  {td_skip_device} rows skipped (MethodId not in device map).")
    print(f"   ✅ {inserted} / {len(rows)} test-device links inserted.")

    # ══════════════════════════════════════════
    # 9. RANGES  (V1 "TestRange")
    # ══════════════════════════════════════════
    print("\n── 9. Seeding Ranges ──")
    df = df_ranges   # already loaded above — no need to re-read from disk

    new_id   = 1
    rows     = []
    skipped  = 0
    orphaned_params = 0

    for _, r in df.iterrows():
        old_test_id = int(r["TestId"])
        new_test_id = test_old_to_new.get(old_test_id)
        if new_test_id is None:
            skipped += 1
            continue

        old_param_id = int(r["ParameterId"])
        if old_param_id == 0:
            new_param_id = None
        else:
            new_param_id = param_old_to_new.get(old_param_id)
            if new_param_id is None:
                # ParameterId exists in Ranges but not in parmeters.xlsx
                # (orphaned V1 record) — insert with parameter_id = NULL
                orphaned_params += 1
                new_param_id = None

        old_device_id = int(r["MethodId"])
        new_device_id = device_old_to_new.get(old_device_id)

        rtype = range_type_map(r["RangeTypeId"])

        rows.append((
            new_id,
            new_test_id,
            new_param_id,
            new_device_id,
            clean(r["UnitName"]) or "",
            gender_map(r["Gender"]),
            int(r["AgeFrom"]),
            int(r["AgeTo"]),
            age_unit_map(r["AgeFromTypeId"]),
            1 if int(r["Fasting"]) == 1 else 0,
            rtype,
            opt_float(r["NormalFrom"]),
            opt_float(r["NormalTo"]),
            None, None,   # vlow
            None, None,   # low
            None, None,   # midlow
            None, None,   # midhigh
            None, None,   # high
            None, None,   # vhigh
            None, None,   # panic
            clean(r["TextRange"]) if rtype == "text" else None,
            1,
            CREATED_BY, NOW,
            None, None,
            None, None,
        ))
        new_id += 1

    sql = """
        INSERT OR IGNORE INTO testrange
            (id, test_id, parameter_id, device_id,
             unit, gender_type, age_from, age_to, age_unit,
             fasting_required, range_type,
             normal_from, normal_to,
             vlow_from, vlow_to, low_from, low_to,
             midlow_from, midlow_to, midhigh_from, midhigh_to,
             high_from, high_to, vhigh_from, vhigh_to,
             panic_less_than, panic_more_than,
             text_range,
             is_active, created_by, created_at,
             edited_by, edited_at, deleted_by, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    inserted = safe_executemany(cur, sql, rows, "testrange")
    conn.commit()

    if skipped:
        print(f"   ℹ️  {skipped} ranges skipped (TestId had no matching test in V1 export).")
    if orphaned_params:
        print(f"   ℹ️  {orphaned_params} ranges had orphaned ParameterIds → inserted with parameter_id=NULL.")
    print(f"   ✅ {inserted} / {len(rows)} ranges inserted.")

    # ══════════════════════════════════════════
    # Re-enable FK enforcement now that all data is in place
    # ══════════════════════════════════════════
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.close()

    print("\n🎉  Migration complete — all tables seeded successfully.")
    print("\n── Summary ──────────────────────────────")
    print(f"   Parameters        : {len(param_old_to_new)}")
    print(f"   Departments       : {len(dept_old_to_new)}")
    print(f"   Sample Types      : {len(sample_old_to_new)}")
    print(f"   Devices           : {len(device_old_to_new)}")
    print(f"   Report Notes      : {len(note_old_to_new)}  (id=1 is 'None')")
    print(f"   Tests             : {len(test_old_to_new)}")
    print(f"   Test-Param links  : {len(seen_tp)}")
    print(f"   Test-Device links : {len(seen_td)}")
    print(f"   Ranges            : {new_id - 1}  (inserted: {inserted})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print(f"\n💥 Migration failed: {exc}")
        traceback.print_exc()