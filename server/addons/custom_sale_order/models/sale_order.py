from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import base64
import csv
import io
import logging

UNIT_SELECTION = [
    ('dias', 'Dias'),
    ('meses', 'Meses'),
    ('años', 'Años'),
]

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    cost_price = fields.Float(
        string="Costo Unitario",
        related='product_id.standard_price',
        store=True,
        readonly=True
    )

    useful = fields.Float(
        string="Utilidad",
        compute='_compute_useful',
        store=True,
        readonly=True
    )

    tax_amount_total = fields.Monetary(
        string="Valor do Imposto",
        compute="_compute_tax_amount_total",
        store=True,
        currency_field='currency_id'
    )

    @api.depends('price_total', 'price_subtotal')
    def _compute_tax_amount_total(self):
        for line in self:
            line.tax_amount_total = line.price_total - line.price_subtotal

    @api.depends('price_reduce_taxinc', 'cost_price')
    def _compute_useful(self):
        for record in self:
            if record.cost_price:
                record.useful = ((record.price_reduce_taxinc - record.cost_price) / record.cost_price) * 100
            else:
                record.useful = 0.0


class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    warranty_period = fields.Integer(
        string="Tiempo de Garantia",
        default=3,
        required=False
    )
    
    warranty_unit = fields.Selection(
        UNIT_SELECTION,
        string="Unidad Garantia",
        default='meses',
        required=True
    )

    validity_period = fields.Integer(
        string="Tiempo de Validez de Oferta",
        default=2,
        required=False
    )

    validity_unit = fields.Selection(
        UNIT_SELECTION,
        string="Unidad Validez",
        default='meses',
        required=True
    )

    delivery_time = fields.Integer(
        string="Tiempo de Entrega",
        compute="_compute_time_delivery",
        store=True
    )

    delivery_unit = fields.Selection(
        UNIT_SELECTION,
        string="Unidad Entrega",
        default='dias',
        required=True
    )

    @api.depends('commitment_date', 'date_order')
    def _compute_time_delivery(self):
        for order in self:
            if order.commitment_date and order.date_order:
                delta = relativedelta(order.commitment_date, order.date_order)
                total_days = (order.commitment_date - order.date_order).days
                
                if total_days < 30:
                    order.delivery_time = total_days
                    order.delivery_unit = 'dias'
                elif total_days < 365:
                    order.delivery_time = delta.years * 12 + delta.months
                    order.delivery_unit = 'meses'
                else:
                    order.delivery_time = delta.years
                    order.delivery_unit = 'años'
            else:
                order.delivery_time = 0
                order.delivery_unit = 'dias'
    
    def action_download_sale_order_csv(self):
        field_names = [
            "Pedido", "Producto", "Descripción", "Cantidad", "Precio Unitario",
            "Subtotal", "Impuestos", "Total", "Costo Unitario", "Utilidad (%)",
            "Descuento (%)", "Valor del Descuento", "Laboratorio", "Marca", "Fabricante",
            "Nombre Genérico", "Requiere Receta", "Código de Barras 1", "Código de Barras 2",
            "Código de Barras 3", "Código de Barras 4", "Código de Barras 5"
        ]

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        # writer = csv.writer(output, delimiter=";")
        writer.writerow(field_names)  

        for line in self.order_line:
            desconto_valor = (line.price_unit * line.discount / 100) * line.product_uom_qty if line.discount else 0.0
            writer.writerow([
                self.name,
                line.product_id.display_name or "",
                line.name, 
                line.product_uom_qty, 
                "{:.2f}".format(line.price_unit),  
                "{:.2f}".format(line.price_subtotal),  
                "{:.2f}".format(line.tax_amount_total),  
                "{:.2f}".format(line.price_total),  
                "{:.2f}".format(line.cost_price),  
                "{:.2f}".format(line.useful),  
                "{:.2f}".format(line.discount or 0.0),
                "{:.2f}".format(desconto_valor),
                line.product_id.laboratory_id.name or "",
                line.product_id.brand_id.name or "",
                line.product_id.manufacturer_id.name or "",
                line.product_id.generic_name or "",
                line.product_id.requires_recipe and "Sí" or "No",
                # line.product_id.barcode1 or "",
                # line.product_id.barcode2 or "",
                # line.product_id.barcode3 or "",
                # line.product_id.barcode4 or "",
                # line.product_id.barcode5 or "",
            ])

        file_data = base64.b64encode(output.getvalue().encode("utf-8"))
        output.close()

        attachment = self.env["ir.attachment"].create({
            "name": f"Proforma_{self.name}.csv",
            "type": "binary",
            "datas": file_data,
            "res_model": "sale.order",
            "res_id": self.id,
            "mimetype": "text/csv",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
