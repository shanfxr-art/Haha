@echo off
rem Jarvis PC app launcher. master.js starts this; HUB_URL, PC_TOKEN, GEMINI_KEY (optional GROQ_KEY) come from the environment.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found & exit /b 1)
python -m pip install --quiet --disable-pip-version-check -r requirements.txt || (echo pip install failed & exit /b 1)
python -m playwright install chromium >nul 2>nul
python main.py
