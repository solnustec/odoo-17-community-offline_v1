@echo off
setlocal enabledelayedexpansion

:: ============================================
:: Odoo 17 - Script de Inicio Optimizado
:: ============================================

set "ODOO_ROOT=C:\Users\sanan\Documents\Github\odoo-17-community-offline_v1"
set "PYTHON_EXE=%ODOO_ROOT%\python\python.exe"
set "ODOO_BIN=%ODOO_ROOT%\server\odoo-bin"
set "ODOO_CONF=%ODOO_ROOT%\server\odoo.conf"
set "MAX_RESTARTS=5"
set "RESTART_DELAY=10"
set RESTART_COUNT=0

title Odoo 17 Community - Servidor Local

:START
cls
echo ============================================
echo   Odoo 17 Community - Servidor Local
echo ============================================
echo.
echo Fecha/Hora: %date% %time%
echo Intentos de reinicio: %RESTART_COUNT%/%MAX_RESTARTS%
echo.
echo Iniciando servidor Odoo...
echo.

:: Ejecutar Odoo
"%PYTHON_EXE%" "%ODOO_BIN%" -c "%ODOO_CONF%"

:: Si llegamos aqui, Odoo se detuvo
set ODOO_EXIT_CODE=%ERRORLEVEL%
echo.
echo ============================================
echo Odoo se ha detenido (Codigo: %ODOO_EXIT_CODE%)
echo ============================================

:: Incrementar contador de reinicios
set /a RESTART_COUNT+=1

:: Verificar si excedemos el maximo de reinicios
if %RESTART_COUNT% GEQ %MAX_RESTARTS% (
    echo.
    echo ERROR: Se alcanzo el limite de %MAX_RESTARTS% reinicios.
    echo Revise los logs en: %ODOO_ROOT%\server\odoo.log
    echo.
    pause
    exit /b 1
)

:: Esperar antes de reiniciar
echo.
echo Reiniciando en %RESTART_DELAY% segundos...
echo Presione Ctrl+C para cancelar.
timeout /t %RESTART_DELAY% /nobreak >nul

goto START
