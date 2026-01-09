import logging
import functools
from odoo import models, api, registry
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

_PATCH_APPLIED = False


def global_readonly_check(original_method):

    @functools.wraps(original_method)
    def wrapper(self, operation, raise_exception=True):
        # Si hay contexto para saltar, usar método original directamente
        if self.env.context.get('skip_global_readonly'):
            return original_method(self, operation, raise_exception)

        try:
            # PRIMERO verificar si debemos aplicar restricciones de solo lectura
            # Si NO debemos aplicar restricciones, usar método original directamente
            if not _should_apply_readonly_restriction(self, operation):
                return original_method(self, operation, raise_exception)

            # Si llegamos aquí, el usuario tiene el grupo de solo lectura
            # Verificar permisos base primero
            result = original_method(self, operation, raise_exception=False)

            if not result:
                if raise_exception:
                    raise AccessError(f"Acceso denegado para '{operation}' en '{self._name}'")
                return False

            # Aplicar restricción de solo lectura
            readonly_result = _check_readonly_permission(self, operation)

            if not readonly_result and raise_exception:
                if operation == 'read':
                    raise AccessError(f"Acceso de lectura denegado para '{self._name}'")
                else:
                    raise AccessError(
                        f"Usuario de solo lectura global. Operación '{operation}' "
                        f"no permitida en '{self._name}'"
                    )

            return readonly_result

        except AccessError:
            raise
        except Exception as e:
            _logger.error(f"Error en verificación readonly: {e}")
            return original_method(self, operation, raise_exception)

    return wrapper


def _should_apply_readonly_restriction(model, operation):

    try:
        user = model.env.user

        # Validaciones básicas
        if not user or not user.id or user._is_superuser():
            return False

        # Si se está usando sudo(), no aplicar restricciones
        # (el desarrollador está manejando permisos manualmente)
        if model.env.su:
            return False

        # Si el usuario es público (APIs públicas), no aplicar restricciones
        # Las APIs públicas manejan sus propios permisos con sudo()
        try:
            public_user = model.env.ref('base.public_user', raise_if_not_found=False)
            if public_user and user.id == public_user.id:
                return False
        except Exception:
            pass

        # Operaciones no estándar
        if operation not in ('read', 'write', 'create', 'unlink'):
            return False

        # Modelos del sistema excluidos
        system_models = {
            'res.users', 'res.partner', 'res.groups', 'res.company',
            'bus.presence', 'ir.sessions', 'mail.channel',
            'ir.model.access', 'ir.rule', 'ir.model', 'ir.model.fields',
            'ir.module.category', 'ir.model.data', 'mail.followers',
            'mail.message', 'ir.ui.menu', 'ir.ui.view',
            'ir.actions.act_window', 'ir.actions.server', 'ir.cron',
            'ir.sequence', 'ir.config_parameter', 'ir.attachment',
            'ir.translation', 'ir.logging', 'base_registry_signaling',
            'ir.qweb', 'ir.ui.view.custom', 'ir.http', 'res.lang',
            # Modelos de stock que pueden ser accedidos indirectamente
            'stock.picking', 'stock.move', 'stock.quant', 'stock.lot',
            'stock.warehouse', 'stock.location',
        }

        if model._name in system_models:
            return False

        # Verificar si el usuario tiene el grupo de solo lectura
        try:
            return user.with_context(skip_global_readonly=True).has_group(
                'global_read_only.global_read_only_group'
            )
        except Exception as group_error:
            _logger.warning(f"Error verificando grupo readonly: {group_error}")
            return False

    except Exception as e:
        _logger.warning(f"Error verificando restricción readonly: {e}")
        return False


def _check_readonly_permission(model, operation):

    try:
        readonly_group = model.env.ref('global_read_only.global_read_only_group', raise_if_not_found=False)

        if not readonly_group:
            _logger.warning("Grupo 'global_read_only.global_read_only_group' no encontrado")
            return operation == 'read'

        # Buscar regla de acceso específica usando el ID del grupo
        access_rule = model.env['ir.model.access'].with_context(
            skip_global_readonly=True
        ).sudo().search([
            ('model_id.model', '=', model._name),
            ('group_id', '=', readonly_group.id)
        ], limit=1)

        if access_rule:
            # Hay regla específica, verificar permiso
            permission_map = {
                'read': access_rule.perm_read,
                'write': access_rule.perm_write,
                'create': access_rule.perm_create,
                'unlink': access_rule.perm_unlink
            }
            return permission_map.get(operation, False)
        else:
            # Sin regla específica, solo permitir lectura
            return operation == 'read'

    except Exception as e:
        _logger.error(f"Error verificando permisos readonly: {e}")
        return operation == 'read'


