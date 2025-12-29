# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools import logging
from datetime import datetime, timedelta
import pytz  # Librería para manejar zonas horarias en Odoo

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    discount = fields.Float(string="Dto. (%)", compute="_compute_discount", store=True)

    free_stock = fields.Char(
        string="Producto gratis", compute="_compute_discount", store=False
    )

    pos_stock_available = fields.Float(
        string="Stock en POS", compute="_compute_pos_stock", store=False
    )
    pos_barcode = fields.Char(
        string="POS Barcode", compute="_compute_pos_barcode", store=True
    )

    pos_stock_incoming = fields.Float(
        string="Stock por recibir", compute="_compute_pos_stock_incoming", store=False
    )

    @api.depends(
        "multi_barcode_ids.product_multi_barcode",
        "product_tmpl_id.template_multi_barcode_ids.product_multi_barcode",
    )
    def _compute_pos_barcode(self):
        for product in self:
            # Primero intenta en la variante
            barcodes = product.multi_barcode_ids
            # Si no hay, toma los de la plantilla
            if not barcodes:
                barcodes = product.product_tmpl_id.template_multi_barcode_ids
            product.pos_barcode = barcodes[0].product_multi_barcode if barcodes else ""

    @api.depends("stock_quant_ids.quantity", "stock_quant_ids.reserved_quantity")
    def _compute_pos_stock(self):
        """Calcula el stock disponible del producto en la ubicación específica del POS
        (cantidad total menos cantidad reservada)"""
        pos_session = self.env["pos.session"].search([], limit=1, order="id desc")
        if (
            not pos_session
            or not pos_session.config_id
            or not pos_session.config_id.picking_type_id
        ):
            for product in self:
                product.pos_stock_available = 0
            return

        stock_location_id = (
            pos_session.config_id.picking_type_id.default_location_src_id.id
        )
        if not stock_location_id:
            for product in self:
                product.pos_stock_available = 0
            return

        for product in self:
            stock_quant = (
                self.env["stock.quant"]
                .sudo()
                .search(
                    [
                        ("product_id", "=", product.id),
                        ("location_id", "=", stock_location_id),
                    ],
                    limit=1,
                )
            )
            # Stock disponible = cantidad total - cantidad reservada
            if stock_quant:
                product.pos_stock_available = stock_quant.quantity - stock_quant.reserved_quantity
            else:
                product.pos_stock_available = 0

    @api.model
    def pos_stock_new(self, session_id=False, product_id=False):
        """Calcula el stock disponible del producto en la ubicación específica del POS
        (cantidad total menos cantidad reservada)"""
        pos_session = self.env["pos.session"].browse(session_id)
        if (
                not pos_session
                or not pos_session.config_id
                or not pos_session.config_id.picking_type_id
        ):
            return 0

        stock_location_id = (
            pos_session.config_id.picking_type_id.default_location_src_id.id
        )
        if not stock_location_id:
            return 0

        product = self.browse(product_id)
        stock_quant = (
            self.env["stock.quant"]
            .sudo()
            .search(
                [
                    ("product_id", "=", product.id),
                    ("location_id", "=", stock_location_id),
                ],
                limit=1,
            )
        )
        # Stock disponible = cantidad total - cantidad reservada
        if stock_quant:
            return stock_quant.quantity - stock_quant.reserved_quantity
        return 0

    def _compute_pos_stock_incoming(self):
        """Calcula el stock pendiente por recibir en la ubicación del POS"""
        pos_session = self.env["pos.session"].search([], limit=1, order="id desc")
        if (
            not pos_session
            or not pos_session.config_id
            or not pos_session.config_id.picking_type_id
        ):
            for product in self:
                product.pos_stock_incoming = 0
            return

        stock_location_id = (
            pos_session.config_id.picking_type_id.default_location_src_id.id
        )
        if not stock_location_id:
            for product in self:
                product.pos_stock_incoming = 0
            return

        for product in self:
            # Buscar movimientos de stock pendientes hacia esta ubicación
            pending_moves = (
                self.env["stock.move"]
                .sudo()
                .search(
                    [
                        ("product_id", "=", product.id),
                        ("location_dest_id", "=", stock_location_id),
                        ("state", "in", ["draft", "waiting", "confirmed", "assigned"]),
                    ]
                )
            )
            product.pos_stock_incoming = sum(pending_moves.mapped("product_uom_qty"))

    @api.model
    def pos_stock_incoming_new(self, session_id=False, product_id=False):
        """Calcula el stock pendiente por recibir para un producto en la ubicación del POS"""
        pos_session = self.env["pos.session"].browse(session_id)
        if (
            not pos_session
            or not pos_session.config_id
            or not pos_session.config_id.picking_type_id
        ):
            return 0

        stock_location_id = (
            pos_session.config_id.picking_type_id.default_location_src_id.id
        )
        if not stock_location_id:
            return 0

        product = self.browse(product_id)
        # Buscar movimientos de stock pendientes hacia esta ubicación
        pending_moves = (
            self.env["stock.move"]
            .sudo()
            .search(
                [
                    ("product_id", "=", product.id),
                    ("location_dest_id", "=", stock_location_id),
                    ("state", "in", ["draft", "waiting", "confirmed", "assigned"]),
                ]
            )
        )
        return sum(pending_moves.mapped("product_uom_qty"))

    @api.model
    def pos_stock_bulk_update(self, session_id, product_ids):
        """Obtiene el stock disponible y pendiente por recibir de múltiples productos en una sola llamada.
        Esto es mucho más eficiente que hacer llamadas individuales."""
        pos_session = self.env["pos.session"].browse(session_id)
        if (
            not pos_session
            or not pos_session.config_id
            or not pos_session.config_id.picking_type_id
        ):
            return {}

        stock_location_id = (
            pos_session.config_id.picking_type_id.default_location_src_id.id
        )
        if not stock_location_id:
            return {}

        result = {}

        # Obtener todos los quants de los productos en una sola consulta
        quants = self.env["stock.quant"].sudo().search([
            ("product_id", "in", product_ids),
            ("location_id", "=", stock_location_id),
        ])

        # Crear un diccionario de quants por producto
        quant_by_product = {q.product_id.id: q for q in quants}

        # Obtener todos los movimientos pendientes en una sola consulta
        pending_moves = self.env["stock.move"].sudo().search([
            ("product_id", "in", product_ids),
            ("location_dest_id", "=", stock_location_id),
            ("state", "in", ["draft", "waiting", "confirmed", "assigned"]),
        ])

        # Agrupar movimientos pendientes por producto
        incoming_by_product = {}
        for move in pending_moves:
            pid = move.product_id.id
            if pid not in incoming_by_product:
                incoming_by_product[pid] = 0
            incoming_by_product[pid] += move.product_uom_qty

        # Construir resultado
        for product_id in product_ids:
            quant = quant_by_product.get(product_id)
            if quant:
                available = quant.quantity - quant.reserved_quantity
            else:
                available = 0

            incoming = incoming_by_product.get(product_id, 0)

            result[product_id] = {
                'pos_stock_available': available,
                'pos_stock_incoming': incoming,
            }

        return result

    @api.depends("list_price","discount")
    def _compute_discount(self):
        """
        Recalcula el descuento basado en los programas de fidelización.
        """
        for product in self:
            info = product._get_loyalty_information()
            product.sudo().write(info)

    def _get_loyalty_information(self):
        """
        Obtiene el descuento actualizado de un producto según los programas de fidelización.
        """
        self.ensure_one()
        current_datetime = fields.Datetime.now()
        loyalty_programs = (
            self.env["loyalty.program"]
            .sudo()
            .search(
                [
                    ("rule_ids.product_ids", "in", [self.id]),
                    ("pos_ok", "=", True),
                    ("trigger", "=", "auto"),
                    "|",
                    ("date_from", "=", False),
                    ("date_from", "<=", current_datetime),
                    "|",
                    ("date_to", "=", False),
                    ("date_to", ">=", current_datetime),
                ],
                limit=1,
            )
        )
        product_loyalty_info = {"discount": 0, "free_stock": "0 + 0"}

        for reward in loyalty_programs.reward_ids:
            if reward.reward_type == "discount":
                product_loyalty_info["discount"] = reward.discount
            if reward.reward_type == "product":
                product_loyalty_info["free_stock"] = (
                    f"{int(reward.required_points)} + {reward.reward_product_qty}"
                )
        return product_loyalty_info

    @api.model
    def get_discount_for_product(self, product_tmpl_id):
        product_id = (
            self.env["product.product"]
            .sudo()
            .search([("product_tmpl_id", "=", product_tmpl_id)], limit=1)
        )
        if product_id:
            return {
                "success": True,
                "discount": product_id.discount,
                "free_stock": product_id.free_stock,
            }
        return {"success": False, "discount": 0.0, "free_stock": "0 + 0"}
