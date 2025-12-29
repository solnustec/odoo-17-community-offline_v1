from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    app_mobile_warehouse = fields.Boolean(
        string="Habilitar Bodega para la aplicación Móvil",
        default=False,
        tracking=True,
        help="Esta bodega se usará para las operaciones de inventario de la app móvil"
    )

    city_id = fields.Many2one(
        'res.country.state',
        string="Ciudad",
        tracking=True,
        domain="[('country_id', '=', 63)]"
    )

    @api.constrains('app_mobile_warehouse', 'city_id')
    def _check_city_required_for_mobile_warehouse(self):
        for warehouse in self:
            if warehouse.app_mobile_warehouse and not warehouse.city_id:
                raise ValidationError(
                    _("Debe seleccionar una ciudad cuando habilita la bodega para la aplicación móvil."))


    @api.constrains('app_mobile_warehouse', 'city_id')
    def _check_one_mobile_warehouse_per_city(self):
        for warehouse in self:
            if warehouse.app_mobile_warehouse and warehouse.city_id:
                other_mobile_warehouses = self.search([
                    ('id', '!=', warehouse.id),
                    ('city_id', '=', warehouse.city_id.id),
                    ('app_mobile_warehouse', '=', True)
                ])

                if other_mobile_warehouses:
                    city_name = self.city_id.name
                    self.city_id = False

                    raise ValidationError(_(
                        "Ya existe una bodega habilitada para la aplicación móvil en la ciudad %s: %s. "
                        "Solo puede haber una bodega móvil activa por ciudad."
                    ) % (city_name,
                         other_mobile_warehouses[0].name))

    @api.onchange('app_mobile_warehouse', 'city_id')
    def _onchange_mobile_city(self):
        if self.app_mobile_warehouse and self.city_id:
            other_mobile_warehouses = self.search([
                ('id', '!=', self._origin.id),
                ('city_id', '=', self.city_id.id),
                ('app_mobile_warehouse', '=', True)
            ])

            if other_mobile_warehouses:
                warning_msg = _(
                    "Ya existe una bodega habilitada para la aplicación móvil en la ciudad %s: %s. "
                    "Si continúa, se generará un error de validación."
                ) % (self.city_id.name, other_mobile_warehouses[0].name)
                self.city_id = False

                return {
                    'warning': {
                        'title': _("Advertencia"),
                        'message': warning_msg,
                    }
                }
        return {}
