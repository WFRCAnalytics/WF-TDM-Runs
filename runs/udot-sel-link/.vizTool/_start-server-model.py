# ----------------------------------------------------------------------------------------
# import libraries
# ----------------------------------------------------------------------------------------
import http.server
import threading

# import os <-- Removed
import time
import traceback
import webbrowser
from functools import partial
from pathlib import Path


# --- HELPER: Load Config File ---
def load_voyager_config(filepath):
    """
    Reads a Key=Value text file safely.
    Handles lines like: ModelDir_Py=D:\\Path\
    """
    config = {}
    # Pathlib read_text handles file opening/closing
    lines = filepath.read_text().splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith((";", "#")):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            # Strip whitespace and quotes just in case
            config[key.strip()] = value.strip().strip('"').strip("'")
    return config


# ----------------------------------------------------------------------------------------
# specify parent and scenario directorys
# ----------------------------------------------------------------------------------------
# create path to global variables input file
in_GlobalVar_txt = "py_Variables - ip_GlobalVars.txt"
path_in_GlobalVar_txt = Path.cwd() / "_Log" / in_GlobalVar_txt

if not path_in_GlobalVar_txt.exists():
    raise FileNotFoundError(f"Configuration file not found at: {path_in_GlobalVar_txt}")

# create variables from input file global variables
GlobalVars = load_voyager_config(path_in_GlobalVar_txt)

# set python variable from global variables
UsedZones = GlobalVars["UsedZones"]
ModelDir_Py = Path(GlobalVars["ModelDir_Py"])
ScenarioDir_Py = Path(GlobalVars["ScenarioDir_Py"])
vizToolDir_Py = Path(GlobalVars["vizToolDir_Py"])


# ----------------------------------------------------------------------------------------
# define function to print request data
# ----------------------------------------------------------------------------------------
# Custom request handler to print detailed information about requests
class VerboseHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        print(f"Handling GET request for {self.path}")
        super().do_GET()


# ----------------------------------------------------------------------------------------
# define functions to start the server and open the browser
# ----------------------------------------------------------------------------------------
# Start the server in a separate thread
def start_server():
    try:
        # Set the directory containing your HTML files
        base_directory = Path(vizToolDir_Py)
        print(base_directory.resolve())

        server_address = ("", 8080)
        handler_class = partial(VerboseHTTPRequestHandler, directory=str(base_directory))
        httpd = http.server.HTTPServer(server_address, handler_class)
        print("Starting server on port 8080...")
        httpd.serve_forever()
    except Exception:
        print("Error starting the server:")
        traceback.print_exc()


# Open in incognito mode after the server has started
def open_browser():
    url = "http://localhost:8080/index.html"
    webbrowser.open(url)


# ----------------------------------------------------------------------------------------
# run functions to start the server and open the browser
# ----------------------------------------------------------------------------------------
# Start the server and open the browser concurrently
server_thread = threading.Thread(target=start_server)
server_thread.start()

# Wait a moment for the server to start
time.sleep(2)

# Open the browser
browser_thread = threading.Thread(target=open_browser)
browser_thread.start()

# Wait for threads to finish
server_thread.join()
browser_thread.join()
