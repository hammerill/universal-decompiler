@echo off
rem universal-decompiler CLI launcher for cmd.exe / PowerShell (bin/ud is the bash one).
if defined UD_NO_UV goto nouv
where uv >NUL 2>NUL || goto nouv
uv run --quiet --project "%~dp0.." python -m ud %*
exit /b %ERRORLEVEL%
:nouv
set "PYTHONPATH=%~dp0..;%PYTHONPATH%"
python -m ud %*
exit /b %ERRORLEVEL%
