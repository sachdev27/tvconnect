import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import os
import sys
import socket
import threading
import io
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import uuid
import urllib.parse
import asyncio

# Try importing qrcode; handle gracefully if missing
try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False
    print("Warning: 'qrcode' library not found. QR features will be disabled.")

class RemoteHandler(BaseHTTPRequestHandler):
    """
    Handles HTTP requests from the phone to control the desktop app.
    Run in a separate thread, so it MUST NOT touch the UI directly.
    """
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # Security Check
        incoming_token = query_params.get('token', [None])[0]
        if incoming_token != self.server.token:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Invalid Token.")
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: sans-serif; padding: 20px; background: #f0f0f0; }}
                .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                input {{ width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }}
                button {{ width: 100%; padding: 15px; background: #007bff; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }}
                button:active {{ background: #0056b3; }}
                h2 {{ text-align: center; color: #333; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>WiFi Login Remote</h2>
                <input type="hidden" id="token" value="{self.server.token}">
                <input type="text" id="username" placeholder="Username / Mobile">
                <input type="password" id="password" placeholder="Password">
                <button onclick="sendCredentials()">Fill & Login</button>
                <p id="status" style="text-align:center; color: #666;"></p>
            </div>
            <script>
                function sendCredentials() {{
                    var u = document.getElementById('username').value;
                    var p = document.getElementById('password').value;
                    var t = document.getElementById('token').value;
                    var status = document.getElementById('status');
                    status.innerText = "Sending...";
                    fetch('/', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{username: u, password: p, token: t}})
                    }})
                    .then(response => {{
                        if(response.ok) status.innerText = "Success! Check TV.";
                        else status.innerText = "Error connecting.";
                    }})
                    .catch(err => status.innerText = "Network Error");
                }}
            </script>
        </body>
        </html>
        """
        self.wfile.write(html_content.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        try:
            data = json.loads(post_data)
            if data.get('token') != self.server.token:
                self.send_response(403)
                self.end_headers()
                return

            username = data.get('username')
            password = data.get('password')

            # CRITICAL FIX: Schedule UI update on the main thread safely
            if self.server.app_instance:
                app = self.server.app_instance
                # Fix: Use the Toga loop property directly.
                # Check if loop is available before scheduling.
                if hasattr(app, 'loop') and app.loop:
                    app.loop.call_soon_threadsafe(
                        app.apply_remote_credentials, username, password
                    )

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print(f"Error processing POST: {e}")
            self.send_response(400)
            self.end_headers()

class TvConnect(toga.App):
    def startup(self):
        # CHANGED TITLE TO VERIFY UPDATE
        self.main_window = toga.MainWindow(title="TV Connect v2")

        # Default credentials
        self.default_user = "9921939226"
        self.default_pass = "7882"
        self.default_url = "https://wifizone.actcorp.in"
        self.server_thread = None
        self.server_token = uuid.uuid4().hex

        # --- Dashboard Tab ---
        self.internet_status_label = toga.Label("Status: Initializing...", style=Pack(padding=5, font_weight='bold'))
        self.web_view = toga.WebView(style=Pack(flex=1))

        btn_check = toga.Button('Check Connectivity', on_press=self.check_internet_handler, style=Pack(padding=5))
        btn_fill = toga.Button('Auto-Fill & Login', on_press=self.fill_login_form_and_submit, style=Pack(padding=5, background_color='#4CAF50', color='white'))

        dashboard_box = toga.Box(
            children=[
                toga.Box(children=[self.internet_status_label, btn_check, btn_fill], style=Pack(direction=ROW, padding=5)),
                self.web_view
            ],
            style=Pack(direction=COLUMN, padding=10)
        )

        # --- Settings Tab ---
        self.input_user = toga.TextInput(value=self.default_user, style=Pack(padding=5))
        self.input_pass = toga.TextInput(value=self.default_pass, style=Pack(padding=5))
        self.input_url = toga.TextInput(value=self.default_url, style=Pack(padding=5))

        settings_box = toga.Box(
            children=[
                toga.Label("WiFi Credentials", style=Pack(padding_top=10, font_weight='bold')),
                toga.Label("Username:", style=Pack(padding_top=5)), self.input_user,
                toga.Label("Password:", style=Pack(padding_top=5)), self.input_pass,
                toga.Label("Login URL:", style=Pack(padding_top=5)), self.input_url,
                toga.Button('Open Android Date Settings', on_press=self.open_system_date_time_settings, style=Pack(padding_top=20)),
                toga.Button('Exit App', on_press=self.close_app, style=Pack(padding_top=10))
            ],
            style=Pack(direction=COLUMN, padding=20)
        )

        # --- Remote Tab ---
        self.qr_image_view = toga.ImageView(style=Pack(width=200, height=200, padding_top=20))
        self.remote_status_label = toga.Label("Status: Server Stopped", style=Pack(padding=10))

        remote_box = toga.Box(
            children=[
                toga.Label("Scan to Control from Phone", style=Pack(font_size=18, font_weight='bold', padding_bottom=10)),
                toga.Label("Ensure your phone and TV are on the SAME network.", style=Pack(font_size=12)),
                self.qr_image_view,
                self.remote_status_label,
                toga.Button('Start Remote Server', on_press=self.start_server, style=Pack(padding=10))
            ],
            style=Pack(direction=COLUMN, alignment='center', padding=20)
        )

        self.container = toga.OptionContainer(
            content=[
                ("Dashboard", dashboard_box),
                ("Remote", remote_box),
                ("Settings", settings_box)
            ]
        )

        self.main_window.content = self.container
        self.main_window.show()

        # Check internet on startup (using async wrapper)
        self.add_background_task(self.check_internet_async)

        # Start server if QR supported
        if HAS_QR:
            self.start_server(None)

    # --- UI Safe Methods ---

    def apply_remote_credentials(self, username, password):
        """Called safely on main thread from the background server"""
        print(f"Applying credentials: {username}")
        self.input_user.value = username
        self.input_pass.value = password
        self.container.current_tab = 0  # Switch to Dashboard
        self.internet_status_label.text = "Received credentials from phone..."
        self.fill_login_form_and_submit(None)

    def check_internet_handler(self, widget):
        """Button handler wrapper for async function"""
        self.add_background_task(self.check_internet_async)

    async def check_internet_async(self, widget=None):
        """Async function to check internet without freezing UI"""
        # Updates here run on the main thread (safe)
        self.internet_status_label.text = "Checking connectivity..."
        self.internet_status_label.style.color = 'black'

        # Offload the blocking network call to a thread executor
        # We await it, so the UI loop keeps running while we wait
        loop = asyncio.get_running_loop()
        is_connected = await loop.run_in_executor(None, self._blocking_check)

        # Back on the main thread (safe)
        if is_connected:
            self.internet_status_label.text = "✅ Internet Connected"
            self.internet_status_label.style.color = 'green'
        else:
            self.internet_status_label.text = "❌ No Internet. Loading Login..."
            self.internet_status_label.style.color = 'red'
            current_url = self.input_url.value if self.input_url.value else "https://wifizone.actcorp.in"
            self.web_view.url = current_url

    def _blocking_check(self):
        """The actual blocking network call. Runs in a thread, NO UI updates allowed here."""
        try:
            urllib.request.urlopen('https://www.google.com', timeout=3)
            return True
        except:
            return False

    def fill_login_form_and_submit(self, widget):
        username = self.input_user.value
        password = self.input_pass.value
        js_code = f"""
            (function() {{
                var u = document.getElementById('username') || document.querySelector('input[name="username"]');
                var p = document.getElementById('password') || document.querySelector('input[name="password"]');
                var btn = document.getElementById('submit') || document.querySelector('button[type="submit"]') || document.querySelector('input[type="submit"]');
                if (u && p && btn) {{
                    u.value = '{username}';
                    p.value = '{password}';
                    u.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    p.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    setTimeout(function(){{ btn.click(); }}, 500);
                    return "Submitted";
                }}
                return "Elements not found";
            }})();
        """
        self.web_view.evaluate_javascript(js_code)

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def start_server(self, widget):
        if self.server_thread and self.server_thread.is_alive():
            self.remote_status_label.text = "Server already running."
            return

        ip = self.get_local_ip()
        port = 8000

        if HAS_QR:
            url = f"http://{ip}:{port}/?token={self.server_token}"
            qr = qrcode.QRCode(box_size=10, border=4)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            self.qr_image_view.image = toga.Image(data=buffer.getvalue())
            self.remote_status_label.text = f"Server running at {url}"
        else:
            self.remote_status_label.text = "QR Library missing."

        def run_server():
            # Use '0.0.0.0' so it's accessible from other devices
            httpd = HTTPServer(('0.0.0.0', port), RemoteHandler)
            httpd.app_instance = self
            httpd.token = self.server_token
            httpd.serve_forever()

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

    def open_system_date_time_settings(self, widget):
        try:
            os.system('adb shell am start -a android.settings.DATE_SETTINGS')
        except:
            pass

    def close_app(self, widget):
        sys.exit(0)

def main():
    return TvConnect()