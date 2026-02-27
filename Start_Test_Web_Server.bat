@echo off
:: Set the port number
set PORT=8000

:: Change directory to where the script is located
cd /d "%~dp0"

echo [INFO] Opening default browser at http://localhost:%PORT%...
:: Start the browser first (non-blocking)
start http://localhost:%PORT%

echo [INFO] Starting Python Web Server on port %PORT%...
echo [HINT] Press Ctrl+C to stop the server.
:: Start the Python server
python -m http.server %PORT%

pause
