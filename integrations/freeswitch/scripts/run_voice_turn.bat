@echo off
setlocal EnableExtensions
set "DIR=%~dp0"
set "PY=python"
if exist "%DIR%python_path.txt" (
  for /f "usebackq delims=" %%P in ("%DIR%python_path.txt") do set "PY=%%P"
)
"%PY%" "%DIR%voice_turn_post.py" "%~1" "%~2"
exit /b %ERRORLEVEL%
