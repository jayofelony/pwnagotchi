@echo off
setlocal

REM ---------------------------------------------------------------------------
REM A simple .bat script that handles two subcommands: "backup" and "restore"
REM USAGE:
REM   backup-restore.bat backup  [ -n HOST ] [ -u USER ] [ -o OUTPUT ]
REM   backup-restore.bat restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]
REM ---------------------------------------------------------------------------

set "SCRIPTNAME=%~0"

REM ---------------------------------------------------------------------------
REM If no arguments, show usage
if "%~1"=="" goto usage

REM First argument is the subcommand: "backup" or "restore"
set "SUBCOMMAND=%~1"
shift

REM Default values
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

echo "Unknown or invalid argument: %~1"
goto usage

:done_args

REM ---------------------------------------------------------------------------
REM Subcommand routing
if "%SUBCOMMAND%"=="backup"  goto do_backup
if "%SUBCOMMAND%"=="restore" goto do_restore
goto usage

REM ===========================================================================
:do_backup
REM If OUTPUT not specified, generate a name like HOST-backup-RANDOM.tgz
if "%OUTPUT%"=="" (
  set /a RAND=%random% 
  set "OUTPUT=%UNIT_HOSTNAME%-backup-%RAND%.tgz"
)

echo @ Checking connectivity to %UNIT_HOSTNAME% ...
ping -n 1 %UNIT_HOSTNAME% >nul 2>&1
if errorlevel 1 (
  echo @ unit %UNIT_HOSTNAME% can't be reached.
  exit /b 1
)

echo @ Backing up %UNIT_HOSTNAME% to %OUTPUT% ...

REM List of files to back up from the remote device:
set "FILES_TO_BACKUP=/root/settings.yaml /root/client_secrets.json /root/.ssh /root/.api-report.json /root/.bashrc /root/.profile /home/pi/handshakes /root/peers /etc/pwnagotchi/ /usr/local/share/pwnagotchi/custom-plugins /etc/ssh/ /home/pi/.bashrc /home/pi/.profile /home/pi/.wpa_sec_uploads"

REM ---------------------------------------------------------------------------
REM We'll have the REMOTE do the tar + gzip (since Windows cmd lacks gzip)
REM so we capture the compressed stream directly into %OUTPUT%
REM ---------------------------------------------------------------------------
ssh %UNIT_USERNAME%@%UNIT_HOSTNAME% "sudo tar -cf - %FILES_TO_BACKUP% | gzip -9" > "%OUTPUT%"
if errorlevel 1 (
  echo @ Backup failed
  exit /b 1
)

echo @ Backup finished. Archive: %OUTPUT%
exit /b 0

REM ===========================================================================
:do_restore
if "%BACKUP_FILE%"=="" (
  REM If user didn't specify -b, try to find the latest *.tgz with the hostname prefix
  for /f "delims=" %%A in ('dir /b /a-d /O-D "%UNIT_HOSTNAME%-backup-*.tgz" 2^>nul') do (
    set "BACKUP_FILE=%%A"
    goto found_file
  )
  echo @ Can't find backup file. Please specify one with '-b'.
  exit /b 1

:found_file
  echo @ Found backup file: %BACKUP_FILE%
  set /p CONTINUE="@ Continue restoring this file? (y/n) "
  if /i "%CONTINUE%"=="y" (
    echo (continuing...)
  ) else (
    exit /b 1
  )
)

echo @ Checking connectivity to %UNIT_HOSTNAME% ...
ping -n 1 %UNIT_HOSTNAME% > nul 2>&1
if errorlevel 1 (
  echo @ unit %UNIT_HOSTNAME% can't be reached.
  exit /b 1
)

echo @ Restoring %BACKUP_FILE% to %UNIT_HOSTNAME% ...

REM We'll send the local file contents over SSH; the remote will do tar xzv
type "%BACKUP_FILE%" | ssh %UNIT_USERNAME%@%UNIT_HOSTNAME% "tar xzv -C /"
if errorlevel 1 (
  echo @ Restore failed.
  exit /b 1
)

echo @ Restore finished.
exit /b 0

REM ===========================================================================
:usage
echo Usage:
echo   %SCRIPTNAME% backup  [ -n HOST ] [ -u USER ] [ -o OUTPUT ]
echo   %SCRIPTNAME% restore [ -n HOST ] [ -u USER ] [ -b BACKUP_FILE ]
echo.
echo Subcommands:
echo   backup      Backup files from the remote device.
echo   restore     Restore files to the remote device.
echo.
echo Common Options:
echo   -n HOST     Hostname or IP of remote device (default: 10.0.0.2)
echo   -u USER     Username for SSH (default: pi)
echo.
echo Options for 'backup':
echo   -o OUTPUT   Path/name of the output archive (default: HOST-backup-RANDOM.tgz)
echo.
echo Options for 'restore':
echo   -b BACKUP   Path to the local backup archive to restore.
echo.
echo Examples:
echo   %SCRIPTNAME% backup
echo   %SCRIPTNAME% backup -n 10.0.0.2 -u pi -o my-backup.tgz
echo   %SCRIPTNAME% restore -b my-backup.tgz
echo.
exit /b 1
