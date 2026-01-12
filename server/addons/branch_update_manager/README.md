# Branch Update Manager

Sistema automatizado para distribuir actualizaciones de módulos Odoo a múltiples sucursales offline.

## Descripción

Este módulo permite gestionar la distribución de actualizaciones de módulos Odoo desde un servidor central hacia múltiples sucursales que operan en modo offline o con conectividad intermitente.

### Características Principales

- Gestión centralizada de paquetes de actualización
- Registro y monitoreo de sucursales
- API REST para distribución segura
- Dashboard de control y monitoreo
- Soporte para actualizaciones incrementales
- Sistema de rollback automático

## Componentes

### Servidor Central (Este módulo)

- **Paquetes de Actualización**: Crear, empaquetar y publicar actualizaciones
- **Registro de Sucursales**: Gestionar todas las sucursales conectadas
- **Logs de Actualización**: Histórico de todas las actualizaciones aplicadas
- **Dashboard**: Vista general del estado del sistema

### Agente de Sucursal (Script independiente)

El script `update_agent_standalone.py` se ejecuta en cada sucursal:
- Verifica actualizaciones periódicamente
- Descarga y aplica paquetes automáticamente
- Crea backups antes de actualizar
- Realiza rollback en caso de fallas

## Instalación

### Servidor Central

```bash
# Copiar módulo a addons
cp -r branch_update_manager /ruta/addons/

# Instalar módulo
./odoo-bin -d mi_base_datos -i branch_update_manager --stop-after-init
```

### Sucursal (Windows)

```batch
REM Copiar scripts
copy scripts\update_agent_standalone.py C:\odoo-17\
copy scripts\config.example.json C:\odoo-17\config.json

REM Editar config.json con datos de la sucursal

REM Instalar como servicio
install_agent_service.bat C:\odoo-17\python\python.exe C:\odoo-17\config.json
```

## Configuración

### Servidor Central

1. Ir a Ajustes > Branch Updates
2. Seleccionar modo "Central Server (Cloud)"
3. Configurar opciones de almacenamiento y retención

### Sucursal

Crear archivo `config.json`:

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
    "update_window_end": 6
}
```

## API REST

### Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /api/updates/ping | Health check |
| POST | /api/branch/register | Registrar sucursal |
| POST | /api/updates/check | Verificar actualizaciones |
| POST | /api/updates/download | Descargar paquete |
| POST | /api/updates/confirm | Confirmar instalación |
| POST | /api/updates/status | Estado de actualizaciones |

## Flujo de Trabajo

1. Administrador crea paquete en servidor central
2. Selecciona módulos a incluir
3. Genera paquete (ZIP + checksums SHA256)
4. Publica el paquete
5. Sucursales verifican automáticamente
6. Descargan si hay actualizaciones pendientes
7. Verifican integridad del paquete
8. Crean backup de módulos actuales
9. Aplican la actualización
10. Reinician servicio Odoo
11. Confirman al servidor central

## Estructura del Módulo

```
branch_update_manager/
├── models/
│   ├── update_package.py      # Paquetes de actualización
│   ├── branch_registry.py     # Registro de sucursales
│   ├── update_log.py          # Logs de actualizaciones
│   ├── update_agent.py        # Agente interno
│   └── res_config_settings.py # Configuración
├── controllers/
│   ├── main.py                # Controlador web
│   └── api.py                 # API REST
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
│   └── ir_sequence.xml
└── scripts/
    ├── update_agent_standalone.py
    ├── config.example.json
    └── install_agent_service.bat
```

## Requisitos

- Odoo 17 Community Edition
- Python 3.10+
- PostgreSQL 12+

## Licencia

LGPL-3
