# -*- coding: utf-8 -*-

import base64
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UpdateAgent(models.Model):
    """
    Agente de actualización que se ejecuta en cada sucursal.
    Gestiona la verificación, descarga y aplicación de actualizaciones.
    """
    _name = 'branch.update.agent'
    _description = 'Update Agent'

    @api.model
    def get_system_info(self):
        """Obtiene información del sistema local."""
        import odoo
        from odoo.tools import config

        try:
            # Obtener tamaño de base de datos
            self.env.cr.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()))
            """)
            db_size = self.env.cr.fetchone()[0]
        except Exception:
            db_size = 'Unknown'

        # Obtener módulos instalados
        installed_modules = {}
        modules = self.env['ir.module.module'].search([('state', '=', 'installed')])
        for mod in modules:
            installed_modules[mod.name] = mod.installed_version or '0.0.0'

        return {
            'odoo_version': odoo.release.version,
            'python_version': platform.python_version(),
            'os_info': f"{platform.system()} {platform.release()}",
            'hostname': platform.node(),
            'database_name': self.env.cr.dbname,
            'database_size': db_size,
            'installed_modules': installed_modules,
            'addons_path': config.get('addons_path', ''),
        }

    @api.model
    def check_for_updates(self):
        """
        Verifica si hay actualizaciones disponibles en el servidor central.
        Este método se ejecuta periódicamente via cron.
        """
        config = self.env['ir.config_parameter'].sudo()

        # Configuración
        cloud_url = config.get_param('branch_update.cloud_url')
        branch_uuid = config.get_param('branch_update.branch_uuid')
        api_key = config.get_param('branch_update.api_key')

        if not all([cloud_url, branch_uuid, api_key]):
            _logger.warning("Branch update agent not configured. Skipping check.")
            return False

        try:
            import requests

            # Preparar datos de la solicitud
            system_info = self.get_system_info()

            response = requests.post(
                f"{cloud_url}/api/updates/check",
                json={
                    'branch_uuid': branch_uuid,
                    'api_key': api_key,
                    'system_info': system_info,
                    'current_version': config.get_param('branch_update.current_version', '0.0.0'),
                },
                timeout=30,
                headers={'Content-Type': 'application/json'},
            )

            if response.status_code == 200:
                data = response.json()

                if data.get('updates'):
                    _logger.info(f"Found {len(data['updates'])} pending updates")

                    # Verificar si auto-update está habilitado
                    if config.get_param('branch_update.auto_apply', 'True') == 'True':
                        # Verificar ventana de actualización
                        if self._is_update_window():
                            for update in data['updates']:
                                self._process_update(update, cloud_url, branch_uuid, api_key)
                        else:
                            _logger.info("Outside update window. Updates will be applied later.")
                    else:
                        _logger.info("Auto-update disabled. Updates need manual application.")

                    return True
                else:
                    _logger.debug("No pending updates")
                    return False
            else:
                _logger.error(f"Update check failed: {response.status_code}")
                return False

        except requests.RequestException as e:
            _logger.warning(f"Could not connect to update server: {e}")
            return False
        except Exception as e:
            _logger.exception(f"Error checking for updates: {e}")
            return False

    def _is_update_window(self):
        """Verifica si estamos dentro de la ventana de actualización."""
        config = self.env['ir.config_parameter'].sudo()

        start_hour = float(config.get_param('branch_update.window_start', '2'))
        end_hour = float(config.get_param('branch_update.window_end', '6'))

        current_hour = datetime.now().hour + datetime.now().minute / 60

        if start_hour < end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Ventana que cruza medianoche
            return current_hour >= start_hour or current_hour < end_hour

    def _process_update(self, update_info, cloud_url, branch_uuid, api_key):
        """Procesa una actualización individual."""
        import requests

        package_ref = update_info.get('reference')
        _logger.info(f"Processing update: {package_ref}")

        try:
            # 1. Descargar el paquete
            _logger.info(f"Downloading package {package_ref}...")

            response = requests.post(
                f"{cloud_url}/api/updates/download",
                json={
                    'branch_uuid': branch_uuid,
                    'api_key': api_key,
                    'package_reference': package_ref,
                },
                timeout=300,  # 5 minutos para descargas grandes
                stream=True,
            )

            if response.status_code != 200:
                raise Exception(f"Download failed: {response.status_code}")

            # Guardar el archivo temporalmente
            temp_dir = tempfile.mkdtemp(prefix='odoo_update_')
            zip_path = os.path.join(temp_dir, f"{package_ref}.zip")

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 2. Verificar integridad
            _logger.info(f"Verifying checksum...")
            expected_checksum = update_info.get('checksum_sha256')

            with open(zip_path, 'rb') as f:
                actual_checksum = hashlib.sha256(f.read()).hexdigest()

            if expected_checksum and actual_checksum != expected_checksum:
                raise Exception(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")

            # 3. Crear backup
            if update_info.get('backup_required', True):
                _logger.info("Creating backup...")
                backup_path = self._create_backup(update_info.get('modules', []))
            else:
                backup_path = None

            # 4. Aplicar actualización
            _logger.info(f"Applying update...")
            applied_modules = self._apply_update(zip_path, temp_dir)

            # 5. Confirmar al servidor
            self._confirm_update(cloud_url, branch_uuid, api_key, package_ref, True, backup_path)

            # 6. Reiniciar si es necesario
            if update_info.get('requires_restart', True):
                _logger.info("Update complete. Scheduling restart...")
                self._schedule_restart()

            # Limpiar
            shutil.rmtree(temp_dir, ignore_errors=True)

            _logger.info(f"Update {package_ref} applied successfully")
            return True

        except Exception as e:
            _logger.exception(f"Error processing update {package_ref}: {e}")

            # Notificar fallo al servidor
            try:
                self._confirm_update(cloud_url, branch_uuid, api_key, package_ref, False, error=str(e))
            except Exception:
                pass

            return False

    def _create_backup(self, modules):
        """Crea un backup de los módulos antes de actualizar."""
        config = self.env['ir.config_parameter'].sudo()
        addons_path = config.get_param('addons_path', '').split(',')[0].strip()

        if not addons_path:
            import odoo
            addons_path = os.path.dirname(odoo.addons.__path__[0])

        backup_dir = os.path.join(tempfile.gettempdir(), 'odoo_backups')
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}.zip")

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

        _logger.info(f"Backup created at: {backup_path}")
        return backup_path

    def _apply_update(self, zip_path, temp_dir):
        """Aplica la actualización extrayendo los módulos."""
        config = self.env['ir.config_parameter'].sudo()
        addons_path = config.get_param('addons_path', '').split(',')[0].strip()

        if not addons_path:
            import odoo
            addons_path = os.path.dirname(odoo.addons.__path__[0])

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
            _logger.info("Executing pre-update script...")
            exec(manifest['pre_update_script'], {'env': self.env, 'logger': _logger})

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
                    _logger.info(f"Updated module: {module_name}")

        # Copiar archivos adicionales si existen
        additional_source = os.path.join(extract_dir, 'additional')
        if os.path.isdir(additional_source):
            for item in os.listdir(additional_source):
                source_path = os.path.join(additional_source, item)
                # Los archivos adicionales se copian al directorio de addons
                dest_path = os.path.join(addons_path, item)

                if os.path.isdir(source_path):
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)

        # Ejecutar script post-actualización si existe
        if manifest.get('post_update_script'):
            _logger.info("Executing post-update script...")
            exec(manifest['post_update_script'], {'env': self.env, 'logger': _logger})

        # Actualizar módulos en la base de datos
        if applied_modules:
            self._update_module_list()
            self._upgrade_modules(applied_modules)

        return applied_modules

    def _update_module_list(self):
        """Actualiza la lista de módulos en Odoo."""
        try:
            self.env['ir.module.module'].sudo().update_list()
            _logger.info("Module list updated")
        except Exception as e:
            _logger.warning(f"Could not update module list: {e}")

    def _upgrade_modules(self, module_names):
        """Actualiza los módulos especificados."""
        Module = self.env['ir.module.module'].sudo()

        for module_name in module_names:
            try:
                module = Module.search([('name', '=', module_name)], limit=1)
                if module and module.state == 'installed':
                    module.button_immediate_upgrade()
                    _logger.info(f"Module {module_name} upgraded")
                elif module and module.state == 'uninstalled':
                    _logger.info(f"Module {module_name} is not installed, skipping upgrade")
            except Exception as e:
                _logger.error(f"Error upgrading module {module_name}: {e}")

    def _confirm_update(self, cloud_url, branch_uuid, api_key, package_ref, success, backup_path=None, error=None):
        """Confirma la aplicación de la actualización al servidor."""
        import requests

        try:
            response = requests.post(
                f"{cloud_url}/api/updates/confirm",
                json={
                    'branch_uuid': branch_uuid,
                    'api_key': api_key,
                    'package_reference': package_ref,
                    'success': success,
                    'backup_path': backup_path,
                    'error': error,
                    'system_info': self.get_system_info(),
                },
                timeout=30,
            )

            if response.status_code != 200:
                _logger.warning(f"Could not confirm update: {response.status_code}")

        except Exception as e:
            _logger.warning(f"Could not confirm update: {e}")

    def _schedule_restart(self):
        """Programa un reinicio del servicio Odoo."""
        # En Windows, podemos usar NSSM para reiniciar el servicio
        if platform.system() == 'Windows':
            try:
                # Crear un archivo de señal para el watchdog
                signal_file = os.path.join(tempfile.gettempdir(), 'odoo_restart_signal')
                with open(signal_file, 'w') as f:
                    f.write(datetime.now().isoformat())

                _logger.info("Restart signal created. Watchdog will restart the service.")
            except Exception as e:
                _logger.error(f"Could not create restart signal: {e}")
        else:
            # En Linux, podemos usar systemctl
            try:
                subprocess.Popen(['systemctl', 'restart', 'odoo'], shell=False)
            except Exception as e:
                _logger.error(f"Could not restart service: {e}")

    @api.model
    def rollback_update(self, backup_path):
        """Ejecuta el rollback de una actualización."""
        if not os.path.exists(backup_path):
            raise UserError(_("Backup file not found: %s") % backup_path)

        config = self.env['ir.config_parameter'].sudo()
        addons_path = config.get_param('addons_path', '').split(',')[0].strip()

        if not addons_path:
            import odoo
            addons_path = os.path.dirname(odoo.addons.__path__[0])

        _logger.info(f"Starting rollback from: {backup_path}")

        try:
            with zipfile.ZipFile(backup_path, 'r') as zf:
                # Extraer a un directorio temporal
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
                        _logger.info(f"Restored module: {item}")

                # Limpiar
                shutil.rmtree(temp_dir)

            _logger.info("Rollback completed successfully")
            return True

        except Exception as e:
            _logger.exception(f"Rollback failed: {e}")
            raise UserError(_("Rollback failed: %s") % str(e))

    @api.model
    def register_branch(self, cloud_url, registration_code):
        """Registra esta sucursal en el servidor central."""
        import requests

        system_info = self.get_system_info()

        try:
            response = requests.post(
                f"{cloud_url}/api/branch/register",
                json={
                    'registration_code': registration_code,
                    'system_info': system_info,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()

                # Guardar configuración
                config = self.env['ir.config_parameter'].sudo()
                config.set_param('branch_update.cloud_url', cloud_url)
                config.set_param('branch_update.branch_uuid', data.get('branch_uuid'))
                config.set_param('branch_update.api_key', data.get('api_key'))
                config.set_param('branch_update.branch_name', data.get('branch_name'))

                return {
                    'success': True,
                    'message': _('Branch registered successfully!'),
                    'branch_name': data.get('branch_name'),
                }
            else:
                return {
                    'success': False,
                    'message': _('Registration failed: %s') % response.text,
                }

        except requests.RequestException as e:
            return {
                'success': False,
                'message': _('Could not connect to server: %s') % str(e),
            }
