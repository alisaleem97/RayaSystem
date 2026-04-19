import sys; sys.path.insert(0, r'c:\Users\aliss\Desktop\lab_system')
from routes.generate_pdf import generate_native_barcode_pdf
class Patient:
    patient_id = '1100053'
    full_name = 'عائشه مكي طالب'
    gender = 'Female'
    age = 12
    age_unit = 'years'
class Template:
    paper_width = '2in'
    paper_height = '1in'
    elements = '[{"type": "patient_name", "x": 79, "y": 0, "width": 113, "height": 33}, {"type": "barcode_image", "x": 43, "y": 44, "width": 103, "height": 47}, {"type": "test_list", "x": 0, "y": 10, "width": 98, "height": 27}]'
buffer = generate_native_barcode_pdf(Patient(), {'Blood': ['D3', 'Calcium']}, Template())
with open('native_test.pdf', 'wb') as f: f.write(buffer.read())
print('Created native_test.pdf:', len(buffer.getvalue()))
