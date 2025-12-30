# Branch Update Manager

Sistema automatizado para distribuir actualizaciones de módulos Odoo a múltiples sucursales offline.

## 🎯 Problema que Resuelve

Cuando tienes 250+ sucursales con Odoo POS en modo offline, actualizar manualmente los módulos en cada ubicación es:
- Lento y propenso a errores
- No escalable
- Difícil de rastrear qué versión tiene cada sucursal
- Imposible cuando no hay conexión constante

## ✅ Solución

Este sistema proporciona:

1. **Servidor Central (Cloud)**: Gestiona paquetes de actualización y monitorea sucursales
2. **Agente de Sucursal (Windows)**: Se ejecuta en cada POS y aplica actualizaciones automáticamente
3. **API REST**: Comunicación segura entre servidor y sucursales
4. **Dashboard**: Monitoreo en tiempo real del estado de todas las sucursales

## 📦 Componentes

### Servidor Central (`branch_update_manager` módulo Odoo)

- Gestión de paquetes de actualización
- Registro y monitoreo de sucursales
- API REST para distribución
- Dashboard de control

### Agente de Sucursal (`update_agent_standalone.py`)

- Script Python independiente
- Se ejecuta como servicio de Windows
- Verifica actualizaciones cada 5 minutos
- Descarga, aplica y confirma actualizaciones
- Rollback automático en caso de fallas

## 🚀 Instalación Rápida

### En el Servidor Central (AWS)

```bash
# 1. Copiar el módulo
cp -r branch_update_manager /opt/odoo/addons/

# 2. Instalar
./odoo-bin -d odoo_db -i branch_update_manager --stop-after-init

# 3. Configurar en Ajustes > Branch Updates > Settings
#    - Seleccionar modo: "Central Server (Cloud)"
```

### En Cada Sucursal (Windows)

```batch
REM 1. Copiar scripts al servidor local
copy scripts\update_agent_standalone.py C:\odoo-17\
copy scripts\config.example.json C:\odoo-17\config.json

REM 2. Editar config.json con los datos de la sucursal

REM 3. Instalar como servicio
install_agent_service.bat C:\odoo-17\python\python.exe C:\odoo-17\config.json
```

## 📋 Flujo de Trabajo

```
1. Administrador crea paquete en servidor central
                    ↓
2. Selecciona módulos a incluir
                    ↓
3. Genera paquete (ZIP + checksums)
                    ↓
4. Publica el paquete
                    ↓
5. Sucursales verifican automáticamente (cada 5 min)
                    ↓
6. Descargan el paquete si hay actualizaciones
                    ↓
7. Verifican integridad (SHA256)
                    ↓
8. Crean backup de módulos actuales
                    ↓
9. Aplican la actualización
                    ↓
10. Reinician el servicio Odoo
                    ↓
11. Confirman al servidor central
```

## ⚙️ Configuración del Agente

Crear `config.json`:

```json
{
    "cloud_url": "https://erp.empresa.com",
    "branch_uuid": "uuid-de-la-sucursal",
    "api_key": "api-key-de-la-sucursal",
    "addons_path": "C:\\odoo-17\\server\\addons",
    "odoo_service_name": "OdooService",
    "check_interval": 300,
    "auto_apply": true,
    "backup_before_update": true,
    "update_window_start": 2,
    "update_window_end": 6,
    "log_file": "C:\\odoo-17\\logs\\update_agent.log"
}
```

### Parámetros

| Parámetro | Descripción | Default |
|-----------|-------------|---------|
| `cloud_url` | URL del servidor central | Requerido |
| `branch_uuid` | UUID de la sucursal | Requerido |
| `api_key` | API Key de la sucursal | Requerido |
| `addons_path` | Ruta de addons de Odoo | Requerido |
| `check_interval` | Intervalo de verificación (segundos) | 300 |
| `auto_apply` | Aplicar actualizaciones automáticamente | true |
| `backup_before_update` | Crear backup antes de actualizar | true |
| `update_window_start` | Hora inicio ventana de actualización | 2 |
| `update_window_end` | Hora fin ventana de actualización | 6 |

