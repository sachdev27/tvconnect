import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import os
from datetime import datetime
import urllib.request
import urllib.error
import sys  # Add sys to handle app exit

class WifiAutomationApp(toga.App):

    def startup(self):
        # Create the main window
        self.main_window = toga.MainWindow(title=self.formal_name)

        # Get the current system date
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Create labels and buttons
        self.internet_status_label = toga.Label("Internet Status: Unknown")
        self.date_label = toga.Label(f"Current Date: {current_date}")  # Label to show the current date

        # Create input fields for username, password, and URL with default values
        self.username_input = toga.TextInput(value="9921939226", placeholder="Enter Username")  # Prefill username
        self.password_input = toga.TextInput(value="7882", placeholder="Enter Password", style=Pack(padding_top=5))  # Prefill password
        self.url_input = toga.TextInput(value="https://wifizone.actcorp.in", placeholder="Enter URL", style=Pack(padding_top=5))  # Prefill URL

        open_date_settings_button = toga.Button('Open Date & Time Settings', on_press=self.open_system_date_time_settings)
        check_internet_button = toga.Button('Check Internet', on_press=self.check_internet)
        close_app_button = toga.Button('Close App', on_press=self.close_app)  # Button to close the app
        self.fill_form_button = toga.Button('Fill Login Form & Submit', on_press=self.fill_login_form_and_submit, enabled=True)

        # WebView to display the WiFi login page
        self.web_view = toga.WebView(style=Pack(flex=1))

        # Box layout: left = form, right = WebView (side-by-side)
        form_box = toga.Box(
            children=[
                self.date_label,
                self.internet_status_label,
                toga.Label("Username:"),
                self.username_input,
                toga.Label("Password:"),
                self.password_input,
                toga.Label("URL:"),
                self.url_input,
                open_date_settings_button,
                check_internet_button,
                self.fill_form_button,
                close_app_button,
            ],
            style=Pack(direction=COLUMN, padding=10, width=360)
        )

        web_box = toga.Box(
            children=[
                self.web_view,
            ],
            style=Pack(direction=COLUMN, flex=1, padding=10)
        )

        box = toga.Box(
            children=[
                form_box,
                web_box,
            ],
            style=Pack(direction=ROW, padding=10)
        )

        # Set content of the main window and show it
        self.main_window.content = box
        self.main_window.show()

    def open_system_date_time_settings(self, widget=None):
        try:
            os.system('adb shell am start -a android.settings.DATE_SETTINGS')  # Open system date settings
            print("Opened system date and time settings.")
        except Exception as e:
            print(f"Failed to open system date and time settings: {e}")

    def check_internet(self, widget=None):
        self.internet_status_label.text = "Checking internet connection..."
        try:
            # Check if internet is accessible via a simple GET request
            urllib.request.urlopen('https://www.google.com', timeout=5)
            self.internet_status_label.text = "Internet is connected!"
            print("Internet is connected!")
        except urllib.error.URLError as e:
            # Display error in the label if there is a connection issue
            error_message = f"Internet Error: {e.reason}"
            self.internet_status_label.text = error_message
            print(f"Failed to connect to the internet: {e}")
        except Exception as e:
            # General error handler
            error_message = f"Error: {e}"
            self.internet_status_label.text = error_message
            print(f"An error occurred: {e}")
            self.internet_status_label.text = "No Internet. Loading WiFi login page..."
            # Load the WiFi login page in case of no internet
        self.web_view.url = self.url_input.value if self.url_input.value else "https://wifizone.actcorp.in/web/hotel?param1=3920-3902"

    def fill_login_form_and_submit(self, widget=None):
        # Get the username, password, and URL from the input fields
        username = self.username_input.value if self.username_input.value else "9921939226"
        password = self.password_input.value if self.password_input.value else "5438"

        # JavaScript code to fill the form and submit it
        js_code = f"""
            setTimeout(function() {{
                var usernameField = document.getElementById('username');
                var passwordField = document.getElementById('password');
                var submitButton = document.getElementById('submit');

                if (usernameField && passwordField && submitButton) {{
                    usernameField.value = '{username}';  // Fill in username
                    passwordField.value = '{password}';  // Fill in password
                    submitButton.click();  // Submit the form
                }} else {{
                    console.log('Form elements not found.');
                }}
            }}, 1000);  // Wait 1 second before attempting to fill the form
        """
        # Execute the JavaScript to fill and submit the form
        self.web_view.evaluate_javascript(js_code, on_result=self.on_js_result)

    def on_js_result(self, result):
        print(f"JavaScript result: {result}")

    def close_app(self, widget=None):
        print("Closing the app.")
        sys.exit(0)  # Exit the application

def main():
    return WifiAutomationApp()

if __name__ == '__main__':
    main().main_loop()
