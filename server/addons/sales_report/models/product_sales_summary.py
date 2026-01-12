import functools
import logging
import math
import time
from datetime import timedelta, datetime
from odoo.exceptions import UserError, ValidationError

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SalesSummaryError(models.Model):
    _name = 'sales.summary.error'
    _description = 'Error en Resumen de Ventas'
    error_details = fields.Text(string='Detalles del Error', readonly=True)


class ProductWarehouseSaleSummary(models.Model):
    _name = 'product.warehouse.sale.summary'
    _description = 'Resumen de Ventas por Producto y Almacén'
    _order = 'date desc'

    date = fields.Date(string='Fecha', required=True)
    hour = fields.Float(string='Hora', required=False, default=0.0)
    product_id = fields.Many2one('product.product', string='Producto',
                                 required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén',
                                   required=False)
    quantity_sold = fields.Float(string='Cantidad Vendida', default=0.0)
    amount_total = fields.Float(string='Monto Total', default=0.0)
    costo_total = fields.Float(string='Costo Total', default=0.0)

    uom_id = fields.Many2one('uom.uom', string='Unidad de Medida',
                             related='product_id.uom_id')
    is_legacy_system = fields.Boolean(
        string='Sistema Legado',
        help='Indica si el resumen proviene de un sistema legado.',
        default=False
    )

    stock_adjusted = fields.Boolean(
        string='Stock Ajustado',
        default=False,
        help='Indica si ya se ajustó el stock para este registro'
    )

    record_type = fields.Selection(
        selection=[
            ('sale', 'Ventas'),
            ('transfer', 'Transferencias'),
        ],
        default='sale',
        string="Tipo"
    )


    # user_id = fields.Many2one('res.users', string='Usuario')

    def timed_cache(timeout=3600):
        def decorator(func):
            cache = {}

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                key = str(args) + str(kwargs)
                now = time.time()
                if key in cache and now - cache[key][1] < timeout:
                    print(
                        f"Resultado desde caché para {func.__name__} con key={key}")
                    return cache[key][0]
                result = func(*args, **kwargs)
                cache[key] = (result, now)
                print(
                    f"Nuevo resultado calculado para {func.__name__} con key={key}")
                return result

            wrapper.cache_clear = lambda: cache.clear()
            return wrapper

        return decorator

    @api.model
    def get_google_spreadsheet_api_key(self):
        api_key = self.env['ir.config_parameter'].sudo().search([('key', '=','google_spreedsheet_api')])
        return api_key.value

    @api.model
    def get_total_sales_by_warehouse(self, date_from, date_to,
                                     warehouse_id=None, product_id=None):

        Product = self.env['product.product']
        active_product = Product.search([('id', '=', product_id)])
        Quant = self.env['stock.quant']
        stock_data = Quant.read_group(
            [('product_id', 'in', active_product.ids),
             ('location_id.usage', '=', 'internal')],
            ['product_id', 'quantity:sum'],
            ['product_id']
        )
        stock_map = {q['product_id'][0]: q['quantity'] for q in stock_data}
        Summary = self.env['product.warehouse.sale.summary']
        sales_data = Summary.read_group(
            [('date', '>=', date_from), ('date', '<=', date_to),
             ('product_id', 'in', active_product.ids),
             ('is_legacy_system', '=', True),
             ('warehouse_id', '=', warehouse_id)],
            ['product_id', 'quantity_sold:sum', 'amount_total:sum',
             'costo_total:sum'],
            ['product_id']
        )
        summary_map = {
            s['product_id'][0]: {
                'quantity_sold': s['quantity_sold'],
                'amount_total': s['amount_total'],
                'costo_total': s['costo_total']

            } for s in sales_data
        }
        products = active_product.read(
            ['default_code', 'brand_id', 'laboratory_id', 'name', 'uom_id',
             'uom_po_id', 'discount', 'standard_price', 'list_price',
             'product_sales_priority', 'currency_id', 'taxes_id',
             'product_tmpl_id'])
        results = []
        for product in products:
            product_id = product['id']
            data = summary_map.get(product_id,
                                   {'quantity_sold': 0.0, 'amount_total': 0.0,
                                    'costo_total': 0.0})
            quantity_sold = data['quantity_sold']
            costo_total = data['costo_total']

            uom_po = self.env['uom.uom'].browse(
                product['uom_po_id'][0]) if product.get('uom_po_id') else False
            uom_po_ratio = uom_po.ratio if uom_po else 1.0

            if uom_po_ratio and uom_po_ratio != 0:
                boxes = quantity_sold // uom_po_ratio
                units = quantity_sold % uom_po_ratio
            else:
                boxes = 0
                units = quantity_sold
            template = self.env['product.template'].browse(
                product.get('product_tmpl_id')[0])
            if quantity_sold == 0 or costo_total == 0 or data[
                'amount_total'] == 0:
                # si no se vendio nada o el costo es cero, no se calcula utilidad
                # ni precio con impuestos
                product_utility = 0
                price_with_taxes = 0
            else:
                price_with_taxes = self.get_price_with_taxes(product.get('id'))

                product_utility = (data[
                                       'amount_total'] - costo_total) / costo_total
            utility_percent = product_utility * 100
            truncado = math.floor(round(utility_percent, 2) * 10) / 10

            product_name = product.get('name',
                                       '')
            change_average_cost = 0
            percentage_change_average_cost = 0

            if template.avg_standar_price_old != 0:
                # pvf = price_with_taxes - (price_with_taxes * (16.5 / 100))
                pvf = product.get('list_price', 0) - (
                        product.get('list_price', 0) * (16.66 / 100))
                change_average_cost = (
                                              pvf - template.avg_standar_price_old) / template.avg_standar_price_old
                percentage_change_average_cost = change_average_cost * 100
            results.append({
                'product_id': product_id,
                'product_code': product.get('default_code', ''),
                'id_database_old': template.id_database_old or '',
                'brand': product.get('brand_id', (0, ''))[1] if isinstance(
                    product.get('brand_id'), tuple) else '',
                'brand_id': product.get('brand_id', (0, ''))[0] if isinstance(
                    product.get('brand_id'), tuple) else 0,
                'laboratory_id': product.get('laboratory_id', (0, ''))[
                    0] if isinstance(
                    product.get('laboratory_id'), tuple) else '',
                'product_name': product_name.lower().title(),
                'quantity_sold': quantity_sold,
                'amount_total': round(data['amount_total'], 3),
                'total_cost': round(data['costo_total'], 3),
                'boxes': boxes,
                'units': units,
                'uom': product.get('uom_id', (0, ''))[1] if isinstance(
                    product.get('uom_id'), tuple) else '',
                'uom_po_id': product.get('uom_po_id', (0, ''))[
                    1] if isinstance(
                    product.get('uom_po_id'), tuple) else '',
                'uom_factor': uom_po_ratio,
                'stock_total': stock_map.get(product_id, 0.0),
                'standard_price': template.standar_price_old,
                'list_price': product.get('list_price', 0),
                'discount': product.get('discount', 0),
                'utility': truncado,
                'product_sales_priority': product.get('product_sales_priority',
                                                      False),
                'price_with_taxes': price_with_taxes,
                'change_average_cost': change_average_cost,
                'percentage_change_average_cost':
                    round(percentage_change_average_cost, 2),
                'standar_price_old': round(template.standar_price_old, 2),
                'avg_standar_price_old': round(template.avg_standar_price_old,
                                               2) if template.avg_standar_price_old > 0 else template.standar_price_old,

            })
        return results

    @api.model
    def get_products_by_query(self, date_from, date_to, query=None, limit=50, offset=0,
                              laboratory_id=None, brand_id=None):
        """
        Búsqueda global paginada de productos por nombre/código (case-insensitive),
        devolviendo un subconjunto de campos necesarios para la tabla.
        - No carga todos los productos: aplica limit/offset
        - Filtra opcionalmente por laboratorio y/o marca
        - Devuelve métricas básicas de ventas agregadas en el rango de fechas
        Retorna un dict con:
          {
            'records': [...],
            'has_more': bool,
            'next_offset': int
          }
        """
        Product = self.env['product.product']

        # Construir dominio de productos
        prod_domain = [
            ('active', '=', True),
            ('type', '=', 'product'),
            ('sale_ok', '=', True),
        ]
        if laboratory_id:
            prod_domain.append(('laboratory_id', '=', laboratory_id))
        if brand_id:
            prod_domain.append(('brand_id', '=', brand_id))
        if query:
            q = query.strip()
            # Mejora: dividir la búsqueda en palabras para encontrar productos que contengan
            # todas las palabras de la búsqueda en cualquier parte del nombre, código o códigos alternativos
            words = q.split()
            for word in words:
                word = word.strip()
                if word:
                    # Cada palabra debe estar en el nombre, código principal O en códigos de barras alternativos
                    prod_domain += ['|', '|', ('name', 'ilike', word), 
                                    ('default_code', 'ilike', word),
                                    ('multi_barcode_ids.product_multi_barcode', 'ilike', word)]

        # Buscar ids paginados
        products = Product.search(prod_domain, limit=(limit or 50) + 1, offset=offset or 0)
        product_ids = products.ids[:limit or 50]

        # Detectar si hay más resultados
        has_more = len(products) > (limit or 50)
        next_offset = (offset or 0) + (limit or 50) if has_more else (offset or 0)

        if not product_ids:
            return {'records': [], 'has_more': False, 'next_offset': offset or 0}

        # Agregados básicos de ventas para los productos encontrados
        Summary = self.env['product.warehouse.sale.summary']
        sales_data = Summary.read_group(
            [('date', '>=', date_from), ('date', '<=', date_to),
             ('product_id', 'in', product_ids),
             ('is_legacy_system', '=', True)],
            ['product_id', 'quantity_sold:sum', 'amount_total:sum', 'costo_total:sum'],
            ['product_id']
        )
        sales_map = {rec['product_id'][0]: rec for rec in sales_data}

        # Construir respuesta de registros
        records = []
        for prod in Product.browse(product_ids):
            rec = sales_map.get(prod.id, {})
            quantity_sold = rec.get('quantity_sold', 0)
            amount_total = rec.get('amount_total', 0)
            total_cost = rec.get('costo_total', 0)
            records.append({
                'product_id': prod.id,
                'product_name': prod.name,
                'product_code': prod.default_code or '',
                'id_database_old': prod.product_tmpl_id.id_database_old or '',
                'quantity_sold': quantity_sold,
                'amount_total': amount_total,
                'total_cost': total_cost,
                # Campos adicionales usados por la tabla; valores por defecto si no aplican
                'boxes': 0,
                'units': 0,
                'stock_total': 0,
                'costo_total': total_cost,
                'discount': 0,
                'pvf': 0,
                'uc': 0,
                'cp': 0,
            })

        return {
            'records': records,
            'has_more': has_more,
            'next_offset': next_offset,
        }

    @api.model
    def get_total_sales_summary(self, date_from, date_to, laboratory_id=None,
                                brand_id=None, sales_priority=False,
                                product_query=None, limit=None, offset=0, warehouse_id=None):
        """
        Obtiene resumen de ventas por producto con datos agregados.
        OPTIMIZADO: Elimina N+1 queries usando batch loading para templates y UoM.
        """
        start_time = time.time()

        # Constantes pre-calculadas (evita cálculos repetidos en el loop)
        DISCOUNT_FACTOR = 0.1667  # 16.66 / 100
        DEFAULT_SALES_DATA = {'quantity_sold': 0.0, 'amount_total': 0.0, 'costo_total': 0.0}

        Product = self.env['product.product']

        # Construir dominio base
        base_domain = [
            ('active', '=', True),
            ('type', '=', 'product'),
            ('sale_ok', '=', True),
        ]
        if laboratory_id:
            base_domain.append(('laboratory_id', '=', laboratory_id))
        if brand_id:
            base_domain.append(('brand_id', '=', brand_id))
        # Búsqueda de productos según el modo
        if product_query:
            # Búsqueda por palabras clave (nombre, código y códigos de barras alternativos)
            q = product_query.strip()
            words = q.split()
            domain_with_query = base_domain.copy()
            for word in words:
                word = word.strip()
                if word:
                    # Buscar en: nombre, código principal, y códigos de barras alternativos
                    domain_with_query += ['|', '|', ('name', 'ilike', word),
                                          ('default_code', 'ilike', word),
                                          ('multi_barcode_ids.product_multi_barcode', 'ilike', word)]
            active_products = Product.search(domain_with_query, limit=limit or 50,
                                             offset=offset or 0)
        else:
            # Flujo original: priorizados + no priorizados
            priority_domain = base_domain + [('product_sales_priority', '=', True)]
            priority_products = Product.search(priority_domain)

            if sales_priority:
                active_products = priority_products
            else:
                filtered_domain = base_domain + [('product_sales_priority', '=', False)]
                filtered_products = Product.search(filtered_domain)
                active_products = priority_products + filtered_products

        if not active_products:
            return []

        active_product_ids = active_products.ids

        # =====================================================================
        # PASO 1: Obtener datos de ventas agregados (1 query)
        # =====================================================================
        Summary = self.env['product.warehouse.sale.summary']
        sales_domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('product_id', 'in', active_product_ids),
            ('is_legacy_system', '=', True),
        ]
        if warehouse_id:
            sales_domain.append(('warehouse_id', '=', warehouse_id))

        sales_data = Summary.read_group(
            sales_domain,
            ['product_id', 'quantity_sold:sum', 'amount_total:sum', 'costo_total:sum'],
            ['product_id']
        )
        summary_map = {
            s['product_id'][0]: {
                'quantity_sold': s['quantity_sold'],
                'amount_total': s['amount_total'],
                'costo_total': s['costo_total'],
            } for s in sales_data
        }

        # =====================================================================
        # PASO 2: Leer productos con campos necesarios (1 query)
        # =====================================================================
        products = active_products.read([
            'default_code', 'brand_id', 'laboratory_id', 'name', 'uom_id',
            'uom_po_id', 'discount', 'standard_price', 'list_price', 'price_with_tax',
            'product_sales_priority', 'currency_id', 'taxes_id', 'product_tmpl_id'
        ])

        # =====================================================================
        # PASO 3: PRE-CARGAR TEMPLATES EN BATCH (elimina N+1 query)
        # =====================================================================
        template_ids = [p['product_tmpl_id'][0] for p in products if p.get('product_tmpl_id')]
        if template_ids:
            templates_data = self.env['product.template'].browse(template_ids).read([
                'id', 'id_database_old', 'price_with_tax', 'standar_price_old',
                'avg_standar_price_old', 'list_price', 'sales_stock_total'
            ])
            template_map = {t['id']: t for t in templates_data}
        else:
            template_map = {}

        # =====================================================================
        # PASO 4: PRE-CARGAR UOM RATIOS EN BATCH (elimina N+1 query)
        # =====================================================================
        uom_ids = [p['uom_po_id'][0] for p in products if p.get('uom_po_id')]
        if uom_ids:
            uom_data = self.env['uom.uom'].browse(uom_ids).read(['id', 'ratio'])
            uom_ratio_map = {u['id']: u['ratio'] for u in uom_data}
        else:
            uom_ratio_map = {}

        # =====================================================================
        # PASO 5: Stock por bodega (condicional, 1 query)
        # =====================================================================
        stock_map = {}
        if warehouse_id:
            warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            if warehouse.exists() and warehouse.lot_stock_id:
                stock_data = self.env['stock.quant'].read_group(
                    [
                        ('product_id', 'in', active_product_ids),
                        ('location_id', 'child_of', warehouse.lot_stock_id.id),
                    ],
                    ['product_id', 'quantity:sum'],
                    ['product_id']
                )
                stock_map = {rec['product_id'][0]: rec.get('quantity', 0.0) for rec in stock_data}

        # =====================================================================
        # PASO 6: Datos de reabastecimiento Bodega Matilde (1-2 queries)
        # =====================================================================
        matilde_qty_map = {}
        matilde_op_map = {}
        matilde_warehouse = self.env['stock.warehouse'].search(
            [('code', '=', 'BODMA')], limit=1
        )
        if matilde_warehouse and matilde_warehouse.lot_stock_id:
            Orderpoint = self.env['stock.warehouse.orderpoint']
            matilde_orderpoints = Orderpoint.search([
                ('product_id', 'in', active_product_ids),
                ('location_id', '=', matilde_warehouse.lot_stock_id.id),
            ])
            for op in matilde_orderpoints:
                matilde_qty_map[op.product_id.id] = op.qty_to_order
                matilde_op_map[op.product_id.id] = op.id

        # =====================================================================
        # PASO 7: Pendiente de recibir (OC/Cotizaciones) - 1 query
        # =====================================================================
        pending_qty_map = {}
        try:
            POLine = self.env['purchase.order.line']
            # Estados: draft=cotización, sent=enviada, purchase=confirmada
            po_lines = POLine.search([
                ('product_id', 'in', active_product_ids),
                ('order_id.state', 'in', ['draft', 'sent', 'purchase']),
            ])
            for line in po_lines:
                pending = line.product_qty - line.qty_received
                if pending > 0:
                    product_id = line.product_id.id
                    pending_qty_map[product_id] = pending_qty_map.get(product_id, 0) + pending
        except Exception as e:
            _logger.warning("Error obteniendo cantidades pendientes de OC: %s", e)

        # =====================================================================
        # PASO 8: Construir resultados (sin queries adicionales en el loop)
        # =====================================================================
        results = []
        for product in products:
            product_id = product['id']
            data = summary_map.get(product_id,
                                   {'quantity_sold': 0.0,
                                    'amount_total': 0.0,
                                    'costo_total': 0.0})
            quantity_sold = data['quantity_sold']
            costo_total = data['costo_total']
            stock_qty = stock_map.get(product_id, 0.0) if warehouse_id else 0.0

            # Obtener datos del template desde el mapa pre-cargado (SIN query)
            tmpl_id = product.get('product_tmpl_id', (0,))[0] if product.get('product_tmpl_id') else 0
            tmpl_data = template_map.get(tmpl_id, {})

            # Obtener ratio de UoM desde el mapa pre-cargado (SIN query)
            uom_po_id = product.get('uom_po_id', (0,))[0] if product.get('uom_po_id') else 0
            uom_po_ratio = uom_ratio_map.get(uom_po_id, 1.0) or 1.0

            if uom_po_ratio and uom_po_ratio != 0:
                if warehouse_id:
                    boxes = math.floor(stock_qty / uom_po_ratio)
                    units = round(stock_qty - (boxes * uom_po_ratio), 3)
                else:
                    boxes = quantity_sold // uom_po_ratio
                    units = quantity_sold % uom_po_ratio
            else:
                boxes = 0
                units = stock_qty if warehouse_id else quantity_sold
            if quantity_sold == 0 or costo_total == 0:
                # si no se vendio nada o el costo es cero, no se calcula utilidad
                # ni precio con impuestos
                product_utility = 0
                price_with_taxes = 0
            else:
                # calculo dee precio con impuestos y descuentos y utlidad
                # amount_unit = data['amount_total'] / quantity_sold
                product_utility = (data[
                                       'amount_total'] - costo_total) / costo_total
            utility_percent = product_utility * 100
            # utility_total = f"{utility_percent:.2f}"
            truncado = math.floor(round(utility_percent, 2) * 10) / 10
            product_name = product.get('name',
                                       '') if not sales_priority else product.get(
                'name', '') + ' - ' + product.get('brand_id', (0, ''))[1]
            # Obtener valores del template desde el mapa (SIN query)
            list_price = product.get('list_price', 0)
            standar_price_old = tmpl_data.get('standar_price_old', 0) or 0
            avg_standar_price_old = tmpl_data.get('avg_standar_price_old', 0) or 0
            price_with_taxes = tmpl_data.get('price_with_tax', 0) or 0

            # Calcular PVF y cambio de costo promedio
            pvf = 0
            change_average_cost = 0
            percentage_change_average_cost = 0

            if avg_standar_price_old <= 0.01 and standar_price_old != 0.01:
                pvf = list_price * (1 - DISCOUNT_FACTOR)
                change_average_cost = (pvf - standar_price_old) / standar_price_old
                percentage_change_average_cost = change_average_cost * 100
            elif avg_standar_price_old <= 0.01 and standar_price_old <= 0.01:
                percentage_change_average_cost = 0
            elif avg_standar_price_old > 0.01:
                pvf = list_price * (1 - DISCOUNT_FACTOR)
                change_average_cost = (pvf - avg_standar_price_old) / avg_standar_price_old
                percentage_change_average_cost = change_average_cost * 100
            # Stock total
            stock_total = stock_map.get(product_id, 0.0) if warehouse_id else (tmpl_data.get('sales_stock_total', 0.0) or 0.0)

            results.append({
                'product_id': product_id,
                'product_code': product.get('default_code', ''),
                'id_database_old': tmpl_data.get('id_database_old', '') or '',
                'brand': product.get('brand_id', (0, ''))[1] if isinstance(
                    product.get('brand_id'), tuple) else '',
                'brand_id': product.get('brand_id', (0, ''))[0] if isinstance(
                    product.get('brand_id'), tuple) else 0,
                'laboratory_id': product.get('laboratory_id', (0, ''))[0] if isinstance(
                    product.get('laboratory_id'), tuple) else '',
                'product_name': product_name.lower().title(),
                'quantity_sold': quantity_sold,
                'amount_total': round(data['amount_total'], 3),
                'total_cost': round(data['costo_total'], 3),
                'boxes': boxes,
                'units': units,
                'uom': product.get('uom_id', (0, ''))[1] if isinstance(
                    product.get('uom_id'), tuple) else '',
                'uom_po_id': product.get('uom_po_id', (0, ''))[1] if isinstance(
                    product.get('uom_po_id'), tuple) else '',
                'uom_factor': uom_po_ratio,
                'stock_total': stock_total,
                'standard_price': standar_price_old,
                'list_price': list_price,
                'discount': product.get('discount', 0),
                'utility': truncado,
                'pvf': round(pvf, 2),
                'product_sales_priority': product.get('product_sales_priority', False),
                'price_with_taxes': price_with_taxes,
                'change_average_cost': change_average_cost,
                'percentage_change_average_cost': round(percentage_change_average_cost, 2),
                'standar_price_old': round(standar_price_old, 3),
                'avg_standar_price_old': round(avg_standar_price_old, 3) if avg_standar_price_old > 0 else standar_price_old,
                'matilde_qty_to_order': matilde_qty_map.get(product_id, 0.0),
                'matilde_orderpoint_id': matilde_op_map.get(product_id),
                'pending_qty': pending_qty_map.get(product_id, 0.0),
            })

        results.sort(key=lambda x: (not x['product_sales_priority'],
                                    x['product_name'].lower()))
        end_time = time.time()
        _logger.info(f"get_total_sales_summary: {end_time - start_time:.3f}s para {len(results)} productos")

        return results

    @api.model
    def get_multibarcode_info(self, product_id, exclude_code=None):
        """
        Obtiene todos los códigos de barras alternativos de un producto.

        Args:
            product_id: ID del producto
            exclude_code: Código a excluir (generalmente el product_code que ya se muestra)

        Returns:
            dict: {'long_codes': [], 'short_codes': []}
            - long_codes: códigos con más de 6 dígitos (EAN-13, EAN-8, etc.)
            - short_codes: códigos con 6 dígitos o menos (códigos internos)
        """
        result = {'long_codes': [], 'short_codes': []}

        product = self.env['product.product'].browse(product_id)

        if not product:
            return result

        # Obtener todos los códigos de barras
        all_barcodes = product.multi_barcode_ids.filtered(
            lambda b: b.product_multi_barcode
        )

        if not all_barcodes:
            return result

        # Excluir el código que ya aparece en product_code (si se proporciona)
        if exclude_code:
            exclude_code_clean = exclude_code.strip()
            all_barcodes = all_barcodes.filtered(
                lambda b: b.product_multi_barcode.strip() != exclude_code_clean
            )

        if not all_barcodes:
            return result

        # Separar códigos por longitud
        for barcode in all_barcodes:
            code = barcode.product_multi_barcode.strip()
            if len(code) <= 6:
                result['short_codes'].append(code)
            else:
                result['long_codes'].append(code)

        # Ordenar cada lista: largos por longitud desc, cortos por longitud desc
        result['long_codes'] = sorted(result['long_codes'], key=lambda x: (-len(x), x))
        result['short_codes'] = sorted(result['short_codes'], key=lambda x: (-len(x), x))

        return result


    @api.model
    def get_today_sales_summary(self, limit=20, offset=0, date_from=None, date_to=None):
        """
        Obtiene resumen de ventas con paginación para un rango de fechas.
        Si no se especifican fechas, usa el día actual.

        Args:
            limit: Número máximo de productos a retornar (default 50)
            offset: Número de productos a saltar para paginación (default 0)
            date_from: Fecha inicio del rango (string 'YYYY-MM-DD' o None para hoy)
            date_to: Fecha fin del rango (string 'YYYY-MM-DD' o None para hoy)

        Returns:
            dict: {
                'records': [...],  # Lista de productos con datos de ventas
                'has_more': bool,  # Si hay más resultados
                'next_offset': int,  # Offset para la siguiente página
                'total_count': int,  # Total de productos con ventas
                'date_from': str,  # Fecha inicio del rango
                'date_to': str  # Fecha fin del rango
            }
        """
        start_time = time.time()
        today = fields.Date.today()
        print(date_from,date_to,'++++++++++++++')

        # Procesar fechas: si no vienen, usar fecha actual
        if date_from:
            if isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
        else:
            date_from = today

        if date_to:
            if isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)
        else:
            date_to = today

        # Construir dominio de fechas
        if date_from == date_to:
            date_domain = [('date', '=', date_from)]
        else:
            date_domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        print(date_domain,limit,offset,'------------------')
        # Constantes pre-calculadas
        DISCOUNT_FACTOR = 0.1667
        DEFAULT_SALES_DATA = {'quantity_sold': 0.0, 'amount_total': 0.0, 'costo_total': 0.0}

        # =====================================================================
        # PASO 1: Obtener productos con ventas ORDENADOS por quantity_sold
        # =====================================================================
        Summary = self.env['product.warehouse.sale.summary']

        # Obtener todos los productos con ventas agregando todos los campos necesarios
        base_domain = date_domain + [('is_legacy_system', '=', True)]
        all_sales_data = Summary.read_group(
            base_domain,
            ['product_id', 'quantity_sold:sum', 'amount_total:sum', 'costo_total:sum'],
            ['product_id'],
            orderby='quantity_sold desc'
        )

        # Ordenar por quantity_sold descendente (respaldo si orderby no funciona en read_group)
        all_sales_sorted = sorted(
            all_sales_data,
            key=lambda x: x.get('quantity_sold', 0) or 0,
            reverse=True
        )

        total_count = len(all_sales_sorted)

        if not all_sales_sorted:
            return {
                'records': [],
                'has_more': False,
                'next_offset': 0,
                'total_count': 0,
                'date_from': str(date_from),
                'date_to': str(date_to)
            }

        # Aplicar paginación a la lista ordenada
        paginated_sales = all_sales_sorted[offset:offset + limit + 1]
        has_more = len(paginated_sales) > limit
        page_sales = paginated_sales[:limit]

        # Extraer IDs de productos para esta página (mantener orden)
        product_ids_page = [s['product_id'][0] for s in page_sales if s.get('product_id')]

        if not product_ids_page:
            return {
                'records': [],
                'has_more': False,
                'next_offset': offset,
                'total_count': total_count,
                'date_from': str(date_from),
                'date_to': str(date_to)
            }

        # Crear mapa de ventas con todos los campos desde los datos ya obtenidos
        summary_map = {
            s['product_id'][0]: {
                'quantity_sold': s.get('quantity_sold', 0) or 0,
                'amount_total': s.get('amount_total', 0) or 0,
                'costo_total': s.get('costo_total', 0) or 0,
            } for s in page_sales if s.get('product_id')
        }

        # =====================================================================
        # PASO 2: Leer productos con campos necesarios
        # =====================================================================
        Product = self.env['product.product']
        products = Product.browse(product_ids_page).read([
            'default_code', 'brand_id', 'laboratory_id', 'name', 'uom_id',
            'uom_po_id', 'discount', 'standard_price', 'list_price', 'price_with_tax',
            'product_sales_priority', 'currency_id', 'taxes_id', 'product_tmpl_id'
        ])

        # =====================================================================
        # PASO 3: PRE-CARGAR TEMPLATES EN BATCH
        # =====================================================================
        template_ids = [p['product_tmpl_id'][0] for p in products if p.get('product_tmpl_id')]
        if template_ids:
            templates_data = self.env['product.template'].browse(template_ids).read([
                'id', 'id_database_old', 'price_with_tax', 'standar_price_old',
                'avg_standar_price_old', 'list_price', 'sales_stock_total'
            ])
            template_map = {t['id']: t for t in templates_data}
        else:
            template_map = {}

        # =====================================================================
        # PASO 4: PRE-CARGAR UOM RATIOS EN BATCH
        # =====================================================================
        uom_ids = [p['uom_po_id'][0] for p in products if p.get('uom_po_id')]
        if uom_ids:
            uom_data = self.env['uom.uom'].browse(uom_ids).read(['id', 'ratio'])
            uom_ratio_map = {u['id']: u['ratio'] for u in uom_data}
        else:
            uom_ratio_map = {}

        # =====================================================================
        # PASO 5: Construir resultados (sin queries adicionales en el loop)
        # =====================================================================
        results = []
        for product in products:
            product_id = product['id']
            data = summary_map.get(product_id, DEFAULT_SALES_DATA)
            quantity_sold = data['quantity_sold']
            costo_total = data['costo_total']
            amount_total = data['amount_total']

            # Obtener datos del template desde el mapa
            tmpl_id = product.get('product_tmpl_id', (0,))[0] if product.get('product_tmpl_id') else 0
            tmpl_data = template_map.get(tmpl_id, {})

            # Obtener ratio de UoM desde el mapa
            uom_po_id = product.get('uom_po_id', (0,))[0] if product.get('uom_po_id') else 0
            uom_po_ratio = uom_ratio_map.get(uom_po_id, 1.0) or 1.0

            # Calcular boxes/units basado en cantidad vendida
            if uom_po_ratio and uom_po_ratio != 0:
                boxes = quantity_sold // uom_po_ratio
                units = quantity_sold % uom_po_ratio
            else:
                boxes = 0
                units = quantity_sold

            # Calcular utilidad
            if quantity_sold == 0 or costo_total == 0:
                product_utility = 0
            else:
                product_utility = (amount_total - costo_total) / costo_total

            utility_percent = product_utility * 100
            truncado = math.floor(round(utility_percent, 2) * 10) / 10

            # Obtener valores del template
            list_price = product.get('list_price', 0)
            standar_price_old = tmpl_data.get('standar_price_old', 0) or 0
            avg_standar_price_old = tmpl_data.get('avg_standar_price_old', 0) or 0
            price_with_taxes = tmpl_data.get('price_with_tax', 0) or 0
            stock_total = tmpl_data.get('sales_stock_total', 0.0) or 0.0

            # Calcular PVF y cambio de costo promedio
            pvf = 0
            change_average_cost = 0
            percentage_change_average_cost = 0

            if avg_standar_price_old <= 0 and standar_price_old != 0:
                pvf = list_price * (1 - DISCOUNT_FACTOR)
                change_average_cost = (pvf - standar_price_old) / standar_price_old
                percentage_change_average_cost = change_average_cost * 100
            elif avg_standar_price_old <= 0 and standar_price_old <= 0:
                percentage_change_average_cost = 0
            elif avg_standar_price_old > 0:
                pvf = list_price * (1 - DISCOUNT_FACTOR)
                change_average_cost = (pvf - avg_standar_price_old) / avg_standar_price_old
                percentage_change_average_cost = change_average_cost * 100

            results.append({
                'product_id': product_id,
                'product_code': product.get('default_code', ''),
                'id_database_old': tmpl_data.get('id_database_old', '') or '',
                'brand': product.get('brand_id', (0, ''))[1] if isinstance(
                    product.get('brand_id'), tuple) else '',
                'brand_id': product.get('brand_id', (0, ''))[0] if isinstance(
                    product.get('brand_id'), tuple) else 0,
                'laboratory_id': product.get('laboratory_id', (0, ''))[0] if isinstance(
                    product.get('laboratory_id'), tuple) else '',
                'product_name': product.get('name', '').lower().title(),
                'quantity_sold': quantity_sold,
                'amount_total': round(amount_total, 3),
                'total_cost': round(costo_total, 3),
                'boxes': boxes,
                'units': units,
                'uom': product.get('uom_id', (0, ''))[1] if isinstance(
                    product.get('uom_id'), tuple) else '',
                'uom_po_id': product.get('uom_po_id', (0, ''))[1] if isinstance(
                    product.get('uom_po_id'), tuple) else '',
                'uom_factor': uom_po_ratio,
                'stock_total': stock_total,
                'standard_price': standar_price_old,
                'list_price': list_price,
                'discount': product.get('discount', 0),
                'utility': truncado,
                'pvf': round(pvf, 2),
                'product_sales_priority': product.get('product_sales_priority', False),
                'price_with_taxes': price_with_taxes,
                'change_average_cost': change_average_cost,
                'percentage_change_average_cost': round(percentage_change_average_cost, 2),
                'standar_price_old': round(standar_price_old, 3),
                'avg_standar_price_old': round(avg_standar_price_old, 3) if avg_standar_price_old > 0 else standar_price_old,
            })

        # Ordenar por cantidad vendida (mayor primero) y luego por nombre
        results.sort(key=lambda x: (-x['quantity_sold'], x['product_name'].lower()))

        end_time = time.time()
        _logger.info(f"get_today_sales_summary: {end_time - start_time:.3f}s para {len(results)} productos")

        return {
            'records': results,
            'has_more': has_more,
            'next_offset': offset + limit if has_more else offset,
            'total_count': total_count,
            'date_from': str(date_from),
            'date_to': str(date_to)
        }

    def get_price_with_taxes(self, product_id, quantity=1):
        product = self.env['product.product'].browse(product_id)
        taxes = product.taxes_id
        if taxes:
            tax_result = taxes.compute_all(
                product.list_price,
                quantity=quantity,
                product=product
            )
            return tax_result['total_included']
        return product.list_price

    @api.model
    def get_total_sales_by_laboratory(self, date_from, date_to, limit=80, offset=0,
                                      search_query=None):
        """Versão otimizada: pagina diretamente sobre laboratórios.

        Em vez de calcular todos e depois cortar (ineficiente), busca a página de
        laboratórios (limit/offset + filtro de nome) e só então agrega vendas
        e estoque para aqueles IDs.
        Retorna mesmo formato anterior para manter compatibilidade frontend.
        """
        Lab = self.env['product.laboratory']
        Product = self.env['product.product']
        Template = self.env['product.template']

        lab_domain = []
        if search_query:
            lab_domain.append(('name', 'ilike', search_query))

        total_count = Lab.search_count(lab_domain)
        labs = Lab.search(lab_domain, limit=limit or None, offset=offset, order='name asc')
        if not labs:
            return {
                'records': [],
                'has_more': False,
                'next_offset': offset,
                'total_count': total_count,
            }

        products = Product.search([
            ('laboratory_id', 'in', labs.ids),
            ('active', '=', True),
            ('type', '=', 'product')
        ])
        if not products:
            # Mesmo sem produtos retornamos metadados para scroll continuar
            has_more = (offset + (limit or 0)) < total_count if limit else False
            return {
                'records': [],
                'has_more': has_more,
                'next_offset': (offset + (limit or 0)) if has_more else total_count,
                'total_count': total_count,
            }

        Summary = self.env['product.warehouse.sale.summary']
        sales_data = Summary.read_group(
            [
                ('date', '>=', date_from), ('date', '<=', date_to),
                ('product_id', 'in', products.ids),
                ('is_legacy_system', '=', True)
            ],
            ['product_id', 'quantity_sold:sum', 'amount_total:sum', 'costo_total:sum'],
            ['product_id']
        )
        sales_map = {s['product_id'][0]: s for s in sales_data}

        templates = Template.browse(products.mapped('product_tmpl_id').ids)
        tmpl_map = {t.id: t for t in templates}

        # Mapear produtos por laboratório (só labs desta página)
        products_by_lab = {}
        for prod in products:
            products_by_lab.setdefault(prod.laboratory_id.id, []).append(prod)

        records = []
        for lab in labs:
            prods_lab = products_by_lab.get(lab.id, [])
            qty = amt = cost = stock_total = 0.0
            for p in prods_lab:
                s = sales_map.get(p.id, {})
                qty += s.get('quantity_sold', 0.0)
                amt += s.get('amount_total', 0.0)
                cost += s.get('costo_total', 0.0)
                tmpl = tmpl_map.get(p.product_tmpl_id.id)
                if tmpl:
                    # Verificação de segurança para o campo sales_stock_total
                    try:
                        stock_value = tmpl.sales_stock_total or 0.0
                        stock_total += stock_value
                    except AttributeError:
                        # Campo não existe ou não está acessível
                        stock_total += 0.0
                    except Exception:
                        # Qualquer outro erro
                        stock_total += 0.0

            if cost > 0:
                utilidad_bruta = amt - cost
                util_pct = (utilidad_bruta * 100) / cost if cost else 0.0
            else:
                util_pct = 0.0

            records.append({
                'laboratory_id': lab.id,
                'product_id': None,
                'product_name': lab.name,
                'quantity_sold': round(qty, 3),
                'amount_total': round(amt, 3),
                'total_cost': round(cost, 3),
                'boxes': 0.0,
                'units': 0.0,
                'stock_total': round(stock_total, 3),
                'discount': 0.0,
                'utility': round(util_pct, 3),
                'pvf': 0.0,
                'percentage_change_average_cost': 0.0,
            })

        # Orden já garantida pelo search, mas garantimos ordenação por nome (case-insensitive)
        records.sort(key=lambda r: r['product_name'].lower())
        if search_query:
            # (já filtrado via domain, mas mantemos compatibilidade)
            pass

        if limit:
            next_offset = offset + len(labs)
            has_more = next_offset < total_count
        else:
            next_offset = total_count
            has_more = False

        return {
            'records': records,
            'has_more': has_more,
            'next_offset': next_offset,
            'total_count': total_count,
        }

    @api.model
    def get_products_by_laboratories_for_export(self, date_from, date_to):
        """
        Obtiene TODOS los productos de TODOS los laboratorios para exportación a Excel.
        Retorna solo 6 columnas: COD ITEM, LABORATORIO, producto, UNIDADES POR CAJA, cantidad vendida, stock.

        Args:
            date_from: Fecha de inicio del período
            date_to: Fecha de fin del período

        Returns:
            Lista de productos con las 6 columnas requeridas
        """
        start_time = time.time()

        Lab = self.env['product.laboratory']
        Product = self.env['product.product']

        # Obtener TODOS los laboratorios
        labs = Lab.search([], order='name asc')

        if not labs:
            return []

        # Obtener todos los productos de todos los laboratorios
        products = Product.search([
            ('laboratory_id', 'in', labs.ids),
            ('active', '=', True),
            ('type', '=', 'product'),
            ('sale_ok', '=', True),
        ])

        if not products:
            return []

        active_product_ids = products.ids

        # Obtener datos de ventas agregados
        Summary = self.env['product.warehouse.sale.summary']
        sales_data = Summary.read_group(
            [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('product_id', 'in', active_product_ids),
                ('is_legacy_system', '=', True),
            ],
            ['product_id', 'quantity_sold:sum'],
            ['product_id']
        )
        summary_map = {s['product_id'][0]: s['quantity_sold'] for s in sales_data}

        # Leer productos con campos necesarios
        products_data = products.read([
            'default_code', 'laboratory_id', 'name', 'uom_po_id', 'product_tmpl_id'
        ])

        # Pre-cargar templates para stock
        template_ids = [p['product_tmpl_id'][0] for p in products_data if p.get('product_tmpl_id')]
        if template_ids:
            templates_data = self.env['product.template'].browse(template_ids).read([
                'id', 'sales_stock_total'
            ])
            template_map = {t['id']: t for t in templates_data}
        else:
            template_map = {}

        # Pre-cargar UOM ratios
        uom_ids = [p['uom_po_id'][0] for p in products_data if p.get('uom_po_id')]
        if uom_ids:
            uom_data = self.env['uom.uom'].browse(uom_ids).read(['id', 'ratio'])
            uom_ratio_map = {u['id']: u['ratio'] for u in uom_data}
        else:
            uom_ratio_map = {}

        # Mapa de laboratorios para nombres
        lab_map = {lab.id: lab.name for lab in labs}

        results = []
        for product in products_data:
            # Obtener datos del template
            tmpl_id = product.get('product_tmpl_id', (0,))[0] if product.get('product_tmpl_id') else 0
            tmpl_data = template_map.get(tmpl_id, {})

            # Obtener ratio de UoM (unidades por caja)
            uom_po_id = product.get('uom_po_id', (0,))[0] if product.get('uom_po_id') else 0
            uom_po_ratio = uom_ratio_map.get(uom_po_id, 1.0) or 1.0

            # Obtener nombre del laboratorio
            lab_id = product.get('laboratory_id', (0, ''))[0] if isinstance(product.get('laboratory_id'), tuple) else 0
            laboratory_name = lab_map.get(lab_id, '')

            # Cantidad vendida
            quantity_sold = summary_map.get(product['id'], 0.0)

            # Stock total
            stock_total = tmpl_data.get('sales_stock_total', 0.0) or 0.0

            results.append({
                'product_code': product.get('default_code', ''),
                'laboratory': laboratory_name,
                'product_name': product.get('name', '').lower().title(),
                'units_per_box': round(uom_po_ratio, 2),
                'quantity_sold': round(quantity_sold, 3),
                'stock': round(stock_total, 3),
            })

        # Ordenar por laboratorio y luego por nombre de producto
        results.sort(key=lambda x: (x['laboratory'].lower(), x['product_name'].lower()))

        end_time = time.time()
        _logger.info(f"get_products_by_laboratories_for_export: {end_time - start_time:.3f}s para {len(results)} productos")

        return results

    # @api.model
    # def get_stock_by_warehouse(self, product_id, date_from, date_to):
    #     """
    #     CRITICAL OPTIMIZATION: This function was completely rewritten to solve
    #     the performance issue that caused 4 seconds of loading time.

    #     ORIGINAL PROBLEM:
    #     - N+1 Query: One query was executed per warehouse individually
    #     - If there were 10 warehouses = 11 database queries
    #     - Each individual query to stock.quant was slow

    #     IMPLEMENTED SOLUTION:
    #     - Only 2 main database queries
    #     - Use of read_group to optimize aggregations
    #     - Data maps for fast access without additional queries
    #     """
    #     Warehouse = self.env['stock.warehouse']
    #     Quant = self.env['stock.quant']
    #     product_product = self.env['product.product'].browse(product_id)

    #     result = []

    #     # QUERY 1: Get all sales grouped by warehouse for the given product
    #     # This query was already optimized with read_group
    #     sales_summary_all = self.env[
    #         'product.warehouse.sale.summary'].read_group(
    #         [
    #             ('date', '>=', date_from),
    #             ('date', '<=', date_to),
    #             ('product_id', '=', product_id),
    #             ('is_legacy_system', '=', True)
    #         ],
    #         ['warehouse_id', 'quantity_sold:sum'],
    #         ['warehouse_id']
    #     )
    #     # Convert the result to a dict for fast access by warehouse_id
    #     sales_by_warehouse = {
    #         summary['warehouse_id'][0]: summary.get('quantity_sold', 0)
    #         for summary in sales_summary_all if summary.get('warehouse_id')
    #     }

    #     # OPTIMIZATION 1: Get all warehouses at once with their locations
    #     # BEFORE: Iterated over Warehouse.search([]) and made individual query for each one
    #     # NOW: Single query to get all warehouses and create location map
    #     warehouses = Warehouse.search([])
    #     warehouse_locations = {w.id: w.lot_stock_id.id for w in warehouses}

    #     # OPTIMIZATION 2: Get all stock at once using read_group
    #     # BEFORE: For each warehouse it executed: Quant.search([...]) individually
    #     # NOW: Single read_group query that gets all stock grouped by location_id
    #     # THIS COMPLETELY ELIMINATES THE N+1 PROBLEM
    #     stock_data = Quant.read_group(
    #         [
    #             ('product_id', '=', product_id),
    #             ('location_id', 'in', list(warehouse_locations.values()))
    #         ],
    #         ['location_id', 'quantity:sum'],
    #         ['location_id']
    #     )

    #     # OPTIMIZATION 3: Create stock map by location_id for O(1) access
    #     # Instead of making individual queries, we use a dictionary for fast access
    #     stock_by_location = {
    #         item['location_id'][0]: item['quantity'] 
    #         for item in stock_data if item.get('location_id')
    #     }

    #     # OPTIMIZATION 4: Create warehouse_id map by location_id for fast access
    #     # This allows quick mapping between locations and warehouses
    #     location_to_warehouse = {loc_id: wh_id for wh_id, loc_id in warehouse_locations.items()}

    #     # OPTIMIZATION 5: Iterate over warehouses using pre-calculated data
    #     # BEFORE: Each iteration made an individual database query
    #     # NOW: We only access pre-calculated data maps
    #     for warehouse in warehouses:
    #         location_id = warehouse_locations[warehouse.id]
    #         qty_sold = sales_by_warehouse.get(warehouse.id, 0)

    #         # OPTIMIZATION 6: Use pre-calculated stock instead of individual query
    #         # BEFORE: qty_available = sum(Quant.search([...]).mapped('quantity'))
    #         # NOW: Direct access to data map
    #         qty_available = stock_by_location.get(location_id, 0)

    #         result.append({
    #             'warehouse_id': warehouse.id,
    #             'warehouse_name': warehouse.name.lower().title(),
    #             'total_sold': qty_sold,
    #             'warehouse_sequence': warehouse.sequence,
    #             'uom': f"x {int(product_product.uom_po_id.ratio)}",
    #             'stock': qty_available if qty_available > 0 else 0,
    #             'boxes': qty_available // product_product.uom_po_id.ratio if qty_available > 0 else 0,
    #             'units': qty_available % product_product.uom_po_id.ratio if qty_available > 0 else 0
    #         })

    #     result.sort(key=lambda x: x['warehouse_sequence'])

    #     return result

    # def _get_warehouse_from_location_id(self, location_id):

    #     warehouse = self.env['stock.warehouse'].search([
    #         ('lot_stock_id', 'child_of', location_id)
    #     ], limit=1)

    #     return warehouse

    @api.model
    def get_stock_by_warehouse(self, product_id, date_from, date_to):
        """
        Optimiza la consulta de stock y ventas por almacén para un producto,
        usando agregaciones en una sola consulta para stock y ventas.
        """
        Warehouse = self.env['stock.warehouse']
        Quant = self.env['stock.quant']
        product_product = self.env['product.product'].browse(product_id)

        # Consulta todas las ventas agrupadas por almacén
        sales_summary_all = self.env['product.warehouse.sale.summary'].read_group(
            [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('product_id', '=', product_id),
                ('is_legacy_system', '=', True)
            ],
            ['warehouse_id', 'quantity_sold:sum'],
            ['warehouse_id']
        )
        sales_by_warehouse = {
            summary['warehouse_id'][0]: summary.get('quantity_sold', 0)
            for summary in sales_summary_all if summary.get('warehouse_id')
        }

        # Obtén todos los almacenes y sus ubicaciones principales
        warehouses = Warehouse.search([('company_id', '=', 1), ])
        warehouse_locations = {w.id: w.lot_stock_id.id for w in warehouses}

        # Consulta el stock agrupado por ubicación en una sola query
        stock_data = Quant.read_group(
            [
                ('product_id', '=', product_id),
                ('location_id', 'in', list(warehouse_locations.values()))
            ],
            ['location_id', 'quantity:sum'],
            ['location_id']
        )
        # stock_data = [data for data in stock_data if data['quantity'] > 0]
        stock_by_location = {
            item['location_id'][0]: item['quantity']
            for item in stock_data if item.get('location_id')
        }

        result = []
        for warehouse in warehouses:
            location_id = warehouse_locations[warehouse.id]
            qty_sold = sales_by_warehouse.get(warehouse.id, 0)
            qty_available = stock_by_location.get(location_id, 0)
            result.append({
                'warehouse_id': warehouse.id,
                'warehouse_name': warehouse.name.lower().title(),
                'total_sold': qty_sold,
                'warehouse_sequence': warehouse.sequence,
                'uom': f"x {int(product_product.uom_po_id.ratio)}",
                'stock': qty_available if qty_available else 0,
                'boxes': qty_available // product_product.uom_po_id.ratio if qty_available else 0,
                'units': qty_available % product_product.uom_po_id.ratio if qty_available else 0
            })
        result.sort(key=lambda x: x['warehouse_sequence'])
        return result

    def _get_warehouse_from_location_id(self, location_id):

        warehouse = self.env['stock.warehouse'].search([
            ('lot_stock_id', 'child_of', location_id)
        ], limit=1)

        return warehouse

    @api.model
    def get_product_sales_totals(self, product_id, date_start, date_end):
        """
        Retorna el total de cantidad vendida y monto total para un producto en un rango de fechas.

        :param product_id: ID del product.prodcut (int)
        :param date_start: Fecha de inicio (str o date, formato 'YYYY-MM-DD')
        :param date_end: Fecha de fin (str o date, formato 'YYYY-MM-DD')
        :return: Diccionario con totales de quantity_sold y amount_total
        """
        # Convertir fechas a objetos date si son cadenas
        if isinstance(date_start, str):
            date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
        if isinstance(date_end, str):
            date_end = datetime.strptime(date_end, '%Y-%m-%d').date()

        # Buscar registros en el rango de fechas para el producto
        domain = [
            ('product_id', '=', product_id),
            ('date', '>=', date_start),
            ('date', '<=', date_end),
        ]
        sale_summaries = self.search(domain)

        # Sumar quantity_sold y amount_total
        total_quantity_sold = sum(sale_summaries.mapped('quantity_sold'))
        total_amount = sum(sale_summaries.mapped('amount_total'))

        return {
            'product_id': product_id,
            'total_quantity_sold': total_quantity_sold,
            'total_amount': total_amount,
            'uom_id': sale_summaries[0].uom_id.id if sale_summaries else False,
        }

    @api.model
    def get_stock_by_warehouse_laboratory(self, laboratory_id, date_from, date_to):
        """Retorna vendas e estoque agregados por warehouse para todos os produtos de um laboratório."""
        if not laboratory_id:
            return []
        Product = self.env['product.product']
        Quant = self.env['stock.quant']
        Warehouse = self.env['stock.warehouse']
        products = Product.search([
            ('laboratory_id', '=', laboratory_id),
            ('active', '=', True),
            ('type', '=', 'product')
        ])
        if not products:
            return []

        # Agrupa vendas por product + warehouse
        sales_summary = self.env['product.warehouse.sale.summary'].read_group(
            [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('product_id', 'in', products.ids),
                ('is_legacy_system', '=', True)
            ],
            ['warehouse_id', 'quantity_sold:sum', 'amount_total:sum', 'costo_total:sum'],
            ['warehouse_id']
        )
        sales_map = {s['warehouse_id'][0]: s for s in sales_summary if s.get('warehouse_id')}

        result = []
        for warehouse in Warehouse.search([]):
            # estoque total dos produtos do laboratório nesse warehouse
            location = warehouse.lot_stock_id
            quants = Quant.read_group(
                [
                    ('product_id', 'in', products.ids),
                    ('location_id', 'child_of', location.id)
                ],
                ['quantity:sum'],
                []
            )
            qty_available = quants[0]['quantity'] if quants else 0.0
            sales = sales_map.get(warehouse.id, {})
            qty_sold = sales.get('quantity_sold', 0.0)
            result.append({
                'warehouse_id': warehouse.id,
                'warehouse_name': warehouse.name.lower().title(),
                'total_sold': qty_sold,
                'warehouse_sequence': warehouse.sequence,
                'stock': qty_available,
                'boxes': 0,  # Não calculado em nível agregado
                'units': 0,
                'uom': '',
            })
        result.sort(key=lambda x: x['warehouse_sequence'])
        return result

    def update_daily_summaries(self):
        pass

    def generate_historical_summaries(self):
        """Procesar el historico de ventas resúmenes."""

        current_date = fields.Date.today()
        # date = current_date - timedelta(days=160)
        from datetime import date
        date = date(2025, 1, 1)

        move_lines = self.env['stock.move.line'].search([
            ('date', '>=', date),
            ('date', '<', current_date + timedelta(days=1)),
            ('state', '=', 'done'),
            ('location_dest_id.usage', '=', 'customer'),
            '|',
            ('move_id.sale_line_id', '!=', False),
            ('move_id.reference', 'ilike', '/POS/'),
        ])

        self.search([]).unlink()

        for line in move_lines:
            product = line.product_id
            warehouse = self._get_warehouse_from_location_id(
                line.location_id.id)
            quantity = line.quantity

            summary = self.search([
                ('date', '=', line.date),
                ('product_id', '=', product.id),
                ('warehouse_id', '=', warehouse.id),
            ], limit=1)
            if summary:
                summary.quantity_sold += quantity
                summary.amount_total += line.sale_price  # Acumular el monto
            else:
                self.create({
                    'date': line.date,
                    'product_id': product.id,
                    'warehouse_id': warehouse.id,
                    'quantity_sold': quantity,
                    'amount_total': line.sale_price
                })

    @api.model
    def update_zero_values(self):
        """Actualiza los resúmenes de ventas con valores cero."""
        summaries = self.search([('amount_total', '<=', 0.01)])
        for summary in summaries:
            summary.amount_total = 0.0

        summaries_zero = self.search([('costo_total', '<=', 0.01)])
        for d in summaries_zero:
            d.costo_total = 0.0
        return True

    def _is_auto_adjust_enabled(self):
        """Verifica si el ajuste automático está habilitado desde ir.config_parameter"""
        auto_adjust = self.env['ir.config_parameter'].sudo().get_param(
            'product_warehouse_sale_summary.auto_adjust_stock_from_sales_summary',
            default='False'
        )
        return auto_adjust == 'True'

    @api.model
    def create(self, vals):
        records = super(ProductWarehouseSaleSummary, self).create(vals)

        # DUAL INSERTION: Encolar eventos para procesamiento de stats
        # Nota: records puede ser un recordset con múltiples registros
        # cuando se llama create() con una lista de vals
        for record in records:
            try:
                self._enqueue_for_replenishment(record)
            except Exception as e:
                # No fallar la creación del registro si falla el encolado
                _logger.warning(
                    "Error encolando evento de reabastecimiento para record %s: %s",
                    record.id, e
                )

            if record._is_auto_adjust_enabled():
                if record.quantity_sold > 0 and not record.stock_adjusted:
                    record._reduce_stock()

        return records

    def _enqueue_for_replenishment(self, record):
        """
        Encola el registro en la cola de reabastecimiento para procesamiento async.

        Este método implementa el patrón de "dual write":
        1. El registro se guarda en product.warehouse.sale.summary (síncrono)
        2. Un evento se encola para actualización de stats (asíncrono)

        La cola permite:
        - Procesamiento en batch para eficiencia
        - Desacoplamiento temporal
        - Tolerancia a fallos en el cálculo de stats

        IMPORTANTE: Para ventas solo se encolan registros del sistema legado.
        Para transferencias se encolan todos los registros.
        """
        # Solo encolar si hay datos relevantes
        if not record.product_id or not record.warehouse_id:
            return

        if record.quantity_sold <= 0:
            return

        # FILTRO CRÍTICO:
        # - Ventas: solo sistema legado (is_legacy_system=True)
        # - Transferencias: todos los registros
        record_type = record.record_type or 'sale'
        if record_type == 'sale' and not record.is_legacy_system:
            return  # No encolar ventas que no son del sistema legado

        # Verificar si el módulo de cola está instalado
        Queue = self.env.get('product.replenishment.queue')
        if Queue is None:
            return

        # Encolar el evento
        Queue.enqueue_event(
            product_id=record.product_id.id,
            warehouse_id=record.warehouse_id.id,
            quantity=record.quantity_sold,
            event_date=record.date,
            record_type=record_type,
            is_legacy_system=record.is_legacy_system,
            source_id=record.id
        )

    def write(self, vals):
        # Guardar información para encolamiento ANTES del write
        records_to_enqueue = []
        if 'quantity_sold' in vals:
            for record in self:
                old_qty = record.quantity_sold
                new_qty = vals['quantity_sold']
                diff = new_qty - old_qty

                # Solo encolar si hay incremento
                if diff > 0:
                    records_to_enqueue.append({
                        'record': record,
                        'diff': diff,
                    })

                    # Ajustar stock si está habilitado
                    if self._is_auto_adjust_enabled():
                        record._reduce_stock(qty_to_reduce=diff)
                elif diff < 0 and self._is_auto_adjust_enabled():
                    record._return_stock(qty_to_return=abs(diff))
        elif self._is_auto_adjust_enabled():
            # Otros campos sin quantity_sold
            pass

        result = super(ProductWarehouseSaleSummary, self).write(vals)

        # DUAL INSERTION: Encolar eventos para procesamiento de stats
        for item in records_to_enqueue:
            try:
                record = item['record']
                # Crear un pseudo-record con la cantidad diferencial
                self._enqueue_for_replenishment_with_qty(record, item['diff'])
            except Exception as e:
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(
                    "Error encolando evento de reabastecimiento (write) para record %s: %s",
                    record.id, e
                )

        return result

    def _enqueue_for_replenishment_with_qty(self, record, quantity):
        """
        Encola el registro con una cantidad específica (para updates).

        IMPORTANTE: Para ventas solo se encolan registros del sistema legado.
        Para transferencias se encolan todos los registros.
        """
        if not record.product_id or not record.warehouse_id:
            return

        if quantity <= 0:
            return

        # FILTRO CRÍTICO:
        # - Ventas: solo sistema legado (is_legacy_system=True)
        # - Transferencias: todos los registros
        record_type = record.record_type or 'sale'
        if record_type == 'sale' and not record.is_legacy_system:
            return  # No encolar ventas que no son del sistema legado

        # Verificar si el módulo de cola está instalado
        try:
            Queue = self.env['product.replenishment.queue']
        except KeyError:
            return

        Queue.sudo().enqueue_event(
            product_id=record.product_id.id,
            warehouse_id=record.warehouse_id.id,
            quantity=quantity,
            event_date=record.date,
            record_type=record_type,
            is_legacy_system=record.is_legacy_system,
            source_id=record.id
        )

    def unlink(self):
        if self._is_auto_adjust_enabled():
            for record in self:
                if record.quantity_sold > 0 and record.stock_adjusted:
                    record._return_stock()
        return super(ProductWarehouseSaleSummary, self).unlink()

    def _get_stock_location(self):
        """Obtiene la ubicación de stock del almacén"""
        self.ensure_one()
        if self.warehouse_id:
            return self.warehouse_id.lot_stock_id
        else:
            return self.env['stock.location'].search([
                ('usage', '=', 'internal')
            ], limit=1)

    def _get_removal_strategy_name(self, product, location):
        """
        Obtiene el nombre de la estrategia de remoción aplicable
        """
        # Prioridad: Categoría del producto > Ubicación > FIFO por defecto
        removal_strategy = product.categ_id.removal_strategy_id
        if not removal_strategy:
            removal_strategy = location.removal_strategy_id

        if removal_strategy:
            return removal_strategy.method
        return 'fifo'  # Por defecto

    def _reduce_stock(self, qty_to_reduce=None):
        """
        Reduce el stock usando la estrategia configurada (FEFO si está configurado)
        """
        self.ensure_one()

        if qty_to_reduce is None:
            qty_to_reduce = self.quantity_sold

        if qty_to_reduce <= 0:
            return

        location = self._get_stock_location()
        if not location:
            raise UserError(('No se encontró ubicación de stock válida.'))

        # Obtener la estrategia de remoción
        strategy = self._get_removal_strategy_name(self.product_id, location)

        # Usar _gather para obtener quants con la estrategia aplicada
        quants = self.env['stock.quant']._gather(
            self.product_id,
            location,
            lot_id=False,
            package_id=False,
            owner_id=False,
            strict=False,  # Permite buscar todos los quants disponibles
            qty=qty_to_reduce
        )

        if not quants:
            raise ValidationError((
                                      'No hay stock disponible para el producto %s en %s'
                                  ) % (self.product_id.display_name, location.display_name))

        # Si la estrategia es FEFO, aplicar ordenamiento manual por removal_date
        # porque _gather no lo hace automáticamente para FEFO
        if strategy == 'fefo':
            quants = self._apply_fefo_ordering(quants)

        remaining_qty = qty_to_reduce

        # Reducir stock usando el método nativo
        for quant in quants:
            if remaining_qty <= 0:
                break

            available_qty = quant.quantity - quant.reserved_quantity

            if available_qty <= 0:
                continue

            qty_to_take = min(available_qty, remaining_qty)

            # Usar _update_available_quantity (método nativo)
            self.env['stock.quant']._update_available_quantity(
                self.product_id,
                location,
                -qty_to_take,
                lot_id=quant.lot_id,
                package_id=quant.package_id,
                owner_id=quant.owner_id
            )

            remaining_qty -= qty_to_take

        if remaining_qty > 0:
            raise ValidationError((
                                      'Stock insuficiente para %s en %s. Faltante: %.2f %s'
                                  ) % (
                                      self.product_id.display_name,
                                      location.display_name,
                                      remaining_qty,
                                      self.uom_id.name
                                  ))

        self.stock_adjusted = True

    def _apply_fefo_ordering(self, quants):
        """
        Ordena los quants según estrategia FEFO
        Prioriza por removal_date (fecha de remoción del lote)

        FEFO en Odoo usa removal_date que se calcula como:
        removal_date = use_date - removal_days

        Donde:
        - use_date: fecha en que el producto debe usarse
        - removal_days: días antes de la fecha de uso que debe removerse
        """
        # Separar quants con removal_date vs sin removal_date
        quants_with_removal = quants.filtered(
            lambda q: q.lot_id and q.lot_id.removal_date
        )

        quants_without_removal = quants - quants_with_removal

        # Ordenar los que tienen removal_date (de menor a mayor = más cerca a vencer primero)
        if quants_with_removal:
            quants_with_removal = quants_with_removal.sorted(
                key=lambda q: (q.lot_id.removal_date, q.in_date, q.id)
            )

        # Ordenar los sin removal_date por FIFO como fallback
        if quants_without_removal:
            quants_without_removal = quants_without_removal.sorted(
                key=lambda q: (q.in_date, q.id)
            )

        # Retornar: primero los que tienen removal_date, luego los que no
        return quants_with_removal + quants_without_removal

    def _return_stock(self, qty_to_return=None):
        """
        Devuelve stock usando método nativo de Odoo
        """
        self.ensure_one()

        if qty_to_return is None:
            qty_to_return = self.quantity_sold

        if qty_to_return <= 0:
            return

        location = self._get_stock_location()
        if not location:
            raise UserError(('No se encontró ubicación de stock válida.'))

        # Usar método nativo para incrementar cantidad disponible
        self.env['stock.quant']._update_available_quantity(
            self.product_id,
            location,
            qty_to_return
        )

        if qty_to_return == self.quantity_sold:
            self.stock_adjusted = False

    # @api.constrains('quantity_sold')
    # def _check_quantity_sold(self):
    #     for record in self:
    #         if record.quantity_sold < 0:
    #             raise ValidationError(('La cantidad vendida no puede ser negativa.'))

    @api.model
    def create_batch(self, vals_list):
        """
        Creación masiva optimizada con ajuste de stock agrupado
        Usar este método para imports de miles de registros

        Ejemplo de uso:
        vals_list = [
            {'date': '2025-01-01', 'product_id': 1, 'warehouse_id': 1, 'quantity_sold': 10},
            {'date': '2025-01-02', 'product_id': 2, 'warehouse_id': 1, 'quantity_sold': 5},
        ]
        records = env['product.warehouse.sale.summary'].create_batch(vals_list)
        """
        # Crear registros sin ajustar stock
        records = self.env['product.warehouse.sale.summary']
        for vals in vals_list:
            vals['stock_adjusted'] = False
            records |= super(ProductWarehouseSaleSummary, self).create(vals)

        # Agrupar por producto y ubicación para procesamiento masivo
        stock_adjustments = {}

        for record in records:
            if record.quantity_sold > 0:
                location = record._get_stock_location()
                key = (record.product_id.id, location.id)

                if key not in stock_adjustments:
                    stock_adjustments[key] = {
                        'product': record.product_id,
                        'location': location,
                        'quantity': 0,
                        'records': []
                    }

                stock_adjustments[key]['quantity'] += record.quantity_sold
                stock_adjustments[key]['records'].append(record)

        # Procesar ajustes agrupados
        StockQuant = self.env['stock.quant']

        for key, data in stock_adjustments.items():
            product = data['product']
            location = data['location']
            total_qty = data['quantity']

            # Obtener estrategia
            strategy = self._get_removal_strategy_name(product, location)

            # Obtener quants con _gather
            quants = StockQuant._gather(
                product,
                location,
                lot_id=False,
                package_id=False,
                owner_id=False,
                strict=False,
                qty=total_qty
            )

            if not quants:
                raise ValidationError((
                                          'No hay stock disponible para %s'
                                      ) % product.display_name)

            # Si es FEFO, aplicar ordenamiento manual
            if strategy == 'fefo':
                quants = self._apply_fefo_ordering(quants)

            remaining_qty = total_qty

            for quant in quants:
                if remaining_qty <= 0:
                    break

                available_qty = quant.quantity - quant.reserved_quantity
                if available_qty <= 0:
                    continue

                qty_to_take = min(available_qty, remaining_qty)

                StockQuant._update_available_quantity(
                    product,
                    location,
                    -qty_to_take,
                    lot_id=quant.lot_id,
                    package_id=quant.package_id,
                    owner_id=quant.owner_id
                )

                remaining_qty -= qty_to_take

            if remaining_qty > 0:
                raise ValidationError((
                                          'Stock insuficiente para %s. Faltante: %.2f'
                                      ) % (product.display_name, remaining_qty))

            # Marcar todos los registros como ajustados
            for rec in data['records']:
                rec.stock_adjusted = True

        return records
