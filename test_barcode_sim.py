import sys, os, time
sys.path.insert(0, r'c:\Users\aliss\Desktop\lab_system\print_client')
from print_client.printer import render_html_to_pdf, find_edge_executable, crop_pdf

html_content = '''
<html>
<head>
<style>
body { background: white; padding: 0; margin: 0; align-items: flex-start; justify-content: flex-start; display: block; }
.barcode-page { border: none; box-shadow: none; position: absolute; top: 0; left: 0; width: 2in; height: 1in; }
.barcode-element { position: absolute; overflow: hidden; }
</style>
<script src="https://cdn.jsdelivr.net/npm/bwip-js/dist/bwip-js-min.js"></script>
</head>
<body>
<div class="barcode-page">
  <div class="barcode-element" style="left: 79px; top: 0px; width: 113px; height: 33px;"><div style="padding:5px;">Aisha Maki Taleb</div></div>
  <div class="barcode-element" style="left: 0px; top: 10px; width: 98px; height: 27px;"><div style="padding:5px;">Test D3</div></div>
  <div class="barcode-element" style="left: 0px; top: 30px; width: 67px; height: 29px;"><div style="padding:5px;">Blood</div></div>
  <div class="barcode-element" style="left: 43px; top: 44px; width: 103px; height: 47px;">
    <div style="text-align: center; padding: 5px;">
      <canvas id="mycanvas"></canvas>
      <script>
      setTimeout(() => {
        try {
          bwipjs.toCanvas('mycanvas', { bcid: 'code128', text: '1100053', scale: 2, height: 10 });
        } catch(e) {}
      }, 100);
      </script>
    </div>
  </div>
</div>
<!-- Wait for script block -->
<script>
  setTimeout(() => {}, 2000);
</script>
</body>
</html>
'''

with open('test_barcode_simulation.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

edge = find_edge_executable()
pdf_nocrop = 'test_simulation_nocrop.pdf'
pdf_crop = 'test_simulation_crop.pdf'

render_html_to_pdf('file:///' + os.path.abspath('test_barcode_simulation.html'), pdf_nocrop, edge)

import shutil
shutil.copy(pdf_nocrop, pdf_crop)
crop_pdf(pdf_crop, '2in', '1in')

import PyPDF2
with open(pdf_crop, 'rb') as f:
    page = PyPDF2.PdfReader(f).pages[0]
    print('Cropped MediaBox:', page.mediabox)
    
print("Done!")
