@echo off
REM Database backup script for Indique e Ganhe (Windows)
REM Usage: scripts\backup_db.bat [backup_dir]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "BACKUP_DIR=%~1"
if "%BACKUP_DIR%"=="" set "BACKUP_DIR=%PROJECT_DIR%\backups"

set "DB_PATH=%PROJECT_DIR%\backend\retro.db"
if not exist "%DB_PATH%" (
    echo Database not found: %DB_PATH%
    exit /b 1
)

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f "tokens=2 delims==." %%a in ('wmic os get localdatetime /value') do set "DT=%%a"
set "TIMESTAMP=%DT:~0,8%_%DT:~8,6%"

copy "%DB_PATH%" "%BACKUP_DIR%\retro_%TIMESTAMP%.db" >nul

echo Backup saved: %BACKUP_DIR%\retro_%TIMESTAMP%.db

REM Keep only last 30 backups
forfiles /p "%BACKUP_DIR%" /m retro_*.db /d -30 /c "cmd /c del @path" 2>nul
