# Odoo 17 Community - Guía de Instalación Local para Windows

## Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Requisitos del Sistema](#requisitos-del-sistema)
3. [Estructura del Proyecto](#estructura-del-proyecto)
4. [Instalación Paso a Paso](#instalación-paso-a-paso)
5. [Configuración](#configuración)
6. [Gestión de Addons Personalizados](#gestión-de-addons-personalizados)
7. [Ejecución del Sistema](#ejecución-del-sistema)
8. [Optimización para 8GB RAM](#optimización-para-8gb-ram)
9. [Solución de Problemas](#solución-de-problemas)
10. [Buenas Prácticas](#buenas-prácticas)

---

## Descripción General

Este proyecto contiene una instalación offline de **Odoo 17 Community Edition** preparada para Windows, incluyendo:

- Código fuente completo de Odoo 17.0 (versión final)
- 636 addons base incluidos
- Python 3.12 bundled
- PostgreSQL bundled (referencia)
- wkhtmltopdf para generación de PDFs

**Versión:** 17.0 Final
**Licencia:** LGPL-3

---

## Requisitos del Sistema

### Hardware Mínimo (8GB RAM)

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | 2 cores | 4 cores |
| Disco | 10 GB libres | SSD 20 GB |

### Distribución de Memoria (8GB)

```
┌─────────────────────────────────────┐
│ Windows OS        │ ~2.5 GB        │
│ PostgreSQL        │ ~1.5 GB        │
│ Odoo              │ ~2.0 GB        │
│ Navegador/Otros   │ ~2.0 GB        │
└─────────────────────────────────────┘
```

### Software Requerido

| Software | Versión | Incluido | Notas |
|----------|---------|----------|-------|
| Python | 3.10 - 3.12 | ✅ Sí (`python/`) | Python 3.12 bundled |
| PostgreSQL | 12 - 16 | ✅ Referencia | Instalar como servicio |
| wkhtmltopdf | 0.12.6 | ✅ Sí (`thirdparty/`) | Para reportes PDF |
| Visual C++ Redist | 2015-2022 | ✅ Sí (`vcredist/`) | Dependencia de Python |

---

## Estructura del Proyecto

```
odoo-17-community-offline_v1/
│
├── server/                          # Código fuente de Odoo
│   ├── odoo-bin                     # Punto de entrada (ejecutable)
│   ├── requirements.txt             # Dependencias Python
│   ├── odoo/                        # Core del framework
│   │   └── addons/                  # 636 addons base (NO MODIFICAR)
│   └── addons/                      # TUS ADDONS PERSONALIZADOS
│
├── python/                          # Python 3.12 bundled
│   ├── python.exe                   # Ejecutable Python
│   └── Scripts/                     # pip, etc.
│
├── PostgreSQL/                      # PostgreSQL bundled (referencia)
│   ├── bin/                         # Binarios (psql, pg_dump, etc.)
│   └── data/                        # Configuración base
│
├── thirdparty/
│   └── wkhtmltopdf.exe              # Generador de PDFs
│
├── nssm/                            # Para instalar como servicio Windows
│   ├── win32/
│   └── win64/
│
├── vcredist/                        # Visual C++ Redistributable
│
├── odoo.conf                        # Archivo de configuración
└── README.md                        # Este archivo
```

### Directorios Clave

| Directorio | Propósito | ¿Modificar? |
|------------|-----------|-------------|
| `server/odoo/addons/` | Addons base de Odoo | ❌ NUNCA |
| `server/addons/` | **TUS ADDONS** | ✅ SÍ |
| `python/` | Python incluido | ❌ No |
| `PostgreSQL/` | Referencia instalación | ❌ Usar instalador |

---

## Instalación Paso a Paso

### Paso 1: Instalar Visual C++ Redistributable

```
vcredist/vc_redist.x64.exe
```
Ejecutar e instalar. Requerido para que Python funcione correctamente.

### Paso 2: Instalar PostgreSQL

**Opción A: Usar instalador oficial (Recomendado)**
1. Descargar de https://www.postgresql.org/download/windows/
2. Instalar PostgreSQL 15 o 16
3. Durante instalación:
   - Puerto: `5432`
   - Usuario: `postgres`
   - Password: (recordar la contraseña)
4. Verificar que el servicio esté corriendo: `services.msc`

**Opción B: Usar PostgreSQL bundled**
```cmd
cd PostgreSQL\bin
initdb -D ..\data -U postgres -E UTF8
pg_ctl -D ..\data -l logfile start
```

### Paso 3: Crear Usuario de Base de Datos

Abrir CMD como administrador:

```cmd
cd "C:\Program Files\PostgreSQL\16\bin"
psql -U postgres

-- En la consola de PostgreSQL:
CREATE USER odoo WITH PASSWORD 'odoo' CREATEDB;
\q
```

### Paso 4: Instalar Dependencias Python

```cmd
cd odoo-17-community-offline_v1

:: Usar Python bundled
python\python.exe -m pip install --upgrade pip
python\python.exe -m pip install -r server\requirements.txt
```

> **Nota:** Si hay errores de compilación, instalar [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

### Paso 5: Configurar wkhtmltopdf

**Opción A: Agregar al PATH**
1. Copiar `thirdparty\wkhtmltopdf.exe` a `C:\Windows\System32\`

**Opción B: Agregar thirdparty al PATH de Windows**
1. Panel de Control → Sistema → Configuración avanzada
2. Variables de entorno → Path → Editar
3. Agregar: `C:\ruta\proyecto\thirdparty`

Verificar instalación:
```cmd
wkhtmltopdf --version
```

### Paso 6: Configurar odoo.conf

El archivo `odoo.conf` ya está configurado. Solo verificar la contraseña de PostgreSQL:

```ini
db_user = odoo
db_password = odoo    ; Cambiar si usaste otra contraseña
```

---

## Configuración

### Archivo odoo.conf - Parámetros Principales

```ini
[options]
; RUTAS - Usar barras normales (/) incluso en Windows
addons_path = ./server/odoo/addons,./server/addons

; BASE DE DATOS
db_host = localhost
db_port = 5432
db_user = odoo
db_password = odoo
db_maxconn = 32        ; Reducido para 8GB RAM

; SERVIDOR
http_port = 8069
http_interface = 127.0.0.1

; DESARROLLO
dev_mode = reload,xml  ; Evitar 'all' en 8GB RAM

; RENDIMIENTO
workers = 0            ; Obligatorio en Windows
max_cron_threads = 1   ; Reducir si hay problemas de memoria
```

### Parámetros que NO Aplican en Windows

| Parámetro | Razón |
|-----------|-------|
| `workers > 0` | Multiprocessing no soportado en Windows |
| `limit_memory_soft` | Solo funciona en Linux |
| `limit_memory_hard` | Solo funciona en Linux |

---

## Gestión de Addons Personalizados

### Ubicación

```
server/
└── addons/                    <-- AQUÍ VAN TUS ADDONS
    ├── mi_modulo_ventas/
    │   ├── __init__.py
    │   ├── __manifest__.py
    │   ├── models/
    │   ├── views/
    │   └── security/
    └── otro_modulo/
```

### Estructura Mínima de un Addon

```
mi_addon/
├── __init__.py              # from . import models
├── __manifest__.py          # Metadatos del módulo
├── models/
│   ├── __init__.py
│   └── mi_modelo.py
├── views/
│   └── mi_modelo_views.xml
└── security/
    └── ir.model.access.csv
```

### Ejemplo __manifest__.py

```python
{
    'name': 'Mi Addon Personalizado',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Descripción breve',
    'author': 'Tu Empresa',
    'license': 'LGPL-3',
    'depends': ['base', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/mi_modelo_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
```

### Agregar Rutas Adicionales de Addons

En `odoo.conf`:
```ini
addons_path = ./server/odoo/addons,./server/addons,C:/MisProyectos/addons_cliente
```

### Después de Agregar un Addon

1. Reiniciar Odoo
2. Activar modo desarrollador (Ajustes → Activar modo desarrollador)
3. Ir a Aplicaciones → Actualizar lista de aplicaciones
4. Buscar e instalar tu módulo

---

## Ejecución del Sistema

### Iniciar Odoo (CMD)

```cmd
cd C:\ruta\odoo-17-community-offline_v1
python\python.exe server\odoo-bin -c odoo.conf
```

### Iniciar Odoo (PowerShell)

```powershell
cd C:\ruta\odoo-17-community-offline_v1
.\python\python.exe server\odoo-bin -c odoo.conf
```

### Crear Archivo BAT para Inicio Rápido

Crear `iniciar_odoo.bat` en la raíz del proyecto:

```bat
@echo off
cd /d %~dp0
echo Iniciando Odoo 17...
echo.
echo Acceder a: http://localhost:8069
echo Presionar Ctrl+C para detener
echo.
python\python.exe server\odoo-bin -c odoo.conf
pause
```

### Acceso Web

Una vez iniciado, abrir en el navegador:
```
http://localhost:8069
```

Primera vez:
1. Crear base de datos
2. Email: admin
3. Password: (la que elijas)

### Comandos Útiles

```cmd
:: Instalar módulo específico
python\python.exe server\odoo-bin -c odoo.conf -d mi_bd -i mi_modulo --stop-after-init

:: Actualizar módulo
python\python.exe server\odoo-bin -c odoo.conf -d mi_bd -u mi_modulo --stop-after-init

:: Consola interactiva
python\python.exe server\odoo-bin shell -c odoo.conf -d mi_bd
```

### Instalar como Servicio de Windows

Usando NSSM (incluido en `nssm/`):

```cmd
:: Abrir CMD como Administrador
cd nssm\win64
nssm install OdooService

:: En la ventana de NSSM:
:: Path: C:\ruta\python\python.exe
:: Startup directory: C:\ruta\odoo-17-community-offline_v1
:: Arguments: server\odoo-bin -c odoo.conf

:: Iniciar servicio
nssm start OdooService
```

---

## Optimización para 8GB RAM

### Configuración Recomendada

```ini
; En odoo.conf
db_maxconn = 32          ; Menos conexiones = menos memoria
max_cron_threads = 1     ; Solo 1 hilo para cron
dev_mode = reload,xml    ; NO usar 'all'
workers = 0              ; Obligatorio en Windows
```

### Tips de Rendimiento

1. **Cerrar aplicaciones pesadas**
   - Chrome con muchas pestañas consume mucha RAM
   - Usar Edge o Firefox para Odoo

2. **Primera carga lenta**
   - Normal: Odoo compila assets CSS/JS
   - Siguientes cargas son más rápidas

3. **Si Odoo se pone lento**
   ```cmd
   :: Reiniciar Odoo para liberar memoria
   Ctrl+C
   python\python.exe server\odoo-bin -c odoo.conf
   ```

4. **Deshabilitar cron temporalmente**
   ```ini
   max_cron_threads = 0
   ```

5. **Evitar módulos pesados en desarrollo**
   - `website` consume más recursos
   - Instalar solo lo necesario

### Monitoreo de Memoria

Abrir Administrador de Tareas (Ctrl+Shift+Esc):
- Python: ~1-2 GB (Odoo)
- postgres: ~500 MB - 1 GB
- Total ideal: < 6 GB para dejar margen

---

## Solución de Problemas

### Error: "could not connect to server"

```
Causa: PostgreSQL no está corriendo

Solución:
1. Abrir services.msc
2. Buscar "postgresql-x64-XX"
3. Iniciar el servicio
```

### Error: "FATAL: password authentication failed"

```
Causa: Contraseña incorrecta en odoo.conf

Solución:
1. Verificar db_password en odoo.conf
2. Debe coincidir con la del usuario en PostgreSQL
```

### Error: "No module named 'xxx'"

```cmd
:: Reinstalar dependencias
python\python.exe -m pip install -r server\requirements.txt
```

### Error al generar PDF

```
Causa: wkhtmltopdf no encontrado

Solución:
1. Verificar: wkhtmltopdf --version
2. Si falla, copiar thirdparty\wkhtmltopdf.exe a C:\Windows\System32\
```

### Odoo muy lento

```
Causas posibles:
1. Primera carga (compilando assets) - esperar
2. Poca RAM disponible - cerrar otras aplicaciones
3. dev_mode = all - cambiar a dev_mode = reload

Verificar en odoo.conf:
dev_mode = reload,xml   ; NO usar 'all'
max_cron_threads = 1    ; O 0 para deshabilitar cron
```

### Limpiar Caché

```cmd
:: Eliminar archivos compilados
del /s /q server\odoo\*.pyc
del /s /q server\addons\*.pyc
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
```

### Error: "Port 8069 already in use"

```cmd
:: Encontrar proceso usando el puerto
netstat -ano | findstr :8069

:: Terminar proceso (reemplazar PID)
taskkill /PID <numero> /F
```

---

## Buenas Prácticas

### Desarrollo

1. **Nunca modificar addons base** (`server/odoo/addons/`)
   - Siempre heredar con `_inherit`

2. **Control de versiones**
   - Mantener addons personalizados en Git separado
   - Versionado: `17.0.X.Y.Z`

3. **Backups regulares**
   ```cmd
   "C:\Program Files\PostgreSQL\16\bin\pg_dump" -U odoo -Fc mi_bd > backup_%date%.dump
   ```

### Código

```python
# Heredar modelo existente
class SaleOrderExtend(models.Model):
    _inherit = 'sale.order'

    campo_nuevo = fields.Char(string='Mi Campo')

# Siempre definir permisos en security/ir.model.access.csv
```

### Antes de Producción

1. Cambiar `admin_passwd` en odoo.conf
2. Establecer `list_db = False`
3. Cambiar `log_level = warning`
4. Configurar backups automáticos

---

## Referencias

- [Documentación Oficial Odoo 17](https://www.odoo.com/documentation/17.0)
- [Tutorial de Desarrollo](https://www.odoo.com/documentation/17.0/developer/howtos.html)
- [PostgreSQL Windows](https://www.postgresql.org/download/windows/)

---

*Documentación para Odoo 17.0 Community - Windows con 8GB RAM*
