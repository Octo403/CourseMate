@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing: .venv\Scripts\python.exe
    pause
    exit /b 1
)
echo AnotherMe study demo: http://127.0.0.1:8501
echo Keep this window open while using the demo. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -u "scripts\start_study_demo.py"
if errorlevel 1 pause
