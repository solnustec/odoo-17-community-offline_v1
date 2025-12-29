# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ChangeSalespersonWizard(models.TransientModel):
    _name = 'change.salesperson.wizard'
    _description = 'Wizard para cambiar vendedor de orden de venta'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        readonly=True
    )
    current_user_id = fields.Many2one(
        'res.users',
        string='Vendedor Actual',
        readonly=True
    )
    new_user_id = fields.Many2one(
        'res.users',
        string='Nuevo Vendedor',
        required=True,
        domain="[('groups_id.name', 'ilike', 'Vendedor'), ('active', '=', True)]"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            # Usar sudo para leer la orden (el usuario puede no tener acceso después del cambio)
            order = self.env['sale.order'].sudo().browse(active_id)
            if order.exists():
                res['sale_order_id'] = order.id
                res['current_user_id'] = order.user_id.id
        return res

    def action_change_salesperson(self):
        """Ejecuta el cambio de vendedor usando sudo()"""
        self.ensure_one()

        if not self.new_user_id:
            raise UserError(_('Debe seleccionar un nuevo vendedor'))

        if self.new_user_id.id == self.current_user_id.id:
            raise UserError(_('El nuevo vendedor debe ser diferente al actual'))

        # Verificar permisos del usuario actual
        current_user = self.env.user
        has_permission = (
            current_user.has_group('pragtech_whatsapp_base.group_change_salesperson') or
            current_user.has_group('sales_team.group_sale_salesman') or
            current_user.has_group('sales_team.group_sale_manager')
        )

        if not has_permission:
            raise UserError(_('No tiene permisos para cambiar el vendedor'))

        # Verificar que el nuevo usuario tiene permisos de venta
        sales_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        if sales_group and sales_group not in self.new_user_id.groups_id:
            raise UserError(_('El usuario seleccionado no tiene permisos de vendedor'))

        try:
            # Usar sudo() para cambiar el vendedor (evita problemas de record rules)
            order = self.sale_order_id.sudo()
            old_user_name = order.user_id.name
            order.write({'user_id': self.new_user_id.id})

            _logger.info(
                f"Usuario {current_user.name} cambió vendedor de orden {order.name}: "
                f"{old_user_name} -> {self.new_user_id.name}"
            )

            # Mensaje en el chatter de la orden
            order.message_post(
                body=_(f"Vendedor cambiado de <b>{old_user_name}</b> a <b>{self.new_user_id.name}</b> "
                       f"por {current_user.name}"),
                message_type='notification'
            )

            # Redirigir al listado de órdenes para evitar error de acceso
            # (el usuario ya no tiene acceso a esta orden después del cambio)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Órdenes de Venta'),
                'res_model': 'sale.order',
                'view_mode': 'tree,form',
                'target': 'current',
                'context': {'search_default_my_quotation': 1},
            }

        except Exception as e:
            _logger.error(f"Error al cambiar vendedor: {str(e)}")
            raise UserError(_('Error al cambiar vendedor: %s') % str(e))
