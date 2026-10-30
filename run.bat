@echo off
echo ====================================
echo PopCentral POS - Python Setup
echo ====================================

python -m venv venv
call venv\Scripts\activate

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Starting POS Application...
python main.py
pause
