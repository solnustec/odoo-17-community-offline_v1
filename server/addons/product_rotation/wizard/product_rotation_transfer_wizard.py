# -*- coding: utf-8 -*-
"""
Wizard para transferencia rapida de productos desde el analisis de rotacion.
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductRotationTransferWizard(models.TransientModel):
    """
    Wizard para crear transferencias de productos sin rotacion.

    Permite al usuario seleccionar:
    - Bodega destino (de las sugeridas o cualquier otra)
    - Cantidad a transferir
    - Crear la transferencia directamente
    """
    _name = 'product.rotation.transfer.wizard'
    _description = 'Wizard de Transferencia de Producto'

    # =========================================================================
    # CAMPOS
    # =========================================================================

    rotation_id = fields.Many2one(
        'product.rotation.daily',
        string='Registro de Rotacion',
        required=True,
        readonly=True,
    )

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        readonly=True,
    )

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Bodega Origen',
        required=True,
        readonly=True,
    )

    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Bodega Destino',
        required=True,
        domain="[('id', '!=', source_warehouse_id)]",
    )

    available_quantity = fields.Float(
        string='Stock Disponible',
        help='Cantidad disponible en la bodega origen.',
    )

    quantity = fields.Float(
        string='Cantidad a Transferir',
        required=True,
        default=0.0,
    )

    transfer_all = fields.Boolean(
        string='Transferir Todo',
        default=True,
        help='Marcar para transferir todo el stock disponible.',
    )

    suggested_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Bodegas Sugeridas',
        compute='_compute_suggested_warehouses',
        help='Bodegas donde el producto tiene rotacion activa.',
    )

    notes = fields.Text(
        string='Notas',
        help='Notas adicionales para la transferencia.',
    )

    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================

    @api.depends('rotation_id')
    def _compute_suggested_warehouses(self):
        """Obtiene las bodegas sugeridas del registro de rotacion."""
        for wizard in self:
            if wizard.rotation_id:
                wizard.suggested_warehouse_ids = wizard.rotation_id.suggested_warehouse_ids
            else:
                wizard.suggested_warehouse_ids = self.env['stock.warehouse']

    # =========================================================================
    # ONCHANGE
    # =========================================================================

    @api.onchange('rotation_id')
    def _onchange_rotation_id(self):
        """Actualiza los valores cuando cambia el registro de rotacion."""
        if self.rotation_id:
            self.product_id = self.rotation_id.product_id
            self.source_warehouse_id = self.rotation_id.warehouse_id
            self.available_quantity = self.rotation_id.stock_on_hand
            self.quantity = self.rotation_id.stock_on_hand

    @api.onchange('transfer_all', 'available_quantity')
    def _onchange_transfer_all(self):
        """Actualiza la cantidad cuando se marca/desmarca transferir todo."""
        if self.transfer_all:
            self.quantity = self.available_quantity

    @api.onchange('quantity')
    def _onchange_quantity(self):
        """Desmarca 'transferir todo' si se modifica la cantidad manualmente."""
        if self.quantity != self.available_quantity:
            self.transfer_all = False

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def action_transfer(self):
        """
        Ejecuta la transferencia del producto.

        Returns:
            dict: Accion para mostrar el picking creado
        """
        self.ensure_one()

        # Validaciones
        if not self.dest_warehouse_id:
            raise UserError(_('Debe seleccionar una bodega destino.'))

        if self.dest_warehouse_id.id == self.source_warehouse_id.id:
            raise UserError(_('La bodega destino debe ser diferente a la bodega origen.'))

        if self.quantity <= 0:
            raise UserError(_('La cantidad a transferir debe ser mayor a 0.'))

        available_qty = self.rotation_id.stock_on_hand

        if self.quantity > available_qty:
            raise UserError(_(
                'La cantidad a transferir (%.2f) excede el stock disponible (%.2f).'
            ) % (self.quantity, self.available_quantity))

        # Llamar al metodo de transferencia rapida del modelo principal
        return self.rotation_id.action_quick_transfer(
            self.dest_warehouse_id.id,
            self.quantity
        )

    def action_select_warehouse(self):
        """
        Accion para seleccionar una bodega sugerida (llamada desde boton).
        Se usa como action_context desde los botones del formulario.
        """
        self.ensure_one()
        # Este metodo se puede usar para abrir un selector de bodegas
        # Por ahora, el usuario selecciona directamente en el campo dest_warehouse_id
        return {'type': 'ir.actions.act_window_close'}
