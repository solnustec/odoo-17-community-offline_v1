import json
import re
from datetime import datetime

from odoo import models, fields, api
from odoo.http import Response


def _shorten_invoice_name(name, move_type='in_invoice'):
    """
    Acorta el nombre de factura/nota de crédito.
    Ej: 'Fact 001-001-000017392' -> 'FACT17392'
    Ej: 'NC 001-001-000017392' -> 'NC17392'
    """
    if not name:
        return ''
    # Extraer solo los dígitos del final del nombre
    digits = re.findall(r'\d+', name)
    if digits:
        # Tomar el último grupo de dígitos (el secuencial)
        last_digits = digits[-1].lstrip('0') or '0'
        # Determinar prefijo según tipo de documento
        if move_type == 'in_refund':
            return f'NC{last_digits}'
        else:
            return f'FACT{last_digits}'
    return name[:15] if len(name) > 15 else name


class ProductProduct(models.Model):
    _inherit = "product.product"

    product_sales_priority = fields.Boolean(string="Producto Prioritario",
                                            help='Este campo de activa cuando en la compra, no existe en el proveedor predeterminado',
                                            default=False)
    coupon_info = fields.Integer(string='Coupon',
                                 help='Coupon asociado al producto, utilizado en promociones',
                                 default=0)

    @api.model
    def get_last_purchase(self, product_id, limit):
        """
        Devuelve las últimas líneas de compra asociadas a un producto.

        :param product_id: ID del producto (product.product) para el que se buscan las compras.
        :type product_id: int
        :param limit: Número máximo de líneas de compra a devolver.
        :type limit: int
        :return: Lista de diccionarios con información relevante de cada línea de compra, incluyendo descuento, precios, cantidad, fecha, unidad de medida, PVF y proveedor.
        :rtype: list[dict]
        """
        product = self.browse(product_id)
        items = len(product.po_product_line_ids)
        if len(product.po_product_line_ids) > limit:
            history_lines = product.po_product_line_ids[
                -limit] if product.po_product_line_ids else []
        else:
            history_lines = product.po_product_line_ids[
                -items] if product.po_product_line_ids else []
        if len(history_lines) > 0:
            # return []
            result = []
            for line in history_lines:
                result.append({
                    'discount': line.product_discount,
                    'price_unit': round(line.price_unit, 3),
                    'price_box': round(line.price_box, 3),
                    'price_subtotal': round(line.price_subtotal, 3),
                    'product_uom_id': line.product_uom_id.name,
                    'product_qty': line.product_qty,
                    'date_order': line.order_reference_id.date_order.date(),
                    'pvf': line.pvf,
                    'supplier': line.order_reference_id.partner_id.name
                })
            return result
        return []

    @api.model
    def get_complete_purchase_history(self, product_id, limit=5, offset=0):
        """
        Returns the complete purchase history from the purchase_history module with pagination support.
        This method fetches persistent purchase history records from product.purchase.history model,
        which is more reliable than computed fields from purchase_product_history module.
        
        Features:
        - Uses persistent data from product.purchase.history model
        - Supports pagination with limit and offset parameters
        - Maps fields to expected format for frontend compatibility
        - Returns date objects for template compatibility
        - Includes error handling with empty list fallback
        
        :param product_id: ID of the product (product.product) to search purchases for.
        :param limit: Maximum number of records to return (default: 5).
        :param offset: Number of records to skip for pagination (default: 0).
        :return: List of dictionaries containing purchase history information.
        :rtype: list[dict]
        """
        try:
            product = self.browse(product_id)
            if not product.exists():
                return []

            # Search in product.purchase.history (purchase_history module) with limit and offset for pagination
            # Incluir tanto compras normales como notas de crédito
            purchase_history = self.env['product.purchase.history'].search([
                ('product_tmpl_id', '=', product.product_tmpl_id.id)
            ], order='date_order desc', limit=limit, offset=offset)

            result = []

            # Process purchase history records and map to expected format
            for line in purchase_history:
                # Obtener las facturas donde el PRODUCTO ESPECÍFICO aparece en las líneas
                # No todas las facturas de la PO, solo las que contienen este producto
                invoices_list = []
                try:
                    po = line.purchase_order_id
                    product_tmpl_id = line.product_tmpl_id.id

                    if po and product_tmpl_id:
                        found_invoice_ids = set()  # Para evitar duplicados

                        # Buscar facturas de la PO donde el producto específico está en las líneas
                        if po.name:
                            # Buscar líneas de factura que:
                            # 1. Pertenezcan a facturas con invoice_origin = nombre de la PO
                            # 2. Contengan el producto específico (por product_tmpl_id)
                            # Incluir facturas (in_invoice) y notas de crédito (in_refund)
                            invoice_lines = self.env['account.move.line'].search([
                                ('move_id.invoice_origin', '=', po.name),
                                ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
                                ('move_id.state', '=', 'posted'),
                                ('product_id.product_tmpl_id', '=', product_tmpl_id),
                            ])

                            for inv_line in invoice_lines:
                                inv = inv_line.move_id
                                if inv and inv.id not in found_invoice_ids:
                                    found_invoice_ids.add(inv.id)
                                    full_name = inv.name or inv.ref or inv.display_name or ''
                                    invoices_list.append({
                                        'id': inv.id,
                                        'name': _shorten_invoice_name(full_name, inv.move_type),
                                        'date': str(inv.invoice_date) if inv.invoice_date else '',
                                        'state': inv.state,
                                        'move_type': inv.move_type,
                                    })

                                    # Buscar notas de crédito vinculadas por reversed_entry_id
                                    credit_notes = self.env['account.move'].search([
                                        ('reversed_entry_id', '=', inv.id),
                                        ('move_type', '=', 'in_refund'),
                                        ('state', '=', 'posted'),
                                    ])
                                    for cn in credit_notes:
                                        if cn.id not in found_invoice_ids:
                                            found_invoice_ids.add(cn.id)
                                            cn_full_name = cn.name or cn.ref or cn.display_name or ''
                                            invoices_list.append({
                                                'id': cn.id,
                                                'name': _shorten_invoice_name(cn_full_name, cn.move_type),
                                                'date': str(cn.invoice_date) if cn.invoice_date else '',
                                                'state': cn.state,
                                                'move_type': cn.move_type,
                                            })

                        # Ordenar por fecha descendente (más reciente primero)
                        invoices_list.sort(key=lambda x: x['date'], reverse=True)

                except Exception:
                    invoices_list = []

                # Para compatibilidad, mantener invoice_id e invoice_name con la última factura
                last_invoice = invoices_list[0] if invoices_list else None
                # Lógica para determinar el precio unitario correcto
                # Si tiene purchase_order_id = es de Odoo, usar price_unit_per_unit (con cálculos)
                # Si NO tiene purchase_order_id = es importado, usar price_unit (original)
                if line.purchase_order_id:
                    # Registro de Odoo: usar price_unit_per_unit (ya calculado con descuentos)
                    price_unit_converted = getattr(line, 'price_unit_per_unit', False)
                    if price_unit_converted is False or price_unit_converted is None:
                        price_unit_converted = line.price_unit
                else:
                    # Registro importado: usar price_unit original (sin cálculos)
                    price_unit_converted = line.price_unit
                # Alinear PVF con la lógica del listado principal (sales_report):
                # En get_total_sales_summary, pvf inicia en 0 y solo se calcula si avg_standar_price_old != 0
                # pvf = list_price - (list_price * 16.66 / 100)
                # print(line.product_tmpl_id.uom_po_id)
                # TODO REvisar esto de la covnersion de unidades
                try:
                    tmpl = product.product_tmpl_id
                    if tmpl and getattr(tmpl, 'avg_standar_price_old', 0) != 0:
                        p_list_price = (tmpl.list_price or 0.0)
                        pvf_display = round(p_list_price - (p_list_price * (16.66 / 100.0)), 2)
                    else:
                        pvf_display = 0
                except Exception:
                    pvf_display = 0
                result.append({
                    'discount': line.discount or 0.0,  # Descuento real del historial
                    'price_unit': round(price_unit_converted, 3),
                    # Usar el valor correcto según origen
                    'price_box': round(line.price_unit, 3),  # mantener original
                    'price_subtotal': round(line.price_unit * line.quantity, 3),
                    'product_uom_id': product.uom_id.name if product.uom_id else '',
                    'product_qty': line.quantity,
                    'paid_quantity': line.paid_quantity,
                    'free_product_qty': line.free_product_qty or 0.0,
                    # Producto gratis real del historial
                    'date_order': line.date_order if line.date_order else '',
                    'pvf': round(pvf_display, 3),
                    'supplier': line.partner_id.name if line.partner_id else '',
                    'order_name': line.purchase_order_id.name if line.purchase_order_id else '',
                    'order_id': line.purchase_order_id.id if line.purchase_order_id else False,
                    # Indicador de nota de crédito
                    'is_credit_note': getattr(line, 'credit_note', False),
                    # Última factura (para compatibilidad)
                    'invoice_name': last_invoice['name'] if last_invoice else '',
                    'invoice_id': last_invoice['id'] if last_invoice else False,
                    # Array con todas las facturas relacionadas
                    'invoices': invoices_list,
                    'invoices_count': len(invoices_list),
                    'description': f"{product.name} - {line.purchase_order_id.name}" if line.purchase_order_id else product.name
                })

            return result

        except Exception as e:
            print(e)
            # Return empty list to avoid failures if any error occurs
            return []

    @api.model
    def toggle_sales_priority(self, product_id):
        """
        Metodo para cambiar el estado del campo product_sales_priority.
        :param product_id: ID del product.product a modificar
        :return: True si se actualizó correctamente
        """
        product = self.browse(product_id)
        if product:
            product.sudo().write(
                {'product_sales_priority': not product.product_sales_priority})
        return True

    @api.model
    def get_product_received_totals(self, product_id, date_start, date_end):
        """
        Retorna el total de cantidad recibida para un producto en un rango de fechas.

        :param product_id: ID del product.produc (int)
        :param date_start: Fecha de inicio (str o date, formato 'YYYY-MM-DD')
        :param date_end: Fecha de fin (str o date, formato 'YYYY-MM-DD')
        :return: Diccionario con el total de cantidad recibida y unidad de medida
        """
        # Convertir fechas a objetos date si son cadenas
        if isinstance(date_start, str):
            date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
        if isinstance(date_end, str):
            date_end = datetime.strptime(date_end, '%Y-%m-%d').date()

        # Buscar movimientos de inventario completados (recepciones)
        domain = [
            ('product_id', '=', product_id),
            ('state', '=', 'done'),  # Solo movimientos completados
            ('picking_id.picking_type_id.code', '=', 'incoming'),
            # Solo recepciones
            ('date', '>=', date_start),
            ('date', '<=', date_end),
        ]
        stock_moves = self.env['stock.move'].search(domain)

        # Sumar la cantidad recibida
        total_quantity_received = sum(stock_moves.mapped('quantity'))

        return {
            'product_id': product_id,
            'total_quantity_received': total_quantity_received,
            'uom_id': self.browse(
                product_id).uom_id.id if product_id else False, }

    @api.model
    def get_product_info(self, product_id):
        """
        Retorna información básica del producto.

        :param product_id: ID del product.product (int)
        :return: Diccionario con informacion del produto adicinal tambien con informacion de las promocjones de ese producto
        """
        # Buscar la variante primero
        # calcular el tiempo  de ejecucion de la consulta con time
        import time
        start_time = time.time()
        product = self.env['product.product'].browse(product_id)
        if not product:
            return {}

        # 1. Usar with_context para prefetch y reducir consultas SQL
        product = product.with_context(prefetch_fields=True)
        product_template = product.product_tmpl_id
        # product_discount = product.discount

        # 2. Optimizar la selección de campos usando read() en lugar de acceder directamente
        product_template_data = product_template.read([
            'id', 'name', 'min_stock', 'max_stock', 'sale_uom_ecommerce',
            'standar_price_old', 'avg_standar_price_old', 'standard_price', 'list_price',
            'price_with_tax', 'taxes_id', 'supplier_taxes_id',
            'uom_id', 'uom_po_id', 'tax_string', 'coupon',
        ])[0] if product_template else {}
        tax_id = product_template.taxes_id[0]
        if tax_id.amount > 0:
            tax_amount = product_template.list_price * tax_id.amount / 100
            product_template_data[
                'price_with_tax'] = product_template.list_price + tax_amount
        else:
            product_template_data['price_with_tax'] = product_template.list_price
        if product_template_data.get('avg_standar_price_old', 0) == 0:
            product_template_data['avg_standar_price_old'] = product_template_data.get(
                'standar_price_old', 0)
        # filtar los impuestos de compras con cero 15 o 12
        supplier_taxes_id = product_template.supplier_taxes_id.filtered(
            lambda t: t.amount in (0, 12, 15)) if product_template.supplier_taxes_id else []
        if supplier_taxes_id:
            product_template_data['supplier_taxes_info'] = {
                'id': supplier_taxes_id[0].id,
                'name': supplier_taxes_id[0].name,
                'amount': supplier_taxes_id[0].amount,
            }
        else:
            product_template_data['supplier_taxes_info'] = {
                'id': 0,
                'name': 'No Tax',
                'amount': 0,
            }

        # 3. Agregar tax_amount directamente en la lectura
        product_template_data['tax_amount'] = product_template.taxes_id[
            0].amount if product_template.taxes_id else 0
        product_template_data['qty_available'] = product.qty_available

        # 4. Optimizar búsqueda de loyalty programs con campos específicos
        loyalty_programs = self.env['loyalty.program'].with_context(
            prefetch_fields=True).search([
            ('active', '=', True),
            ('pos_ok', '=', True),
            ('trigger_product_ids', 'in', [product_id])
        ], order='id')

        # 5. Usar read() para loyalty programs y sus relaciones
        loyalty_program_data = loyalty_programs.read([
            'id', 'name', 'date_from', 'date_to',
            'active', 'mandatory_promotion', 'note_promotion',
            'program_type', 'applies_to_the_second',
        ])

        # 6. Obtener rules y rewards en una sola pasada usando mapped
        rules_data = [
            {'program_id': program.id, 'id': rule.id}
            for program in loyalty_programs
            for rule in program.rule_ids.filtered(lambda r: r.active)
        ]

        reward_discount = [
            {
                'program_id': program.id,
                'id': reward.id,
                'reward_type': reward.reward_type,
                'required_points': reward.required_points,
                'discount_applicability': reward.discount_applicability or None,
                'discount': reward.discount if hasattr(reward, 'discount') else None,
                'reward_product_qty': reward.reward_product_qty if hasattr(
                    reward, 'reward_product_qty') else None,
                'active': reward.active,
                'is_main': reward.is_main,
                'date_from': reward.date_from,
                'date_to': reward.date_to,
                'is_temporary': reward.is_temporary,
            }
            for program in loyalty_programs
            for reward in
            program.mapped('reward_ids').filtered(
                lambda r: r.active and r.reward_type == 'discount')
        ]
        reward_product = [
            {
                'program_id': program.id,
                'id': reward.id,
                'reward_type': reward.reward_type,
                'required_points': reward.required_points,
                'discount_applicability': reward.discount_applicability or None,
                'discount': reward.discount if hasattr(reward,
                                                       'discount') else None,
                'reward_product_qty': reward.reward_product_qty if hasattr(
                    reward, 'reward_product_qty') else None,
                'active': reward.active,
                'date_from': reward.date_from,
                'date_to': reward.date_to,
                'is_temporary': reward.is_temporary,
            }
            for program in loyalty_programs
            for reward in
            program.mapped('reward_ids').filtered(
                lambda r: r.active and r.reward_type == 'product')
        ]

        # 7. Performance measurement (commented out for production)
        # end_time = time.time()
        # print(f"Tiempo de ejecución: {end_time - start_time:.3f} segundos")

        # Filtrar solo el descuento del programa de tipo promociones o tarjeta de lealtad para enviar en product_discount y temporal_product_discount
        promotion_prog = next((p for p in loyalty_programs if p.program_type in ('promotion', 'loyalty')), None)
        promotion_discount = 0.0
        temporary_promotion_discount = 0.0
        if promotion_prog:
            filtered_reward_discount = promotion_prog.reward_ids.filtered(lambda r: r.active and r.reward_type == 'discount' and r.is_main == False)[:1]
            if filtered_reward_discount:
                filtered_reward_discount = filtered_reward_discount[0]
                if filtered_reward_discount.is_temporary:
                    temporary_promotion_discount = filtered_reward_discount.discount
                else:
                    promotion_discount = filtered_reward_discount.discount

        return {
            # 'product_discount': reward_discount[0].get('discount',0) if reward_discount else 0,
            'product_discount': promotion_discount,
            'temporary_product_discount': temporary_promotion_discount,
            'product_tmpl_id': product_template_data,
            'loyalty_program': loyalty_program_data,
            'rules_data': rules_data,
            'reward_discount': reward_discount,
            'reward_product': reward_product,
        }

    @api.model
    def set_disabled_product(self, product_id):
        """
        Desactiva los productos cuyo ID está en la lista proporcionada.

        :param product_ids: Lista de IDs de productos a desactivar.
        :type product_ids: list[int]
        :return: True si la operación se realizó correctamente.
        :rtype: bool
        """
        # get product_template id form product_id
        product = self.browse(product_id)
        if not product:
            return False
        products = self.search(
            [('product_tmpl_id', '=', product.product_tmpl_id.id), ('active', '=', True)])
        if not products:
            return False
        # Desactivar los productos encontrados
        products.sudo().write(
            {'sale_ok': False, 'name': f'{product.name} - DESCONTINUADO/DESACTIVADO',
             'is_discontinued': True})
        return True

    @api.model
    def get_product_image_url(self, product_id):
        """
        Obtiene la URL de la imagen del producto de manera eficiente.
        Solo retorna la URL si el producto tiene imagen, evitando cargas innecesarias.

        :param product_id: ID del producto
        :type product_id: int
        :return: URL de la imagen o None si no tiene imagen
        :rtype: str or None
        """
        try:
            product = self.browse(product_id)
            if not product.exists():
                return None

            # Verificar si el producto tiene imagen
            if product.image_1920:
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                return f"{base_url}/web/image/product.product/{product_id}/image_1920"

            return None
        except Exception:
            return None
