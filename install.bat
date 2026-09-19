@echo off
rem Tạo venv và cài thư viện. Chạy một lần từ thư mục price-path.
cd /d "%~dp0"
if not exist venv (
  py -3.12 -m venv venv || python -m venv venv
)
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Xong. Tai lich su:  venv\Scripts\python -m scripts.fetch_history
echo Chay test:          venv\Scripts\python -m pytest -q
