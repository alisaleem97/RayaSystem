"""
NexPrint - Local HTTP Server
Receives print requests from the browser on port 13501.
Handles CORS for cross-origin requests from the lab system.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from printer import print_job


class PrintRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for print jobs."""
    
    # Reference to the main app (set by NexPrintApp)
    app = None
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging - we use our own."""
        pass
    
    def _send_cors_headers(self):
        """Send CORS headers to allow cross-origin requests from the browser."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """Health check endpoint."""
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            
            response = {
                'status': 'running',
                'app': 'NexPrint',
                'barcode_printer': self.app.config.get('barcode_printer', '') if self.app else '',
                'receipt_printer': self.app.config.get('receipt_printer', '') if self.app else ''
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle print requests."""
        if self.path == '/print':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                
                patient_id = data.get('patient_id', '')
                patient_name = data.get('patient_name', '')
                print_token = data.get('print_token', '')
                barcode_width = data.get('barcode_width', '')
                barcode_height = data.get('barcode_height', '')
                receipt_width = data.get('receipt_width', '')
                receipt_height = data.get('receipt_height', '')
                
                if not patient_id:
                    self._send_error(400, 'patient_id is required')
                    return
                
                if not self.app:
                    self._send_error(500, 'App not initialized')
                    return
                
                # Get config
                server_url = self.app.config.get('server_url', 'http://localhost:8000')
                barcode_printer = self.app.config.get('barcode_printer', '')
                receipt_printer = self.app.config.get('receipt_printer', '')
                
                if not barcode_printer and not receipt_printer:
                    self._send_error(400, 'No printers configured. Please set printer names in NexPrint.')
                    return
                
                # Log the request
                self.app.log(f"Print request received: {patient_name or patient_id}")
                
                # Run print job in a separate thread to not block the HTTP response
                def do_print():
                    try:
                        results = print_job(
                            server_url=server_url,
                            patient_id=patient_id,
                            barcode_printer=barcode_printer,
                            receipt_printer=receipt_printer,
                            print_token=print_token,
                            barcode_width=barcode_width,
                            barcode_height=barcode_height,
                            receipt_width=receipt_width,
                            receipt_height=receipt_height
                        )
                        
                        if results['barcode_success']:
                            self.app.log(f"Barcode Printed: {patient_name or patient_id}")
                        elif results['barcode_error']:
                            self.app.log(f"Barcode Error: {results['barcode_error']}")
                        
                        if results['receipt_success']:
                            self.app.log(f"Receipt Printed: {patient_name or patient_id}")
                        elif results['receipt_error']:
                            self.app.log(f"Receipt Error: {results['receipt_error']}")
                            
                    except Exception as e:
                        self.app.log(f"Print Error: {str(e)}")
                
                threading.Thread(target=do_print, daemon=True).start()
                
                # Send immediate success response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Print job queued for {patient_name or patient_id}'
                }).encode())
                
            except json.JSONDecodeError:
                self._send_error(400, 'Invalid JSON body')
            except Exception as e:
                self._send_error(500, str(e))
        else:
            self.send_response(404)
            self.end_headers()
    
    def _send_error(self, code, message):
        """Send an error response."""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({
            'success': False,
            'error': message
        }).encode())


class PrintServer:
    """Threaded HTTP server for receiving print requests."""
    
    def __init__(self, port=13501, app=None):
        self.port = port
        self.app = app
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the HTTP server in a background thread."""
        PrintRequestHandler.app = self.app
        
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), PrintRequestHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return True
        except OSError as e:
            if 'Address already in use' in str(e) or '10048' in str(e):
                raise RuntimeError(f"Port {self.port} is already in use. Is another NexPrint instance running?")
            raise
    
    def stop(self):
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server = None
