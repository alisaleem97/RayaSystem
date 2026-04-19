from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import code128
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

# Register Arabic font
pdfmetrics.registerFont(TTFont('Arabic', 'c:\\Users\\aliss\\Desktop\\lab_system\\static\\vendor\\fonts\\NotoSansArabic-Regular.ttf'))

width = 2.0 * inch
height = 1.0 * inch
c = canvas.Canvas('test_native_barcode.pdf', pagesize=(width, height))

# Element mapping functions
def convert_x(x_px): return x_px * (inch / 96.0)
def convert_y(y_px, el_height_px): return height - (y_px * (inch / 96.0)) - (el_height_px * (inch / 96.0))

# 1. Arabic Text
text = "عائشه مكي طالب"
reshaped_text = arabic_reshaper.reshape(text)
bidi_text = get_display(reshaped_text)

c.setFont('Arabic', 10)
# Patient name from DB was: X=79, Y=0, Width=113, Height=33
x = convert_x(79)
y = convert_y(0, 33)
c.drawString(x, y + 15, bidi_text)  # add some baseline offset

# 2. English text
c.setFont('Helvetica', 10)
c.drawString(convert_x(0), convert_y(10, 27) + 12, "Test D3")
c.drawString(convert_x(0), convert_y(30, 29) + 12, "Blood")

# 3. Barcode
barcode = code128.Code128("1100053", barHeight=0.3*inch, barWidth=1.0)
barcode.drawOn(c, convert_x(43), convert_y(44, 47) + 5)

c.save()
print("Native PDF created successfully at test_native_barcode.pdf!")
