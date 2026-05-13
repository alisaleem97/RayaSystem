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
        
        # Wait a moment for file to be fully written
        time.sleep(0.5)
        
        if os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
            return True
        else:
            raise RuntimeError(f"PDF not generated. Edge stderr: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("PDF generation timed out (30s)")
    finally:
        # Clean up temp profile
        try:
            import shutil
            shutil.rmtree(temp_profile, ignore_errors=True)
        except:
            pass


def print_pdf_to_printer(pdf_path, printer_name, sumatra_path=None):
    """Print a PDF file to a specific printer using SumatraPDF."""
    if not sumatra_path:
        sumatra_path = find_sumatra()
    
    if not sumatra_path:
        raise FileNotFoundError(
            "SumatraPDF.exe not found. Please download SumatraPDF portable from:\n"
            "https://www.sumatrapdfreader.org/download-free-pdf-viewer\n"
            "and place SumatraPDF.exe in the NexPrint folder."
        )
    
    cmd = [
        sumatra_path,
        '-print-to', printer_name,
        '-silent',
        '-print-settings', 'noscale',
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


def print_job(server_url, patient_id, barcode_printer, receipt_printer, edge_path=None, sumatra_path=None):
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
        if barcode_printer:
            barcode_url = f"{server_url.rstrip('/')}/print-barcode/{patient_id}"
            barcode_pdf = os.path.join(temp_dir, 'barcode.pdf')
            
            try:
                render_html_to_pdf(barcode_url, barcode_pdf, edge_path)
                print_pdf_to_printer(barcode_pdf, barcode_printer, sumatra_path)
                results['barcode_success'] = True
            except Exception as e:
                results['barcode_error'] = str(e)
        
        # --- Print Receipt ---
        if receipt_printer:
            receipt_url = f"{server_url.rstrip('/')}/print-receipt/{patient_id}"
            receipt_pdf = os.path.join(temp_dir, 'receipt.pdf')
            
            try:
                render_html_to_pdf(receipt_url, receipt_pdf, edge_path)
                print_pdf_to_printer(receipt_pdf, receipt_printer, sumatra_path)
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
