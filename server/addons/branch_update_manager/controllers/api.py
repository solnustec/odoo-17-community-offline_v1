# -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime

from odoo import http, fields, _
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def json_response(data, status=200):
    """Helper para crear respuestas JSON."""
    return Response(
        json.dumps(data, default=str),
        status=status,
        content_type='application/json'
    )


def authenticate_branch(func):
    """Decorador para autenticar solicitudes de sucursales."""
    def wrapper(*args, **kwargs):
        try:
            data = request.get_json_data() if request.httprequest.data else {}
        except Exception:
            data = {}

        branch_uuid = data.get('branch_uuid')
        api_key = data.get('api_key')

        if not branch_uuid or not api_key:
            return json_response({'error': 'Missing authentication'}, 401)

        branch = request.env['branch.registry'].sudo().search([
            ('branch_uuid', '=', branch_uuid),
            ('state', '=', 'active'),
        ], limit=1)

        if not branch or not branch.verify_api_key(api_key):
            return json_response({'error': 'Invalid credentials'}, 401)

        # Actualizar información de conexión
        ip_address = request.httprequest.remote_addr
        branch.update_connection_info(ip_address=ip_address, system_info=data.get('system_info'))

        # Añadir branch al contexto
        request.branch = branch

        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


class BranchUpdateAPI(http.Controller):
    """API REST para distribución de actualizaciones."""

    # ==================== Endpoints Públicos ====================

    @http.route('/api/updates/ping', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def ping(self, **kwargs):
        """Health check endpoint."""
        return json_response({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
        })

    @http.route('/api/branch/register', type='json', auth='public', methods=['POST'], csrf=False)
    def register_branch(self, **kwargs):
        """
        Registra una nueva sucursal.
        Requiere un código de registro válido.
        """
        try:
            data = request.get_json_data()
        except Exception:
            return {'error': 'Invalid JSON'}

        registration_code = data.get('registration_code')
        system_info = data.get('system_info', {})

        if not registration_code:
            return {'error': 'Registration code required'}

        # Buscar sucursal pendiente con este código
        branch = request.env['branch.registry'].sudo().search([
            ('code', '=', registration_code),
            ('state', '=', 'pending'),
        ], limit=1)

        if not branch:
            return {'error': 'Invalid or already used registration code'}

        # Activar sucursal y actualizar información
        branch.write({
            'state': 'active',
            'odoo_version': system_info.get('odoo_version'),
            'python_version': system_info.get('python_version'),
            'os_info': system_info.get('os_info'),
            'hostname': system_info.get('hostname'),
            'database_name': system_info.get('database_name'),
            'database_size': system_info.get('database_size'),
            'last_connection': fields.Datetime.now(),
            'last_ip_address': request.httprequest.remote_addr,
        })

        if system_info.get('installed_modules'):
            branch.installed_modules = json.dumps(system_info['installed_modules'])

        return {
            'success': True,
            'branch_uuid': branch.branch_uuid,
            'api_key': branch.api_key,
            'branch_name': branch.name,
            'message': 'Branch registered successfully',
        }

    # ==================== Endpoints Autenticados ====================

    @http.route('/api/updates/check', type='json', auth='public', methods=['POST'], csrf=False)
    @authenticate_branch
    def check_updates(self, **kwargs):
        """
        Verifica si hay actualizaciones disponibles para una sucursal.
        Retorna lista de paquetes pendientes.
        """
        branch = request.branch

        try:
            data = request.get_json_data()
        except Exception:
            data = {}

        system_info = data.get('system_info', {})

        # Actualizar información del sistema
        if system_info:
            branch.update_connection_info(system_info=system_info)

        # Obtener paquetes pendientes
        pending_packages = branch.get_pending_packages()

        return {
            'success': True,
            'branch_name': branch.name,
            'updates': pending_packages,
            'update_count': len(pending_packages),
        }

    @http.route('/api/updates/download', type='http', auth='public', methods=['POST'], csrf=False)
    def download_package(self, **kwargs):
        """
        Descarga un paquete de actualización.
        Retorna el archivo ZIP.
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception:
            return json_response({'error': 'Invalid JSON'}, 400)

        branch_uuid = data.get('branch_uuid')
        api_key = data.get('api_key')
        package_reference = data.get('package_reference')

        if not all([branch_uuid, api_key, package_reference]):
            return json_response({'error': 'Missing parameters'}, 400)

        # Autenticar
        branch = request.env['branch.registry'].sudo().search([
            ('branch_uuid', '=', branch_uuid),
            ('state', '=', 'active'),
        ], limit=1)

        if not branch or not branch.verify_api_key(api_key):
            return json_response({'error': 'Invalid credentials'}, 401)

        # Buscar paquete
        package = request.env['branch.update.package'].sudo().search([
            ('reference', '=', package_reference),
            ('state', '=', 'published'),
        ], limit=1)

        if not package:
            return json_response({'error': 'Package not found'}, 404)

        if not package.package_file:
            return json_response({'error': 'Package file not available'}, 404)

        # Verificar que la sucursal puede recibir este paquete
        if not package.all_branches and branch not in package.target_branch_ids:
            return json_response({'error': 'Package not available for this branch'}, 403)

        # Crear log de descarga
        request.env['branch.update.log'].sudo().create({
            'branch_id': branch.id,
            'package_id': package.id,
            'state': 'downloading',
            'action': 'download',
            'start_time': fields.Datetime.now(),
            'ip_address': request.httprequest.remote_addr,
        })

        # Incrementar contador de descargas
        package.increment_download_count()

        # Retornar archivo
        file_content = base64.b64decode(package.package_file)

        headers = [
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', f'attachment; filename="{package.package_file_name}"'),
            ('Content-Length', str(len(file_content))),
            ('X-Checksum-SHA256', package.checksum_sha256),
            ('X-Checksum-MD5', package.checksum_md5),
        ]

        return Response(file_content, headers=headers)

    @http.route('/api/updates/confirm', type='json', auth='public', methods=['POST'], csrf=False)
    @authenticate_branch
    def confirm_update(self, **kwargs):
        """
        Confirma la aplicación de una actualización.
        """
        branch = request.branch

        try:
            data = request.get_json_data()
        except Exception:
            return {'error': 'Invalid JSON'}

        package_reference = data.get('package_reference')
        success = data.get('success', False)
        error = data.get('error')
        backup_path = data.get('backup_path')
        system_info = data.get('system_info', {})

        if not package_reference:
            return {'error': 'Missing package_reference'}

        # Buscar paquete
        package = request.env['branch.update.package'].sudo().search([
            ('reference', '=', package_reference),
        ], limit=1)

        if not package:
            return {'error': 'Package not found'}

        # Buscar o crear log
        log = request.env['branch.update.log'].sudo().search([
            ('branch_id', '=', branch.id),
            ('package_id', '=', package.id),
            ('state', 'in', ['pending', 'downloading', 'downloaded', 'applying']),
        ], limit=1, order='create_date desc')

        if not log:
            log = request.env['branch.update.log'].sudo().create({
                'branch_id': branch.id,
                'package_id': package.id,
                'action': 'install',
                'start_time': fields.Datetime.now(),
                'ip_address': request.httprequest.remote_addr,
            })

        # Actualizar log
        if success:
            log.mark_success(
                applied_modules=system_info.get('installed_modules'),
                rollback_path=backup_path
            )
        else:
            log.mark_failed(error_message=error)

        # Actualizar información del sistema
        if system_info:
            branch.update_connection_info(system_info=system_info)

        return {
            'success': True,
            'log_id': log.id,
            'message': 'Update confirmation received',
        }

    @http.route('/api/updates/status', type='json', auth='public', methods=['POST'], csrf=False)
    @authenticate_branch
    def update_status(self, **kwargs):
        """
        Retorna el estado de las actualizaciones para una sucursal.
        """
        branch = request.branch

        # Obtener logs recientes
        logs = request.env['branch.update.log'].sudo().search([
            ('branch_id', '=', branch.id),
        ], limit=20, order='create_date desc')

        return {
            'success': True,
            'branch_name': branch.name,
            'current_version': branch.current_version,
            'last_update_date': branch.last_update_date.isoformat() if branch.last_update_date else None,
            'last_update_status': branch.last_update_status,
            'pending_updates': branch.pending_update_count,
            'recent_logs': [{
                'package_reference': log.package_id.reference,
                'package_name': log.package_id.name,
                'state': log.state,
                'action': log.action,
                'start_time': log.start_time.isoformat() if log.start_time else None,
                'end_time': log.end_time.isoformat() if log.end_time else None,
                'success': log.success,
                'error_message': log.error_message,
            } for log in logs],
        }

    @http.route('/api/updates/rollback', type='json', auth='public', methods=['POST'], csrf=False)
    @authenticate_branch
    def request_rollback(self, **kwargs):
        """
        Solicita un rollback a una versión anterior.
        """
        branch = request.branch

        try:
            data = request.get_json_data()
        except Exception:
            return {'error': 'Invalid JSON'}

        package_reference = data.get('package_reference')

        if not package_reference:
            return {'error': 'Missing package_reference'}

        # Buscar log con backup disponible
        log = request.env['branch.update.log'].sudo().search([
            ('branch_id', '=', branch.id),
            ('package_id.reference', '=', package_reference),
            ('rollback_available', '=', True),
            ('state', '=', 'success'),
        ], limit=1, order='create_date desc')

        if not log:
            return {'error': 'No rollback available for this package'}

        # Crear log de rollback
        rollback_log = request.env['branch.update.log'].sudo().create({
            'branch_id': branch.id,
            'package_id': log.package_id.id,
            'action': 'rollback',
            'state': 'pending',
            'metadata': json.dumps({
                'original_log_id': log.id,
                'backup_path': log.rollback_package_path,
            }),
        })

        return {
            'success': True,
            'rollback_log_id': rollback_log.id,
            'backup_path': log.rollback_package_path,
            'message': 'Rollback scheduled',
        }

    # ==================== Endpoints de Administración ====================

    @http.route('/api/admin/branches', type='json', auth='user', methods=['GET'], csrf=False)
    def list_branches(self, **kwargs):
        """Lista todas las sucursales (requiere autenticación de usuario)."""
        branches = request.env['branch.registry'].search([])

        return {
            'success': True,
            'count': len(branches),
            'branches': [{
                'id': b.id,
                'name': b.name,
                'code': b.code,
                'state': b.state,
                'is_online': b.is_online,
                'last_connection': b.last_connection.isoformat() if b.last_connection else None,
                'current_version': b.current_version,
                'pending_updates': b.pending_update_count,
            } for b in branches],
        }

    @http.route('/api/admin/packages', type='json', auth='user', methods=['GET'], csrf=False)
    def list_packages(self, **kwargs):
        """Lista todos los paquetes (requiere autenticación de usuario)."""
        packages = request.env['branch.update.package'].search([])

        return {
            'success': True,
            'count': len(packages),
            'packages': [{
                'id': p.id,
                'reference': p.reference,
                'name': p.name,
                'version': p.version,
                'state': p.state,
                'update_type': p.update_type,
                'priority': p.priority,
                'publish_date': p.publish_date.isoformat() if p.publish_date else None,
                'download_count': p.download_count,
                'install_count': p.install_count,
                'failure_count': p.failure_count,
                'pending_count': p.pending_count,
            } for p in packages],
        }

    @http.route('/api/admin/statistics', type='json', auth='user', methods=['GET'], csrf=False)
    def get_statistics(self, **kwargs):
        """Retorna estadísticas generales."""
        BranchRegistry = request.env['branch.registry']
        UpdatePackage = request.env['branch.update.package']
        UpdateLog = request.env['branch.update.log']

        total_branches = BranchRegistry.search_count([])
        active_branches = BranchRegistry.search_count([('state', '=', 'active')])
        online_branches = BranchRegistry.search_count([('is_online', '=', True)])

        total_packages = UpdatePackage.search_count([])
        published_packages = UpdatePackage.search_count([('state', '=', 'published')])

        log_stats = UpdateLog.get_statistics(days=30)

        return {
            'success': True,
            'branches': {
                'total': total_branches,
                'active': active_branches,
                'online': online_branches,
            },
            'packages': {
                'total': total_packages,
                'published': published_packages,
            },
            'updates_30_days': log_stats,
        }
