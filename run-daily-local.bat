@echo off
rem Chạy job sau phiên trên máy này (ghi file, không push). Thêm tham số: --dry-run | --force | (bỏ --no-push để push thật)
cd /d "%~dp0"
if "%~1"=="" (
  venv\Scripts\python -m job.run_daily --no-push
) else (
  venv\Scripts\python -m job.run_daily %*
)
