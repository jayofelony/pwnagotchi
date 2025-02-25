@echo off
setlocal

REM ---------------------------------------------------------------------------
REM A simple .bat script that handles two subcommands: "backup" and "restore"
REM USAGE:
REM   backup-restore.bat backup  [ -n HOST ] [ -u USER ] [ -o OUTPUT ]
REM   backup-restore.bat restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]
REM ---------------------------------------------------------------------------

set "LOGFILE=%~dp0BR_GPT.log"
echo [INFO] Script started at %DATE% %TIME% > "%LOGFILE%"

REM ---------------------------------------------------------------------------
REM Check for Arguments
if "%~1"=="" goto usage

set "SUBCOMMAND=%~1"
shift

REM Default Values
set "UNIT_HOSTNAME=10.0.0.2"
set "UNIT_USERNAME=pi"
set "OUTPUT="
set "BACKUP_FILE="

:parse_args
if "%~1"=="" goto done_args

if "%~1"=="-n" (
  set "UNIT_HOSTNAME=%~2"
  shift
  shift
  goto parse_args
)

if "%~1"=="-u" (
  set "UNIT_USERNAME=%~2"
  shift
  shift
  goto parse_args
)

if "%SUBCOMMAND%"=="backup" (
  if "%~1"=="-o" (
    set "OUTPUT=%~2"
    shift
    shift
    goto parse_args
  )
)

if "%SUBCOMMAND%"=="restore" (
  if "%~1"=="-b" (
    set "BACKUP_FILE=%~2"
    shift
    shift
    goto parse_args
  )
)

echo [ERROR] Unknown or invalid argument: %~1 >> "%LOGFILE%"
goto usage

:done_args

REM ---------------------------------------------------------------------------
REM Subcommand Routing
if "%SUBCOMMAND%"=="backup"  goto do_backup
if "%SUBCOMMAND%"=="restore" goto do_restore
goto usage

REM ===========================================================================
:do_backup
if "%OUTPUT%"=="" (
  set /a RAND=%random%
  set "OUTPUT=%UNIT_HOSTNAME%-backup-%RAND%.tgz"
)

echo [INFO] Checking connectivity to %UNIT_HOSTNAME% >> "%LOGFILE%"
ping -n 1 %UNIT_HOSTNAME% >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Device %UNIT_HOSTNAME% is unreachable. >> "%LOGFILE%"
  exit /b 1
)

echo [INFO] Backing up %UNIT_HOSTNAME% to %OUTPUT% ... >> "%LOGFILE%"
set "FILES_TO_BACKUP=/root/settings.yaml /root/client_secrets.json /root/.ssh /root/.api-report.json /root/.bashrc /root/.profile /home/pi/handshakes /root/peers /etc/pwnagotchi/ /usr/local/share/pwnagotchi/custom-plugins /etc/ssh/ /home/pi/.bashrc /home/pi/.profile /home/pi/.wpa_sec_uploads"

ssh %UNIT_USERNAME%@%UNIT_HOSTNAME% "sudo tar -cf - %FILES_TO_BACKUP% | gzip -9" > "%OUTPUT%" 2>> "%LOGFILE%"
if errorlevel 1 (
  echo [ERROR] Backup failed! >> "%LOGFILE%"
  exit /b 1
)

echo [INFO] Backup completed successfully: %OUTPUT% >> "%LOGFILE%"
exit /b 0

REM ===========================================================================
:do_restore
if "%BACKUP_FILE%"=="" (
  for /f "delims=" %%A in ('dir /b /a-d /O-D "%UNIT_HOSTNAME%-backup-*.tgz" 2^>nul') do (
    set "BACKUP_FILE=%%A"
    goto found_file
  )
  echo [ERROR] No backup file found. >> "%LOGFILE%"
  exit /b 1

:found_file
  echo [INFO] Found backup file: %BACKUP_FILE% >> "%LOGFILE%"
)

echo [INFO] Checking connectivity to %UNIT_HOSTNAME% >> "%LOGFILE%"
ping -n 1 %UNIT_HOSTNAME% > nul 2>&1
if errorlevel 1 (
  echo [ERROR] Device %UNIT_HOSTNAME% is unreachable. >> "%LOGFILE%"
  exit /b 1
)

echo [INFO] Copying backup file to remote device... >> "%LOGFILE%"
scp "%BACKUP_FILE%" %UNIT_USERNAME%@%UNIT_HOSTNAME%:/tmp/ 2>> "%LOGFILE%"
if errorlevel 1 (
  echo [ERROR] Failed to copy backup file. >> "%LOGFILE%"
  exit /b 1
)

echo [INFO] Restoring %BACKUP_FILE% on %UNIT_HOSTNAME% >> "%LOGFILE%"
ssh %UNIT_USERNAME%@%UNIT_HOSTNAME% "sudo tar xzvf /tmp/%BACKUP_FILE% -C /" 2>> "%LOGFILE%"
if errorlevel 1 (
  echo [ERROR] Restore failed! >> "%LOGFILE%"
  exit /b 1
)

echo [INFO] Restore completed successfully. >> "%LOGFILE%"
exit /b 0

REM ===========================================================================
:usage
echo Usage:
echo   BR_GPT.bat backup  [ -n HOST ] [ -u USER ] [ -o OUTPUT ]
echo   BR_GPT.bat restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]
exit /b 1
