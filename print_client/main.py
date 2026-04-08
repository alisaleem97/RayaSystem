"""
NexPrint — Auto Print Client for NexLab LIS
A standalone Windows application that silently prints barcodes and receipts
when patients are registered in the lab system.

Run on each client PC (not the server).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
from datetime import datetime
from print_server import PrintServer
from printer import find_edge_executable, find_sumatra, get_available_printers

# --- Config ---
CONFIG_FILE = 'config.json'
DEFAULT_PORT = 13501

def get_app_dir():
    """Get the directory where the app is running from."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def load_config():
    """Load config from JSON file."""
    config_path = os.path.join(get_app_dir(), CONFIG_FILE)
    default = {
        'server_url': 'http://localhost:8000',
        'barcode_printer': '',
        'receipt_printer': '',
        'port': DEFAULT_PORT
    }
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                saved = json.load(f)
                default.update(saved)
    except:
        pass
    return default

def save_config(config):
    """Save config to JSON file."""
    config_path = os.path.join(get_app_dir(), CONFIG_FILE)
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


class SettingsDialog(tk.Toplevel):
    """Settings dialog for configuring printers and server URL."""
    
    def __init__(self, parent, config, available_printers):
        super().__init__(parent)
        self.title("Set Printer")
        self.config = config
        self.result = None
        
        # Window setup
        self.geometry("420x480")
        self.resizable(False, False)
        self.configure(bg='white')
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 210
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 240
        self.geometry(f"+{x}+{y}")
        
        # Title bar
        title_bar = tk.Frame(self, bg='#c0392b', height=30)
        title_bar.pack(fill=tk.X)
        tk.Label(title_bar, text="Set Printer", bg='#c0392b', fg='white', 
                 font=('Arial', 10)).pack(side=tk.LEFT, padx=10, pady=5)
        tk.Button(title_bar, text="✕", bg='#c0392b', fg='white', bd=0,
                  font=('Arial', 12, 'bold'), command=self.destroy,
                  activebackground='#e74c3c').pack(side=tk.RIGHT, padx=5)
        
        main_frame = tk.Frame(self, bg='white', padx=30, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Server URL
        tk.Label(main_frame, text="Server URL", font=('Arial', 14, 'bold'),
                 bg='white', fg='#2c3e50').pack(pady=(10, 5))
        self.server_var = tk.StringVar(value=config.get('server_url', 'http://localhost:8000'))
        server_entry = tk.Entry(main_frame, textvariable=self.server_var,
                               font=('Arial', 12), width=30, bd=2, relief=tk.GROOVE)
        server_entry.pack(pady=(0, 15))
        
        # Barcode Printer
        tk.Label(main_frame, text="Barcode Printer", font=('Arial', 14, 'bold'),
                 bg='white', fg='#2c3e50').pack(pady=(10, 5))
        self.barcode_var = tk.StringVar(value=config.get('barcode_printer', ''))
        if available_printers:
            barcode_combo = ttk.Combobox(main_frame, textvariable=self.barcode_var,
                                        values=available_printers, font=('Arial', 12), width=28)
            barcode_combo.pack(pady=(0, 15))
        else:
            barcode_entry = tk.Entry(main_frame, textvariable=self.barcode_var,
                                    font=('Arial', 12), width=30, bd=2, relief=tk.GROOVE)
            barcode_entry.pack(pady=(0, 15))
        
        # Receipt Printer
        tk.Label(main_frame, text="Receipt Printer", font=('Arial', 14, 'bold'),
                 bg='white', fg='#2c3e50').pack(pady=(10, 5))
        self.receipt_var = tk.StringVar(value=config.get('receipt_printer', ''))
        if available_printers:
            receipt_combo = ttk.Combobox(main_frame, textvariable=self.receipt_var,
                                        values=available_printers, font=('Arial', 12), width=28)
            receipt_combo.pack(pady=(0, 20))
        else:
            receipt_entry = tk.Entry(main_frame, textvariable=self.receipt_var,
                                    font=('Arial', 12), width=30, bd=2, relief=tk.GROOVE)
            receipt_entry.pack(pady=(0, 20))
        
        # Save Button
        save_btn = tk.Button(main_frame, text="Save", font=('Arial', 14, 'bold'),
                             bg='#f0f0f0', fg='#2c3e50', width=20, height=2,
                             bd=2, relief=tk.RAISED, command=self._save,
                             cursor='hand2')
        save_btn.pack(pady=10)
    
    def _save(self):
        self.result = {
            'server_url': self.server_var.get().strip(),
            'barcode_printer': self.barcode_var.get().strip(),
            'receipt_printer': self.receipt_var.get().strip()
        }
        self.destroy()


class NexPrintApp:
    """Main NexPrint application."""
    
    def __init__(self):
        self.config = load_config()
        self.server = None
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("NexPrint")
        self.root.geometry("700x400")
        self.root.minsize(600, 300)
        self.root.configure(bg='#f5f5f5')
        
        # Try to set icon
        try:
            icon_path = os.path.join(get_app_dir(), 'icon.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass
        
        self._build_ui()
        self._start_server()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _build_ui(self):
        """Build the main UI."""
        # Top bar
        top_frame = tk.Frame(self.root, bg='#2c3e50', height=40)
        top_frame.pack(fill=tk.X)
        top_frame.pack_propagate(False)
        
        tk.Label(top_frame, text="🖨️ NexPrint", font=('Arial', 12, 'bold'),
                 bg='#2c3e50', fg='white').pack(side=tk.LEFT, padx=15)
        
        # Status indicator
        self.status_label = tk.Label(top_frame, text="● Starting...", 
                                     font=('Arial', 10), bg='#2c3e50', fg='#f39c12')
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Set Names button
        settings_btn = tk.Button(top_frame, text="Set Names", font=('Arial', 10),
                                  bg='#34495e', fg='white', bd=0, padx=15, pady=5,
                                  command=self._open_settings, cursor='hand2',
                                  activebackground='#4a6785')
        settings_btn.pack(side=tk.RIGHT, padx=15, pady=5)
        
        # Log area
        log_frame = tk.Frame(self.root, bg='white', bd=1, relief=tk.SUNKEN)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, font=('Consolas', 11), bg='white',
                                fg='#2c3e50', wrap=tk.WORD, bd=0, padx=10, pady=10,
                                state=tk.DISABLED)
        
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for colored output
        self.log_text.tag_configure('info', foreground='#2c3e50')
        self.log_text.tag_configure('success', foreground='#27ae60')
        self.log_text.tag_configure('error', foreground='#e74c3c')
        self.log_text.tag_configure('warning', foreground='#f39c12')
        
        # Bottom status bar
        bottom_frame = tk.Frame(self.root, bg='#ecf0f1', height=25)
        bottom_frame.pack(fill=tk.X)
        bottom_frame.pack_propagate(False)
        
        self.printer_status = tk.Label(bottom_frame, text="", font=('Arial', 9),
                                        bg='#ecf0f1', fg='#7f8c8d')
        self.printer_status.pack(side=tk.LEFT, padx=10)
        
        self._update_printer_status()
    
    def _update_printer_status(self):
        """Update the bottom status bar with printer info."""
        bp = self.config.get('barcode_printer', 'Not set')
        rp = self.config.get('receipt_printer', 'Not set')
        server = self.config.get('server_url', 'Not set')
        self.printer_status.config(
            text=f"Server: {server}  |  Barcode: {bp or 'Not set'}  |  Receipt: {rp or 'Not set'}"
        )
    
    def _start_server(self):
        """Start the local HTTP server."""
        port = self.config.get('port', DEFAULT_PORT)
        self.server = PrintServer(port=port, app=self)
        
        try:
            self.server.start()
            self.status_label.config(text=f"● Running ({port})", fg='#27ae60')
            self.log(f"Printing Program Started ({port})", 'success')
            
            # Check dependencies
            edge = find_edge_executable()
            if edge:
                self.log(f"Edge found: {os.path.basename(edge)}", 'info')
            else:
                self.log("⚠ Edge/Chrome not found! PDF generation will fail.", 'warning')
            
            sumatra = find_sumatra()
            if sumatra:
                self.log(f"SumatraPDF found: {os.path.basename(sumatra)}", 'info')
            else:
                self.log("⚠ SumatraPDF.exe not found! Place it in the NexPrint folder.", 'warning')
            
            if not self.config.get('barcode_printer') and not self.config.get('receipt_printer'):
                self.log("⚠ No printers configured. Click 'Set Names' to configure.", 'warning')
                
        except RuntimeError as e:
            self.status_label.config(text="● Error", fg='#e74c3c')
            self.log(f"Error: {str(e)}", 'error')
            messagebox.showerror("Startup Error", str(e))
    
    def log(self, message, tag='info'):
        """Add a message to the log display."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        def _update():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        
        # Thread-safe UI update
        self.root.after(0, _update)
    
    def _open_settings(self):
        """Open the settings dialog."""
        printers = get_available_printers()
        dialog = SettingsDialog(self.root, self.config, printers)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.config.update(dialog.result)
            save_config(self.config)
            self._update_printer_status()
            self.log(f"Settings saved. Server: {self.config['server_url']}", 'success')
            self.log(f"  Barcode Printer: {self.config['barcode_printer'] or 'Not set'}", 'info')
            self.log(f"  Receipt Printer: {self.config['receipt_printer'] or 'Not set'}", 'info')
    
    def _on_close(self):
        """Handle window close."""
        if self.server:
            self.server.stop()
        self.root.destroy()
    
    def run(self):
        """Start the application."""
        self.root.mainloop()


if __name__ == '__main__':
    app = NexPrintApp()
    app.run()
