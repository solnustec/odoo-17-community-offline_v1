# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: ADVAITH B G (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models, _


class PurchaseOrderLines(models.Model):
    """Inherits Purchase order line for scanning multi barcode"""
    _inherit = "purchase.order.line"

    scan_barcode = fields.Char(
        string='Cod. Barras',
        help="Escanee o escriba el código de barras del producto"
    )
    barcode_not_found = fields.Boolean(
        string="Barcode Not Found",
        default=False,
        help="Indica si el código de barras escaneado no fue encontrado"
    )
    pending_barcode = fields.Char(
        string="Pending Barcode",
        help="Código de barras pendiente de asignar"
    )

    def _search_product_by_barcode(self, barcode):
        """
        Busca un producto por su código de barras.
        Busca tanto en el barcode estándar como en los códigos alternativos.

        Args:
            barcode (str): Código de barras a buscar

        Returns:
            product.product recordset or False
        """
        if not barcode:
            return False

        # 1. Buscar en el barcode estándar de product.product
        product = self.env["product.product"].search([
            ("barcode", "=", barcode)
        ], limit=1)
        if product:
            return product

        # 2. Buscar en los códigos de barras alternativos
        multi_barcode = self.env["product.multiple.barcodes"].search([
            ("product_multi_barcode", "=", barcode)
        ], limit=1)
        if multi_barcode:
            return multi_barcode.product_id

        return False

    def _barcode_exists(self, barcode):
        """
        Verifica si un código de barras ya existe en el sistema.

        Args:
            barcode (str): Código de barras a verificar

        Returns:
            bool: True si existe, False si no
        """
        if not barcode:
            return False

        # Verificar en barcode estándar
        if self.env["product.product"].search_count([("barcode", "=", barcode)]):
            return True

        # Verificar en códigos alternativos
        if self.env["product.multiple.barcodes"].search_count([
            ("product_multi_barcode", "=", barcode)
        ]):
            return True

        return False

    @api.onchange('scan_barcode')
    def _onchange_scan_barcode(self):
        """
        Busca el producto cuando se escanea/escribe un código de barras.
        Si el código existe, selecciona el producto automáticamente.
        Si no existe, marca el campo pending_barcode para posterior asignación.
        """
        if not self.scan_barcode:
            self.barcode_not_found = False
            self.pending_barcode = False
            return

        # Buscar el producto por barcode
        product = self._search_product_by_barcode(self.scan_barcode)

        if product:
            # Producto encontrado - seleccionar automáticamente
            self.product_id = product.id
            self.barcode_not_found = False
            self.pending_barcode = False
        else:
            # Producto no encontrado - marcar como pendiente
            self.barcode_not_found = True
            self.pending_barcode = self.scan_barcode
            # No limpiar product_id para permitir selección manual

    @api.onchange('product_id')
    def _onchange_product_id_barcode_check(self):
        """
        Detecta cuando el usuario selecciona un producto manualmente
        después de que un barcode no fue encontrado.
        Ofrece registrar el código de barras pendiente.
        """
        # Solo actuar si hay un barcode pendiente y un producto seleccionado
        if not self.pending_barcode or not self.product_id:
            return

        # Verificar nuevamente que el barcode no exista (por seguridad)
        if self._barcode_exists(self.pending_barcode):
            self.pending_barcode = False
            self.barcode_not_found = False
            return

        # Abrir wizard de confirmación
        return {
            "type": "ir.actions.act_window",
            "name": _("Asignar Código de Barras"),
            "res_model": "barcode.assign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_barcode": self.pending_barcode,
                "default_product_id": self.product_id.id,
                "default_purchase_order_id": self.order_id.id if self.order_id else False,
                "default_purchase_line_id": self.id if isinstance(self.id, int) else False,
            }
        }

    def action_assign_pending_barcode(self):
        """
        Acción manual para asignar un código de barras pendiente.
        Puede ser llamada desde un botón en la vista.
        """
        self.ensure_one()

        if not self.pending_barcode:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin Barcode Pendiente"),
                    "message": _("No hay código de barras pendiente para asignar."),
                    "type": "warning",
                    "sticky": False,
                }
            }

        if not self.product_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Producto Requerido"),
                    "message": _("Debe seleccionar un producto primero."),
                    "type": "warning",
                    "sticky": False,
                }
            }

        if self._barcode_exists(self.pending_barcode):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Barcode Ya Existe"),
                    "message": _("El código de barras '%s' ya está registrado.") % self.pending_barcode,
                    "type": "warning",
                    "sticky": False,
                }
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Asignar Código de Barras"),
            "res_model": "barcode.assign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_barcode": self.pending_barcode,
                "default_product_id": self.product_id.id,
                "default_purchase_order_id": self.order_id.id,
                "default_purchase_line_id": self.id,
            }
        }

    def write(self, vals):
        """
        Override write para limpiar campos de barcode pendiente después de guardar
        si el barcode fue asignado exitosamente.
        """
        res = super().write(vals)

        # Si se actualizó scan_barcode, verificar si ahora existe
        if 'scan_barcode' in vals:
            for line in self:
                if line.pending_barcode and line._barcode_exists(line.pending_barcode):
                    line.write({
                        'pending_barcode': False,
                        'barcode_not_found': False
                    })

        return res