def apply_global_readonly_patch():

    global _PATCH_APPLIED

    if _PATCH_APPLIED:
        return

    try:
        # Guardar método original
        original_check_access_rights = models.BaseModel.check_access_rights

        # Aplicar decorador
        models.BaseModel.check_access_rights = global_readonly_check(original_check_access_rights)

        _PATCH_APPLIED = True
        _logger.info("Parche de solo lectura global aplicado exitosamente")

    except Exception as e:
        _logger.error(f"Error aplicando parche de solo lectura global: {e}")


class GlobalReadOnlyConfig(models.TransientModel):
    # Modelo para testing y configuración del sistema de solo lectura.
    _name = 'global.readonly.config'
    _description = 'Configuración de Solo Lectura Global'

    @api.model
    def test_user_readonly_status(self):

        user = self.env.user

        try:
            has_group = user.with_context(skip_global_readonly=True).has_group(
                'global_read_only.global_read_only_group'
            )

            return {
                'user_id': user.id,
                'user_name': user.name,
                'has_readonly_group': has_group,
                'is_superuser': user._is_superuser(),
                'patch_applied': _PATCH_APPLIED
            }
        except Exception as e:
            return {'error': str(e)}

    @api.model
    def test_model_access(self, model_name, operation='read'):
        try:
            model = self.env[model_name]
            result = model.check_access_rights(operation, raise_exception=False)

            return {
                'model': model_name,
                'operation': operation,
                'access_granted': result,
                'patch_applied': _PATCH_APPLIED
            }
        except Exception as e:
            return {
                'model': model_name,
                'operation': operation,
                'error': str(e)
            }

    @api.model
    def disable_readonly_patch(self):
        # Desactiva temporalmente el parche (para debugging).
        global _PATCH_APPLIED
        _PATCH_APPLIED = False
        return {'status': 'Parche desactivado temporalmente'}

    @api.model
    def get_readonly_group_info(self):

        try:
            group = self.env.ref('global_read_only.global_read_only_group', raise_if_not_found=False)
            if group:
                users = group.users
                return {
                    'group_exists': True,
                    'group_id': group.id,
                    'group_name': group.name,
                    'user_count': len(users),
                    'users': [{'id': u.id, 'name': u.name, 'login': u.login} for u in users[:10]]  # Limitar a 10
                }
            else:
                return {
                    'group_exists': False,
                    'error': 'Grupo global_read_only.global_read_only_group no encontrado'
                }
        except Exception as e:
            return {'error': str(e)}

    @api.model
    def get_model_access_rules(self, model_name):

        try:
            group = self.env.ref('global_read_only.global_read_only_group', raise_if_not_found=False)
            if not group:
                return {'error': 'Grupo no encontrado'}

            access_rules = self.env['ir.model.access'].sudo().search([
                ('model_id.model', '=', model_name),
                ('group_id', '=', group.id)
            ])

            rules_info = []
            for rule in access_rules:
                rules_info.append({
                    'id': rule.id,
                    'name': rule.name,
                    'model': rule.model_id.model,
                    'group': rule.group_id.name,
                    'perm_read': rule.perm_read,
                    'perm_write': rule.perm_write,
                    'perm_create': rule.perm_create,
                    'perm_unlink': rule.perm_unlink,
                })

            return {
                'model': model_name,
                'rules': rules_info,
                'rules_count': len(rules_info)
            }

        except Exception as e:
            return {'model': model_name, 'error': str(e)}

    @api.model
    def create_test_access_rule(self, model_name, read=True, write=False, create=False, unlink=False):

        try:
            group = self.env.ref('global_read_only.global_read_only_group', raise_if_not_found=False)
            if not group:
                return {'error': 'Grupo no encontrado'}

            model_obj = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
            if not model_obj:
                return {'error': f'Modelo {model_name} no encontrado'}

            existing_rule = self.env['ir.model.access'].search([
                ('model_id', '=', model_obj.id),
                ('group_id', '=', group.id)
            ], limit=1)

            if existing_rule:
                # Actualizar regla existente
                existing_rule.write({
                    'perm_read': read,
                    'perm_write': write,
                    'perm_create': create,
                    'perm_unlink': unlink,
                })
                return {
                    'action': 'updated',
                    'rule_id': existing_rule.id,
                    'model': model_name
                }
            else:
                # Crear nueva regla
                new_rule = self.env['ir.model.access'].create({
                    'name': f'Global ReadOnly Access {model_obj.name}',
                    'model_id': model_obj.id,
                    'group_id': group.id,
                    'perm_read': read,
                    'perm_write': write,
                    'perm_create': create,
                    'perm_unlink': unlink,
                })
                return {
                    'action': 'created',
                    'rule_id': new_rule.id,
                    'model': model_name
                }

        except Exception as e:
            return {'model': model_name, 'error': str(e)}

    @api.model
    def enable_readonly_patch(self):
        # Reactiva el parche.
        apply_global_readonly_patch()
        return {'status': 'Parche reactivado', 'applied': _PATCH_APPLIED}


def post_load_hook():
    # Hook que se ejecuta después de cargar el módulo.
    apply_global_readonly_patch()

apply_global_readonly_patch()