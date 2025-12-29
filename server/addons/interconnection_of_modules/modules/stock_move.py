# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    extra_products = fields.Float(
        string="Productos extras",
        default=0.0,
        help="Cantidad adicional de productos cuando la cantidad supera a la demanda"
    )

    available_stock_qty = fields.Float(
        string="Stock disponible",
        compute="_compute_stock_restriction_data",
        digits="Product Unit of Measure",
    )
    stock_restriction_enabled = fields.Boolean(
        compute="_compute_stock_restriction_data",
        string="Bloqueo por stock activo",
    )
    stock_blocked = fields.Boolean(
        compute="_compute_stock_restriction_data",
        string="Sin stock",
    )
    stock_restriction_message = fields.Char(
        compute="_compute_stock_restriction_data",
        string="Mensaje de stock",
    )

    def _prepare_new_lot_vals(self):
        vals = super()._prepare_new_lot_vals()
        if self.expiration_date:
            vals['expiration_date'] = self.expiration_date
        return vals

    @api.depends("product_id", "location_id", "product_uom_qty", "quantity")
    def _compute_stock_restriction_data(self):
        restriction_enabled = self._is_stock_restriction_enabled()
        for move in self:
            available_qty = move._get_available_stock() if restriction_enabled else 0.0
            is_applicable = restriction_enabled and move._is_stock_restriction_applicable()
            blocked = bool(is_applicable and available_qty <= 0)
            move.available_stock_qty = available_qty
            move.stock_restriction_enabled = restriction_enabled
            move.stock_blocked = blocked
            move.stock_restriction_message = move._get_stock_restriction_message(
                is_applicable=is_applicable,
                available_qty=available_qty,
                blocked=blocked,
            )

    def _get_stock_restriction_message(self, is_applicable, available_qty, blocked):
        self.ensure_one()
        if not is_applicable:
            return False
        if blocked:
            return _("Sin stock disponible. Ajusta existencias o desactiva el bloqueo en Ajustes.")

        precision = self._get_quantity_precision_rounding()
        qty_demand = self.product_uom_qty or 0.0
        qty_done = self.quantity or 0.0
        over_initial = float_compare(qty_demand, available_qty, precision_rounding=precision) > 0
        over_done = float_compare(qty_done, available_qty, precision_rounding=precision) > 0
        if over_initial or over_done:
            uom_name = self.product_uom.name or ""
            return _(
                "Cantidad solicitada supera el stock disponible (%(qty)s %(uom)s)."
            ) % {
                "qty": available_qty,
                "uom": uom_name,
            }
        return False

    def _get_quantity_precision_rounding(self):
        self.ensure_one()
        if self.product_uom and self.product_uom.rounding:
            return self.product_uom.rounding
        precision_digits = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        if precision_digits:
            return 10 ** (-precision_digits)
        return 0.0001

    @api.model
    def _is_stock_restriction_enabled(self):
        param_value = self.env["ir.config_parameter"].sudo().get_param(
            "interconnection_of_modules.block_transfer_without_stock"
        )
        return param_value in ("True", True, "1", 1)

    def _is_stock_restriction_applicable(self):
        self.ensure_one()
        # No aplicar la restricción para movimientos generados desde el POS
        if self.picking_id and self.picking_id.pos_order_id:
            return False
        # Ni para el tipo de picking configurado como POS en el almacén
        if (
            self.picking_type_id
            and self.picking_type_id == self.picking_type_id.warehouse_id.pos_type_id
        ):
            return False
        return (
            self.product_id
            and self.product_id.detailed_type == "product"
            and self.location_id
            and self.location_id.usage == "internal"
        )

    def _get_available_stock(self):
        self.ensure_one()
        if not self._is_stock_restriction_applicable():
            return 0.0
        product = self.product_id.with_context(location=self.location_id.id)
        return product.qty_available

    def _is_internal_transfer(self):
        """Verifica si el movimiento es parte de un traslado interno"""
        self.ensure_one()
        return (
            self.picking_type_id
            and self.picking_type_id.code == 'internal'
        )

    @api.constrains("product_id", "product_uom_qty", "quantity", "location_id", "location_dest_id")
    def _check_stock_restriction_quantities(self):
        for move in self:
            precision = move._get_quantity_precision_rounding()
            
            # Las siguientes validaciones solo aplican para traslados internos
            is_internal = move._is_internal_transfer()
            
            if is_internal:
                # Validación: No permitir demanda igual a 0
                if float_compare(move.product_uom_qty or 0.0, 0.0, precision_rounding=precision) <= 0:
                    raise ValidationError(
                        _("La demanda (product_uom_qty) debe ser mayor a 0 para %(product)s.")
                        % {
                            "product": move.product_id.display_name if move.product_id else _("el producto"),
                        }
                    )
                
                # Validación: Verificar que existan líneas en el picking
                if move.picking_id:
                    picking_moves = move.picking_id.move_ids.filtered(lambda m: m.id)
                    if not picking_moves:
                        raise ValidationError(
                            _("No se puede guardar la transferencia sin líneas de movimiento.")
                        )
                    
                # Validación: No permitir que location_id y location_dest_id sean iguales
                if (
                    move.location_id
                    and move.location_dest_id
                    and move.location_id == move.location_dest_id
                ):
                    raise ValidationError(
                        _(
                            "No se puede guardar la transferencia cuando la ubicación origen y destino son iguales (%(location)s)."
                        )
                        % {
                            "location": move.location_id.display_name,
                        }
                    )
            
            # Validación de stock (solo si la restricción está habilitada y es aplicable)
            if (
                not move._is_stock_restriction_enabled()
                or not move._is_stock_restriction_applicable()
            ):
                continue
            available_qty = move._get_available_stock()
            exceeds_initial = float_compare(
                move.product_uom_qty or 0.0, available_qty, precision_rounding=precision
            ) > 0
            exceeds_done = float_compare(
                move.quantity or 0.0, available_qty, precision_rounding=precision
            ) > 0
            if exceeds_initial or exceeds_done:
                raise ValidationError(
                    _(
                        "No hay stock suficiente para %(product)s en %(location)s. Disponible: %(qty)s %(uom)s."
                    )
                    % {
                        "product": move.product_id.display_name,
                        "location": move.location_id.display_name,
                        "qty": available_qty,
                        "uom": move.product_uom.display_name if move.product_uom else "",
                    }
                )
    # Warning al momento de editar la cantidad mediante UI, si la cantidad es mayor que la demanda
    @api.onchange("product_uom_qty", "quantity")
    def _onchange_quantity_done_limit(self):
        # Solo aplica en Recepciones (incoming)
        if self.picking_type_code == "incoming":
            if (self.quantity > self.product_uom_qty):
               self.extra_products = self.quantity - self.product_uom_qty  # Productos extras
               self.quantity = self.product_uom_qty                        # Igualar cantidad con la demanda
               return {
                   "warning": {
                       "title": "Advertencia",
                       "message": (
                           "La cantidad que se ingresó es mayor que la demanda, por lo que la cantidad adicional se asignó a productos extras"
                       ),
                   }
               }