## 🔌 API REST

### Endpoints Públicos

```
GET  /api/updates/ping           # Health check
POST /api/branch/register        # Registrar sucursal
```

### Endpoints Autenticados

```
POST /api/updates/check          # Verificar actualizaciones
POST /api/updates/download       # Descargar paquete
POST /api/updates/confirm        # Confirmar instalación
POST /api/updates/status         # Estado de actualizaciones
POST /api/updates/rollback       # Solicitar rollback
```

### Ejemplo: Verificar Actualizaciones

```python
import requests

response = requests.post(
    "https://erp.empresa.com/api/updates/check",
    json={
        "branch_uuid": "mi-uuid",
        "api_key": "mi-api-key",
        "system_info": {"odoo_version": "17.0"}
    }
)

data = response.json()
if data["result"]["updates"]:
    print(f"Hay {len(data['result']['updates'])} actualizaciones pendientes")
```

## 📊 Dashboard

El dashboard muestra:

- **Total de Sucursales**: Registradas en el sistema
- **Sucursales Activas**: Con estado "active"
- **Sucursales Online**: Conectadas en los últimos 10 minutos
- **Paquetes Pendientes**: Paquetes publicados sin instalar

### Vista Kanban de Sucursales

Cada tarjeta muestra:
- Estado (Online/Offline)
- Versión actual
- Actualizaciones pendientes
- Última conexión

## 🛡️ Seguridad

- **API Keys**: Cada sucursal tiene una clave única
- **Checksums**: SHA256 para verificar integridad de paquetes
- **HTTPS**: Recomendado para todas las comunicaciones
- **Ventana de Actualización**: Evita disrupciones en horario laboral

## 🔧 Solución de Problemas

### Sucursal no aparece Online

1. Verificar conectividad de red
2. Revisar que el servicio esté corriendo:
   ```batch
   sc query OdooUpdateAgent
   ```
3. Revisar logs:
   ```batch
   type C:\odoo-17\logs\update_agent.log
   ```

### Actualización Falla

1. El sistema hace rollback automáticamente
2. Revisar logs para identificar el error
3. Verificar espacio en disco
4. Verificar permisos de escritura

### Rollback Manual

```batch
REM 1. Detener servicios
net stop OdooService
net stop OdooUpdateAgent

REM 2. Restaurar backup
REM Los backups están en: %TEMP%\odoo_backups\

REM 3. Extraer el último backup en addons

REM 4. Reiniciar servicios
net start OdooService
net start OdooUpdateAgent
```

## 📁 Estructura del Módulo

```
branch_update_manager/
├── __manifest__.py           # Definición del módulo
├── __init__.py
├── models/
│   ├── update_package.py     # Paquetes de actualización
│   ├── branch_registry.py    # Registro de sucursales
│   ├── update_log.py         # Logs de actualizaciones
│   ├── update_agent.py       # Agente (versión Odoo)
│   └── res_config_settings.py
├── controllers/
│   ├── main.py               # Controlador web
│   └── api.py                # API REST
├── wizards/
│   └── branch_register_wizard.py
├── views/
│   ├── update_package_views.xml
│   ├── branch_registry_views.xml
│   ├── update_log_views.xml
│   ├── dashboard_views.xml
│   └── menu_views.xml
├── security/
│   ├── branch_update_security.xml
│   └── ir.model.access.csv
├── data/
│   ├── ir_cron.xml
│   ├── ir_sequence.xml
│   └── mail_template.xml
├── scripts/
│   ├── update_agent_standalone.py  # Agente para Windows
│   ├── config.example.json
│   └── install_agent_service.bat
└── static/
    └── description/
        └── index.html
```

## 📝 Notas Técnicas

### Compatibilidad

- Odoo 17 Community Edition
- Python 3.10+
- Windows 10/11 (sucursales)
- PostgreSQL 12-16

### Dependencias del Agente

```bash
pip install requests
```

### Requisitos de Red

- Puerto 443 (HTTPS) abierto hacia el servidor central
- Ancho de banda mínimo: 1 Mbps (para descargas de paquetes)

## 📄 Licencia

LGPL-3
