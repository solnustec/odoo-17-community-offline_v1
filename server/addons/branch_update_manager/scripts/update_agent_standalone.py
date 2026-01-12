#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Branch Update Agent - Standalone Version
=========================================

Este script se ejecuta de forma independiente en cada sucursal para:
1. Verificar actualizaciones disponibles en el servidor central
2. Descargar paquetes de actualización
3. Aplicar actualizaciones automáticamente
4. Realizar rollback en caso de fallas

Uso:
    python update_agent_standalone.py --config config.json

Configuración (config.json):
    {
        "cloud_url": "https://erp.empresa.com",
        "branch_uuid": "xxxxxxxx",
        "api_key": "xxxxxxxx",
        "check_interval": 300,
        "auto_apply": true,
        "backup_before_update": true,
        "addons_path": "C:\\odoo\\server\\addons",
        "odoo_service_name": "OdooService",
        "update_window_start": 2,
        "update_window_end": 6,
        "log_file": "update_agent.log"
    }

Para Windows, puede configurarse como un servicio usando NSSM:
    nssm install OdooUpdateAgent python.exe update_agent_standalone.py --config config.json
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger('UpdateAgent')


class UpdateAgent:
    """Agente de actualización standalone."""

    def __init__(self, config_path):
        """Inicializa el agente con la configuración."""
        self.config = self._load_config(config_path)
        self.running = True

        # Configurar logging a archivo si está especificado
        if self.config.get('log_file'):
            file_handler = logging.FileHandler(
                self.config['log_file'],
                encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(file_handler)

        # Registrar manejadores de señales
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Update Agent initialized")
        logger.info(f"Cloud URL: {self.config['cloud_url']}")
        logger.info(f"Branch UUID: {self.config.get('branch_uuid', 'Not set')}")

    def _load_config(self, config_path):
        """Carga la configuración desde un archivo JSON."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Valores por defecto
        defaults = {
            'check_interval': 300,  # 5 minutos
            'auto_apply': True,
            'backup_before_update': True,
            'update_window_start': 2,
            'update_window_end': 6,
            'retry_count': 3,
            'retry_delay': 60,
            'timeout': 30,
        }

        for key, value in defaults.items():
            if key not in config:
                config[key] = value

        # Validar campos requeridos
        required = ['cloud_url', 'branch_uuid', 'api_key', 'addons_path']
        missing = [f for f in required if not config.get(f)]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return config

    def _signal_handler(self, signum, frame):
        """Maneja señales de terminación."""
        logger.info("Received shutdown signal")
        self.running = False

    def get_system_info(self):
        """Obtiene información del sistema."""
        return {
            'python_version': platform.python_version(),
            'os_info': f"{platform.system()} {platform.release()}",
            'hostname': platform.node(),
            'platform': platform.platform(),
        }

    def is_update_window(self):
        """Verifica si estamos dentro de la ventana de actualización."""
        start_hour = self.config['update_window_start']
        end_hour = self.config['update_window_end']
        current_hour = datetime.now().hour + datetime.now().minute / 60

        if start_hour < end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Ventana que cruza medianoche
            return current_hour >= start_hour or current_hour < end_hour

    def check_for_updates(self):
        """Verifica si hay actualizaciones disponibles."""
        import requests

        try:
            response = requests.post(
                f"{self.config['cloud_url']}/api/updates/check",
                json={
                    'branch_uuid': self.config['branch_uuid'],
                    'api_key': self.config['api_key'],
                    'system_info': self.get_system_info(),
                    'current_version': self.config.get('current_version', '0.0.0'),
                },
                timeout=self.config['timeout'],
                headers={'Content-Type': 'application/json'},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('result', {}).get('updates'):
                    return data['result']['updates']
                return []
            else:
                logger.error(f"Update check failed: {response.status_code}")
                return []

        except requests.RequestException as e:
            logger.warning(f"Could not connect to server: {e}")
            return []

    def download_package(self, package_info):
        """Descarga un paquete de actualización."""
        import requests

        package_ref = package_info.get('reference')
        logger.info(f"Downloading package: {package_ref}")

        try:
            response = requests.post(
                f"{self.config['cloud_url']}/api/updates/download",
                json={
                    'branch_uuid': self.config['branch_uuid'],
                    'api_key': self.config['api_key'],
                    'package_reference': package_ref,
                },
                timeout=300,  # 5 minutos para descargas
                stream=True,
            )

            if response.status_code != 200:
                raise Exception(f"Download failed: {response.status_code}")

            # Guardar en directorio temporal
            temp_dir = tempfile.mkdtemp(prefix='odoo_update_')
            zip_path = os.path.join(temp_dir, f"{package_ref}.zip")

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        logger.info(f"Download progress: {progress:.1f}%")

            # Verificar checksum
            expected_checksum = response.headers.get('X-Checksum-SHA256')
            if expected_checksum:
                with open(zip_path, 'rb') as f:
                    actual_checksum = hashlib.sha256(f.read()).hexdigest()

                if actual_checksum != expected_checksum:
                    shutil.rmtree(temp_dir)
                    raise Exception(f"Checksum mismatch: expected {expected_checksum}")

            logger.info(f"Package downloaded successfully: {zip_path}")
            return zip_path, temp_dir

        except Exception as e:
            logger.error(f"Download error: {e}")
            raise

    def create_backup(self, modules):
        """Crea un backup de los módulos antes de actualizar."""
        backup_dir = os.path.join(tempfile.gettempdir(), 'odoo_backups')
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}.zip")

        addons_path = self.config['addons_path']

        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for module_info in modules:
                module_name = module_info.get('name')
                module_path = os.path.join(addons_path, module_name)

                if os.path.isdir(module_path):
                    for root, dirs, files in os.walk(module_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, addons_path)
                            zf.write(file_path, arcname)

        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def apply_update(self, zip_path, temp_dir):
        """Aplica la actualización."""
        addons_path = self.config['addons_path']

        # Extraer el paquete
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # Leer manifest
        manifest_path = os.path.join(extract_dir, 'manifest.json')
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        applied_modules = []

        # Ejecutar script pre-actualización si existe
        if manifest.get('pre_update_script'):
            logger.info("Executing pre-update script...")
            try:
                exec(manifest['pre_update_script'], {'logger': logger})
            except Exception as e:
                logger.error(f"Pre-update script failed: {e}")
                raise

        # Copiar módulos
        addons_source = os.path.join(extract_dir, 'addons')
        if os.path.isdir(addons_source):
            for module_name in os.listdir(addons_source):
                source_path = os.path.join(addons_source, module_name)
                dest_path = os.path.join(addons_path, module_name)

                if os.path.isdir(source_path):
                    # Eliminar módulo existente
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)

                    # Copiar nuevo módulo
                    shutil.copytree(source_path, dest_path)
                    applied_modules.append(module_name)
                    logger.info(f"Updated module: {module_name}")

        # Copiar archivos adicionales si existen
        additional_source = os.path.join(extract_dir, 'additional')
        if os.path.isdir(additional_source):
            for item in os.listdir(additional_source):
                source_path = os.path.join(additional_source, item)
                dest_path = os.path.join(addons_path, item)

                if os.path.isdir(source_path):
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)

        # Ejecutar script post-actualización si existe
        if manifest.get('post_update_script'):
            logger.info("Executing post-update script...")
            try:
                exec(manifest['post_update_script'], {'logger': logger})
            except Exception as e:
                logger.warning(f"Post-update script failed: {e}")

        return applied_modules, manifest

    def confirm_update(self, package_ref, success, backup_path=None, error=None):
        """Confirma la actualización al servidor."""
        import requests

        try:
            response = requests.post(
                f"{self.config['cloud_url']}/api/updates/confirm",
                json={
                    'branch_uuid': self.config['branch_uuid'],
                    'api_key': self.config['api_key'],
                    'package_reference': package_ref,
                    'success': success,
                    'backup_path': backup_path,
                    'error': error,
                    'system_info': self.get_system_info(),
                },
                timeout=self.config['timeout'],
            )

            if response.status_code == 200:
                logger.info(f"Update confirmation sent: {package_ref}")
            else:
                logger.warning(f"Could not confirm update: {response.status_code}")

        except Exception as e:
            logger.warning(f"Could not confirm update: {e}")

    def restart_odoo_service(self):
        """Reinicia el servicio de Odoo."""
        service_name = self.config.get('odoo_service_name', 'OdooService')

        if platform.system() == 'Windows':
            try:
                # Usar NSSM o sc para reiniciar el servicio
                logger.info(f"Restarting service: {service_name}")
                subprocess.run(
                    ['net', 'stop', service_name],
                    capture_output=True,
                    timeout=60
                )
                time.sleep(2)
                subprocess.run(
                    ['net', 'start', service_name],
                    capture_output=True,
                    timeout=60
                )
                logger.info("Service restarted successfully")
            except Exception as e:
                logger.error(f"Could not restart service: {e}")
        else:
            try:
                subprocess.run(
                    ['systemctl', 'restart', 'odoo'],
                    capture_output=True,
                    timeout=60
                )
            except Exception as e:
                logger.error(f"Could not restart service: {e}")

    def process_update(self, package_info):
        """Procesa una actualización completa."""
        package_ref = package_info.get('reference')
        logger.info(f"Processing update: {package_ref}")

        zip_path = None
        temp_dir = None
        backup_path = None

        try:
            # 1. Descargar
            zip_path, temp_dir = self.download_package(package_info)

            # 2. Crear backup si está configurado
            if self.config['backup_before_update']:
                modules = package_info.get('modules', [])
                backup_path = self.create_backup(modules)

            # 3. Aplicar actualización
            applied_modules, manifest = self.apply_update(zip_path, temp_dir)

            # 4. Confirmar
            self.confirm_update(package_ref, True, backup_path)

            # 5. Actualizar versión actual
            self.config['current_version'] = package_info.get('version', '0.0.0')

            # 6. Reiniciar si es necesario
            if manifest.get('requires_restart', True):
                logger.info("Scheduling service restart...")
                # Esperar un poco para asegurar que todo esté en orden
                time.sleep(5)
                self.restart_odoo_service()

            logger.info(f"Update {package_ref} completed successfully")
            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            self.confirm_update(package_ref, False, error=str(e))

            # Intentar rollback si hay backup
            if backup_path and os.path.exists(backup_path):
                logger.info("Attempting rollback...")
                try:
                    self.rollback(backup_path)
                    logger.info("Rollback completed")
                except Exception as re:
                    logger.error(f"Rollback also failed: {re}")

            return False

        finally:
            # Limpiar archivos temporales
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def rollback(self, backup_path):
        """Ejecuta un rollback desde un backup."""
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        addons_path = self.config['addons_path']

        with zipfile.ZipFile(backup_path, 'r') as zf:
            # Extraer a directorio temporal
            temp_dir = tempfile.mkdtemp(prefix='odoo_rollback_')
            zf.extractall(temp_dir)

            # Copiar módulos de vuelta
            for item in os.listdir(temp_dir):
                source_path = os.path.join(temp_dir, item)
                dest_path = os.path.join(addons_path, item)

                if os.path.isdir(source_path):
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(source_path, dest_path)
                    logger.info(f"Restored module: {item}")

            # Limpiar
            shutil.rmtree(temp_dir)

        logger.info("Rollback completed successfully")

    def run(self):
        """Ejecuta el agente en un loop continuo."""
        logger.info("Update Agent started")
        logger.info(f"Check interval: {self.config['check_interval']} seconds")
        logger.info(f"Update window: {self.config['update_window_start']}:00 - {self.config['update_window_end']}:00")

        while self.running:
            try:
                # Verificar actualizaciones
                updates = self.check_for_updates()

                if updates:
                    logger.info(f"Found {len(updates)} pending updates")

                    # Verificar si auto-update está habilitado
                    if self.config['auto_apply']:
                        # Verificar ventana de actualización
                        if self.is_update_window():
                            for update in updates:
                                if not self.running:
                                    break
                                self.process_update(update)
                        else:
                            logger.info("Outside update window. Updates will be applied later.")
                    else:
                        logger.info("Auto-update disabled. Updates need manual application.")
                else:
                    logger.debug("No pending updates")

            except Exception as e:
                logger.error(f"Error in update cycle: {e}")

            # Esperar antes de la siguiente verificación
            for _ in range(int(self.config['check_interval'])):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Update Agent stopped")


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description='Branch Update Agent - Standalone Version'
    )
    parser.add_argument(
        '--config', '-c',
        required=True,
        help='Path to configuration file (JSON)'
    )
    parser.add_argument(
        '--check-once',
        action='store_true',
        help='Check for updates once and exit'
    )
    parser.add_argument(
        '--force-update',
        action='store_true',
        help='Apply updates regardless of update window'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='Branch Update Agent 1.0.0'
    )

    args = parser.parse_args()

    try:
        agent = UpdateAgent(args.config)

        if args.force_update:
            agent.config['update_window_start'] = 0
            agent.config['update_window_end'] = 24

        if args.check_once:
            updates = agent.check_for_updates()
            if updates:
                print(f"Found {len(updates)} pending updates:")
                for u in updates:
                    print(f"  - {u.get('reference')}: {u.get('name')} v{u.get('version')}")
                if agent.config['auto_apply']:
                    for update in updates:
                        agent.process_update(update)
            else:
                print("No pending updates")
        else:
            agent.run()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
