"""
NexPrint - Printing Logic
Uses Microsoft Edge headless for HTML→PDF rendering
Uses SumatraPDF for silent printing to specific printers
"""

import subprocess
import os
import sys
import tempfile
import time
import winreg
import PyPDF2 # Forced global import for PyInstaller

def find_edge_executable():
    """Find Microsoft Edge executable on the system."""
    # Common Edge installation paths
    common_paths = [
        os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('ProgramFiles', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Try registry
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        edge_path, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        if os.path.exists(edge_path):
            return edge_path
    except:
        pass
    
    # Try Chrome as fallback
    chrome_paths = [
        os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('ProgramFiles', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            return path
    
    return None


def find_sumatra():
    """Find SumatraPDF executable - look in the app directory first."""
    # Check in the same directory as the script/exe
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    local_sumatra = os.path.join(app_dir, 'SumatraPDF.exe')
    if os.path.exists(local_sumatra):
        return local_sumatra
    
    # Check in a tools subdirectory
    tools_sumatra = os.path.join(app_dir, 'tools', 'SumatraPDF.exe')
    if os.path.exists(tools_sumatra):
        return tools_sumatra
    
    # Check in PATH
    for path_dir in os.environ.get('PATH', '').split(';'):
        sumatra_path = os.path.join(path_dir, 'SumatraPDF.exe')
        if os.path.exists(sumatra_path):
            return sumatra_path
    
    return None


def render_html_to_pdf(url, output_pdf, edge_path=None):
    """Use Edge/Chrome headless to render an HTML page to PDF."""
    if not edge_path:
        edge_path = find_edge_executable()
    
    if not edge_path:
        raise FileNotFoundError("Microsoft Edge or Google Chrome not found. Please install Edge or Chrome.")
    
    # Create a unique temp user-data-dir to avoid conflicts with running browser
    temp_profile = tempfile.mkdtemp(prefix='nexprint_')
    
    cmd = [
        edge_path,
        '--headless',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        # These two flags force Edge to fully run all JS and paint all canvases before capturing the PDF.
        # Without them, bwip-js canvas barcodes are not yet rendered when the PDF snapshot is taken.
        '--run-all-compositor-stages-before-draw',
        '--virtual-time-budget=5000',
        f'--print-to-pdf={output_pdf}',
        '--no-pdf-header-footer',
        f'--user-data-dir={temp_profile}',
        url
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # Wait for file to be fully written (up to 5s)
        for _ in range(10):
            if os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
                time.sleep(0.3)
                return True
            time.sleep(0.5)
        
        raise RuntimeError(f"PDF not generated. Edge stderr: {result.stderr[-200:] if result.stderr else 'none'}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("PDF generation timed out (30s)")
    finally:
        # Clean up temp profile
        try:
            import shutil
            shutil.rmtree(temp_profile, ignore_errors=True)
        except:
            pass


def print_pdf_to_printer(pdf_path, printer_name, sumatra_path=None, use_fit=False, orientation=None):
    """Print a PDF file to a specific printer using SumatraPDF."""
    if not sumatra_path:
        sumatra_path = find_sumatra()
    
    if not sumatra_path:
        raise FileNotFoundError(
            "SumatraPDF.exe not found. Please download SumatraPDF portable from:\n"
            "https://www.sumatrapdfreader.org/download-free-pdf-viewer\n"
            "and place SumatraPDF.exe in the NexPrint folder."
        )
    
    scale_setting = 'fit' if use_fit else 'noscale'
    if orientation in ['portrait', 'landscape']:
        scale_setting += f',{orientation}'
    # Label printers (like 4x2) often have width > height but are treated as portrait by the driver.
    # Forcing ',landscape' causes SumatraPDF to rotate them 90 degrees, breaking the barcode layout!
    
    cmd = [
        sumatra_path,
        '-print-to', printer_name,
        '-silent',
        '-print-settings', scale_setting,
        pdf_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        return True
    except subprocess.TimeoutExpired:
        raise RuntimeError("Print command timed out (30s)")


def parse_dim_to_px(dim_str, dpi=96):
    """Convert a CSS dimension string (e.g., '4in', '50mm') to pixels at the given DPI."""
    if not dim_str or str(dim_str).strip().lower() in ('auto', ''):
        return None
    dim_str = str(dim_str).strip().lower()
    import re
    match = re.match(r'^([\d\.]+)\s*([a-z]*)$', dim_str)
    if not match:
        return None
    val, unit = float(match.group(1)), match.group(2)
    if unit == 'mm': return val / 25.4 * dpi
    elif unit == 'cm': return val / 2.54 * dpi
    elif unit == 'in': return val * dpi
    elif unit == 'px': return val
    else: return val


def render_page_to_image(url, output_path, viewport_w, viewport_h, scale=3, edge_path=None):
    """Render a web page as a high-resolution PNG using Edge/Chrome headless screenshot mode.
    scale=3 means 3x resolution (~288 effective DPI), producing crisp output on thermal printers.
    """
    if not edge_path:
        edge_path = find_edge_executable()
    if not edge_path:
        raise FileNotFoundError("Microsoft Edge or Google Chrome not found.")

    temp_profile = tempfile.mkdtemp(prefix='nexprint_')

    cmd = [
        edge_path,
        '--headless=old',  # Old headless mode required — new mode ignores --screenshot
        '--disable-gpu',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--run-all-compositor-stages-before-draw',
        '--virtual-time-budget=5000',
        f'--force-device-scale-factor={scale}',
        f'--window-size={viewport_w},{viewport_h}',
        f'--screenshot={output_path}',
        f'--user-data-dir={temp_profile}',
        url
    ]

    try:
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        for _ in range(10):
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                time.sleep(0.3)
                return True
            time.sleep(0.5)

        raise RuntimeError("Screenshot was not generated by Edge")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Screenshot generation timed out (30s)")
    finally:
        try:
            import shutil
            shutil.rmtree(temp_profile, ignore_errors=True)
        except:
            pass


def print_image_via_gdi(image_path, printer_name):
    """Print an image to a specific printer using Windows .NET System.Drawing (GDI).
    This sends proper GDI commands to the printer driver, which renders at native DPI —
    the same rendering path that browsers use, producing clean output on thermal printers.
    Completely bypasses SumatraPDF.
    """
    # Escape single quotes for PowerShell string literals
    img_escaped = image_path.replace("'", "''")
    prn_escaped = printer_name.replace("'", "''")

    ps_script = f"""
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile('{img_escaped}')
$pd = New-Object System.Drawing.Printing.PrintDocument
$pd.PrinterSettings.PrinterName = '{prn_escaped}'
$pd.DefaultPageSettings.Margins = New-Object System.Drawing.Printing.Margins(0,0,0,0)
$pd.add_PrintPage({{
    param($sender, $e)
    $dest = New-Object System.Drawing.RectangleF(0, 0, $e.PageBounds.Width, $e.PageBounds.Height)
    $e.Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $e.Graphics.DrawImage($img, $dest)
}})
$pd.Print()
$img.Dispose()
"""

    result = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )

    if result.returncode != 0:
        raise RuntimeError(f"GDI print failed: {result.stderr[:300]}")

    return True


def parse_dim_to_pt(dim_str):
    """Convert a dimension string (e.g., '4in', '50mm', '80px') to PDF points (1/72 inch)."""
    if not dim_str or dim_str.lower() == 'auto': return None
    dim_str = str(dim_str).strip().lower()
    try:
        import re
        match = re.match(r'^([\d\.]+)\s*([a-z]*)$', dim_str)
        if not match: return None
        val, unit = float(match.group(1)), match.group(2)
        
        if unit == 'mm': return val * 2.83465
        elif unit == 'cm': return val * 28.3465
        elif unit == 'in': return val * 72.0
        elif unit == 'px': return val * 0.75
        else: return val # assume points
    except:
        return None

def crop_pdf(pdf_path, width_str, height_str):
    """Crop the PDF to the given dimensions starting from the top left corner."""
    width_pt = parse_dim_to_pt(width_str)
    height_pt = parse_dim_to_pt(height_str)
    if not width_pt and not height_pt:
        return
        
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            if len(reader.pages) == 0: return
            page = reader.pages[0]
            
            orig_height = float(page.mediabox.height)
            orig_width = float(page.mediabox.width)
            
            w = width_pt if width_pt else orig_width
            h = height_pt if height_pt else orig_height
            
            # Physically shift the PDF contents down by (orig_height - bounding box height)
            # This perfectly zeroes the origin to (0,0), exactly like Native PDFs do,
            # preventing label printers from getting confused by offset CropBoxes.
            from PyPDF2 import Transformation
            page.add_transformation(Transformation().translate(tx=0, ty=-(orig_height - h)))
            
            page.mediabox.lower_left = (0, 0)
            page.mediabox.upper_right = (w, h)
            
            page.cropbox.lower_left = (0, 0)
            page.cropbox.upper_right = (w, h)
            
            writer = PyPDF2.PdfWriter()
            writer.add_page(page)
            
        with open(pdf_path, 'wb') as f:
            writer.write(f)
    except Exception as e:
        raise RuntimeError(f"Failed to crop PDF: {e}")



def print_job(server_url, patient_id, barcode_printer, receipt_printer, print_token='', barcode_width='', barcode_height='', receipt_width='', receipt_height='', barcode_orientation='auto', receipt_orientation='auto', edge_path=None, sumatra_path=None):
    """
    Complete print job: render barcode + receipt to PDF, then print to configured printers.
    Returns dict with results.
    """
    results = {
        'barcode_success': False,
        'receipt_success': False,
        'barcode_error': None,
        'receipt_error': None
    }
    
    temp_dir = tempfile.mkdtemp(prefix='nexprint_job_')
    
    try:
        # --- Print Barcode ---
        # Server generates one barcode label per sample type as PNG.
        # NexPrint downloads each page and prints via GDI.
        if barcode_printer:
            try:
                import urllib.request
                base_url = f"{server_url.rstrip('/')}/api/print-barcode-image/{patient_id}?print_token={print_token}"
                
                # Request page 0 to get total page count
                response = urllib.request.urlopen(f"{base_url}&page=0", timeout=15)
                page_count = int(response.headers.get('X-Page-Count', '1'))
                
                # Save and print page 0
                barcode_img_0 = os.path.join(temp_dir, 'barcode_0.png')
                with open(barcode_img_0, 'wb') as f:
                    f.write(response.read())
                if os.path.getsize(barcode_img_0) > 0:
                    print_image_via_gdi(barcode_img_0, barcode_printer)
                
                # Print remaining pages (if multiple sample types)
                for pg in range(1, page_count):
                    resp = urllib.request.urlopen(f"{base_url}&page={pg}", timeout=15)
                    barcode_img_pg = os.path.join(temp_dir, f'barcode_{pg}.png')
                    with open(barcode_img_pg, 'wb') as f:
                        f.write(resp.read())
                    if os.path.getsize(barcode_img_pg) > 0:
                        print_image_via_gdi(barcode_img_pg, barcode_printer)
                
                results['barcode_success'] = True
            except Exception as e:
                results['barcode_error'] = str(e)

        
        # --- Print Receipt ---
        if receipt_printer:
            receipt_url = f"{server_url.rstrip('/')}/print-receipt/{patient_id}?print_token={print_token}"
            receipt_pdf = os.path.join(temp_dir, 'receipt.pdf')
            
            try:
                render_html_to_pdf(receipt_url, receipt_pdf, edge_path)
                if not receipt_width: receipt_width = '80mm'
                # Do NOT force 210mm height here; let it flow naturally or use default to prevent shifting bugs
                crop_pdf(receipt_pdf, receipt_width, receipt_height)
                
                orient = receipt_orientation if receipt_orientation in ['portrait', 'landscape'] else None
                # Print 1 copy of the receipt
                print_pdf_to_printer(receipt_pdf, receipt_printer, sumatra_path, use_fit=False, orientation=orient)
                results['receipt_success'] = True
            except Exception as e:
                results['receipt_error'] = str(e)
    
    finally:
        # Clean up temp files after a short delay
        def cleanup():
            time.sleep(5)
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        
        import threading
        threading.Thread(target=cleanup, daemon=True).start()
    
    return results


def get_available_printers():
    """List all available printers on the system using win32print."""
    try:
        import win32print
        printers = []
        for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
            printers.append(printer[2])  # printer[2] is the printer name
        return printers
    except ImportError:
        # win32print not available, try PowerShell
        try:
            result = subprocess.run(
                ['powershell', '-Command', 'Get-Printer | Select-Object -ExpandProperty Name'],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            if result.returncode == 0:
                return [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        except:
            pass
    return []
