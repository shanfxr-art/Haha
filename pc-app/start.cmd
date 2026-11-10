@echo off
rem Jarvis PC app launcher. master.js starts this; HUB_URL and PC_TOKEN come from the environment.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found & exit /b 1)
python -m pip install --quiet --disable-pip-version-check -r requirements.txt || (echo pip install failed & exit /b 1)
python main.py
