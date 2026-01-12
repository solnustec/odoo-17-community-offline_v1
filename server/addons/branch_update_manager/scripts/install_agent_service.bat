@echo off
REM ============================================================================
REM Branch Update Agent - Windows Service Installer
REM ============================================================================
REM Este script instala el agente de actualizaciones como un servicio de Windows
REM usando NSSM (Non-Sucking Service Manager)
REM
REM Requisitos:
REM   - NSSM instalado (incluido en nssm/ del paquete Odoo)
REM   - Python 3.10+ instalado
REM   - requests library instalada (pip install requests)
REM   - Archivo config.json configurado
REM
REM Uso:
REM   install_agent_service.bat [ruta_python] [ruta_config]
REM
REM Ejemplo:
REM   install_agent_service.bat C:\odoo-17\python\python.exe C:\odoo-17\config.json
REM ============================================================================

setlocal enabledelayedexpansion

REM Configuración por defecto
set SERVICE_NAME=OdooUpdateAgent
set SCRIPT_DIR=%~dp0
set PYTHON_PATH=%1
set CONFIG_PATH=%2

REM Verificar parámetros
if "%PYTHON_PATH%"=="" (
    echo [ERROR] Debe especificar la ruta de Python
    echo Uso: %~nx0 [ruta_python] [ruta_config]
    echo Ejemplo: %~nx0 C:\odoo-17\python\python.exe C:\odoo-17\config.json
    exit /b 1
)

if "%CONFIG_PATH%"=="" (
    echo [ERROR] Debe especificar la ruta del archivo de configuración
    echo Uso: %~nx0 [ruta_python] [ruta_config]
    exit /b 1
)

REM Verificar que Python existe
if not exist "%PYTHON_PATH%" (
    echo [ERROR] Python no encontrado en: %PYTHON_PATH%
    exit /b 1
)

REM Verificar que la configuración existe
if not exist "%CONFIG_PATH%" (
    echo [ERROR] Archivo de configuración no encontrado: %CONFIG_PATH%
    exit /b 1
)

REM Buscar NSSM
set NSSM_PATH=
if exist "%SCRIPT_DIR%..\..\..\..\nssm\win64\nssm.exe" (
    set NSSM_PATH=%SCRIPT_DIR%..\..\..\..\nssm\win64\nssm.exe
) else if exist "C:\nssm\nssm.exe" (
    set NSSM_PATH=C:\nssm\nssm.exe
) else (
    where nssm >nul 2>nul
    if !errorlevel! equ 0 (
        set NSSM_PATH=nssm
    ) else (
        echo [ERROR] NSSM no encontrado. Por favor instale NSSM primero.
        echo Descarga: https://nssm.cc/download
        exit /b 1
    )
)

echo ============================================================
echo Branch Update Agent - Instalador de Servicio
echo ============================================================
echo.
echo Servicio: %SERVICE_NAME%
echo Python: %PYTHON_PATH%
echo Config: %CONFIG_PATH%
echo NSSM: %NSSM_PATH%
echo.

REM Verificar si el servicio ya existe
sc query %SERVICE_NAME% >nul 2>nul
if %errorlevel% equ 0 (
    echo [AVISO] El servicio ya existe. Deteniendo...
    net stop %SERVICE_NAME% >nul 2>nul
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
)

echo [INFO] Instalando servicio...

REM Instalar el servicio
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" "%SCRIPT_DIR%update_agent_standalone.py" --config "%CONFIG_PATH%"

if %errorlevel% neq 0 (
    echo [ERROR] No se pudo instalar el servicio
    exit /b 1
)

REM Configurar el servicio
echo [INFO] Configurando servicio...

REM Descripción
"%NSSM_PATH%" set %SERVICE_NAME% Description "Odoo Branch Update Agent - Gestiona actualizaciones automáticas"

REM Directorio de trabajo
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"

REM Configurar reinicio automático
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 5000

REM Logs
set LOG_DIR=%SCRIPT_DIR%..\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%LOG_DIR%\update_agent_stdout.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%LOG_DIR%\update_agent_stderr.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdoutCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppStderrCreationDisposition 4
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760

REM Iniciar el servicio
echo [INFO] Iniciando servicio...
net start %SERVICE_NAME%

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo [OK] Servicio instalado e iniciado correctamente
    echo ============================================================
    echo.
    echo Para ver el estado: sc query %SERVICE_NAME%
    echo Para detener: net stop %SERVICE_NAME%
    echo Para iniciar: net start %SERVICE_NAME%
    echo Para desinstalar: nssm remove %SERVICE_NAME%
    echo.
) else (
    echo [ERROR] No se pudo iniciar el servicio
    echo Revise los logs en: %LOG_DIR%
    exit /b 1
)

endlocal
