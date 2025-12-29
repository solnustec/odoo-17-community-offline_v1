# -*- coding: utf-8 -*-
"""
Modelo de Analisis de Rotacion de Productos por Bodega.

Este modulo implementa un sistema de alto rendimiento para identificar
productos con stock que han dejado de rotar en las bodegas.

Arquitectura:
- Tabla unica de snapshot (sin historicos)
- Actualizaciones incrementales via cron
- Operaciones SQL masivas (sin loops ORM)
- Indices optimizados para consultas rapidas

Valor Centinela 9999:
- Cuando days_without_sale = 9999, significa "NUNCA se ha vendido"
- Cuando days_without_transfer = 9999, significa "NUNCA se ha transferido"
- Cuando days_without_rotation = 9999, significa "NUNCA ha tenido movimiento"
- El valor 9999 permite ordenar DESC y que los "nunca" aparezcan primero
- El valor 0 significa "hoy mismo" (maxima rotacion, producto muy activo)
"""
import logging
from datetime import datetime, timedelta, date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTES DE CONFIGURACION
# =============================================================================
# Umbrales para marcar productos como sin rotacion (en dias)
DAYS_NO_ROTATION_THRESHOLD = 30  # Dias sin movimiento para marcar sin rotacion
DAYS_NO_SALE_THRESHOLD = 30      # Dias sin venta para marcar sin ventas
DAYS_NO_TRANSFER_THRESHOLD = 30  # Dias sin transferencia para marcar sin transferencias

# Valor centinela: 9999 = "NUNCA" (el producto nunca tuvo esa actividad)
# Se usa 9999 porque:
# - El valor 0 significa "hoy mismo" (maxima rotacion)
# - Con ORDER BY days DESC, los "nunca" (9999) aparecen primero (mas criticos)
# - Permite filtros simples: WHERE days_without_sale = 9999 (nunca vendido)
# - Es un valor suficientemente alto para no confundirse con dias reales
MAX_DAYS_VALUE = 9999


class ProductRotationDaily(models.Model):
    """
    Snapshot diario del estado de rotacion de productos por bodega.

    Esta tabla almacena SOLO el estado actual, no datos historicos.
    Se actualiza incrementalmente mediante un cron diario que procesa
    unicamente productos con actividad o cambios de stock.

    Principios de diseno:
    - Pre-agregacion incremental (nunca recalcula todo)
    - Sin triggers (toda la logica en cron de Odoo)
    - Operaciones SQL masivas para eficiencia
    - Indices compuestos para rendimiento
    """
    _name = 'product.rotation.daily'
    _description = 'Analisis de Rotacion de Productos'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'days_without_rotation DESC, product_id'
    _rec_name = 'product_id'

    # =========================================================================
    # CAMPOS PRINCIPALES
    # =========================================================================

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        ondelete='cascade',
        help='Producto analizado',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Bodega',
        required=True,
        ondelete='cascade',
        help='Bodega donde se encuentra el stock',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        ondelete='cascade',
        help='Compania propietaria del stock',
    )

    # =========================================================================
    # INFORMACION DE STOCK
    # =========================================================================

    stock_on_hand = fields.Float(
        string='Stock Disponible',
        digits='Product Unit of Measure',
        default=0.0,
        help='Cantidad actual en stock (ubicaciones internas)',
    )

    # =========================================================================
    # FECHAS DE ULTIMA ACTIVIDAD
    # =========================================================================

    last_sale_date = fields.Date(
        string='Ultima Venta',
        help='Fecha de la ultima venta confirmada de este producto en esta bodega. '
             'NULL si nunca se ha vendido.',
    )
    last_transfer_date = fields.Date(
        string='Ultima Transferencia',
        help='Fecha de la ultima transferencia (entrada/salida) de este producto. '
             'Incluye: recepciones, transferencias internas, ajustes. '
             'NULL si nunca se ha transferido.',
    )
    last_rotation_date = fields.Date(
        string='Ultimo Movimiento',
        help='Fecha del ultimo movimiento de cualquier tipo (venta o transferencia). '
             'Es la mas reciente entre ultima venta y ultima transferencia. '
             'NULL si nunca ha tenido movimiento.',
    )

    # =========================================================================
    # DIAS SIN ACTIVIDAD
    # Valor 0 = movimiento HOY (maxima rotacion)
    # Valor 9999 = "NUNCA" (el producto nunca tuvo esa actividad)
    # =========================================================================

    days_without_sale = fields.Integer(
        string='Dias sin Venta',
        default=MAX_DAYS_VALUE,
        help='Dias transcurridos desde la ultima venta. '
             '0 = vendido hoy (maxima rotacion). '
             '9999 = NUNCA se ha vendido (caso mas critico).',
    )
    days_without_transfer = fields.Integer(
        string='Dias sin Transferencia',
        default=MAX_DAYS_VALUE,
        help='Dias transcurridos desde la ultima transferencia. '
             '0 = transferido hoy (maxima rotacion). '
             '9999 = NUNCA se ha transferido.',
    )
    days_without_rotation = fields.Integer(
        string='Dias sin Rotacion',
        default=MAX_DAYS_VALUE,
        help='Dias transcurridos desde cualquier movimiento (venta o transferencia). '
             '0 = movimiento hoy (maxima rotacion). '
             '9999 = NUNCA ha tenido movimiento (caso mas critico).',
    )

    # =========================================================================
    # FLAGS BOOLEANOS (para filtros rapidos)
    # TRUE cuando:
    #   - El producto NUNCA tuvo esa actividad (days = 9999), O
    #   - Han pasado mas de 30 dias desde la ultima actividad
    # =========================================================================

    flag_no_sales = fields.Boolean(
        string='Sin Ventas',
        default=False,
        help=f'TRUE si el producto nunca se ha vendido (dias=9999) o '
             f'lleva {DAYS_NO_SALE_THRESHOLD}+ dias sin venta.',
    )
    flag_no_transfers = fields.Boolean(
        string='Sin Transferencias',
        default=False,
        help=f'TRUE si el producto nunca se ha transferido (dias=9999) o '
             f'lleva {DAYS_NO_TRANSFER_THRESHOLD}+ dias sin transferencia.',
    )
    flag_no_rotation = fields.Boolean(
        string='Sin Rotacion',
        default=False,
        help=f'TRUE si el producto nunca ha tenido movimiento (dias=9999) o '
             f'lleva {DAYS_NO_ROTATION_THRESHOLD}+ dias sin movimiento.',
    )

    # =========================================================================
    # METADATOS
    # =========================================================================

    updated_at = fields.Datetime(
        string='Ultima Actualizacion',
        default=fields.Datetime.now,
        help='Fecha y hora de la ultima actualizacion de este registro por el cron.',
    )

    # =========================================================================
    # CAMPOS RELACIONADOS (solo lectura, sin almacenar)
    # =========================================================================

    product_name = fields.Char(
        related='product_id.name',
        string='Nombre del Producto',
        store=False,
    )
    product_default_code = fields.Char(
        related='product_id.default_code',
        string='Referencia Interna',
        store=False,
    )
    warehouse_name = fields.Char(
        related='warehouse_id.name',
        string='Nombre de Bodega',
        store=False,
    )

    # =========================================================================
    # CAMPOS PARA REDISTRIBUCION (Calculo Perezoso - Lazy Calculation)
    # Solo se calculan cuando se accede al registro, no en el cron
    # =========================================================================

    suggested_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Bodegas Sugeridas',
        compute='_compute_suggested_warehouses',
        help='Bodegas donde este producto tiene rotacion activa. '
             'Maximo 5 bodegas ordenadas por rotacion reciente. '
             'Si no hay bodegas con rotacion, se sugiere Bodega Matilde.',
    )

    suggested_warehouses_html = fields.Html(
        string='Bodegas para Redistribucion',
        compute='_compute_suggested_warehouses',
        help='Tabla con bodegas sugeridas y stock disponible para redistribucion.',
    )

    has_suggested_warehouses = fields.Boolean(
        string='Tiene Bodegas Sugeridas',
        compute='_compute_suggested_warehouses',
        help='Indica si hay bodegas alternativas para redistribuir el producto.',
    )

    # =========================================================================
    # RESTRICCIONES SQL
    # =========================================================================

    _sql_constraints = [
        (
            'unique_product_warehouse',
            'UNIQUE(product_id, warehouse_id)',
            'Solo puede existir un registro por producto y bodega.'
        ),
    ]

    # =========================================================================
    # CREACION DE INDICES OPTIMIZADOS
    # =========================================================================

    # def init(self):
    #     """
    #     Crea indices PostgreSQL optimizados para consultas de alto rendimiento.
    #
    #     Indices creados:
    #     1. idx_rotation_flags_composite: Para filtrar por flags (uso mas comun)
    #     2. idx_rotation_warehouse_days: Para ordenar por dias dentro de bodega
    #     3. idx_rotation_company_days: Para reportes por compania
    #     4. idx_rotation_with_stock: Para filtro "con stock" (muy frecuente)
    #     5. idx_rotation_updated: Para monitoreo de ejecucion del cron
    #     6. idx_rotation_never: Para filtrar productos que "nunca" tuvieron actividad
    #     """
    #     # Indice compuesto para filtrado por flags (caso de uso mas comun)
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_flags_composite
    #         ON product_rotation_daily (company_id, flag_no_rotation, flag_no_sales, flag_no_transfers)
    #         WHERE flag_no_rotation = TRUE OR flag_no_sales = TRUE OR flag_no_transfers = TRUE;
    #     """)
    #
    #     # Indice para ordenamiento por bodega + dias sin rotacion
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_warehouse_days
    #         ON product_rotation_daily (warehouse_id, days_without_rotation DESC);
    #     """)
    #
    #     # Indice para consultas por compania + dias
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_company_days
    #         ON product_rotation_daily (company_id, days_without_rotation DESC);
    #     """)
    #
    #     # Indice parcial para productos con stock (filtro muy frecuente)
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_with_stock
    #         ON product_rotation_daily (company_id, warehouse_id)
    #         WHERE stock_on_hand > 0;
    #     """)
    #
    #     # Indice para monitoreo de actualizaciones del cron
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_updated
    #         ON product_rotation_daily (updated_at DESC);
    #     """)
    #
    #     # Indice para productos que NUNCA han tenido actividad (days = 9999)
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_never
    #         ON product_rotation_daily (company_id, warehouse_id)
    #         WHERE days_without_rotation = 9999;
    #     """)
    #
    #     # Indice para buscar productos con rotacion activa (para sugerencias)
    #     self.env.cr.execute("""
    #         CREATE INDEX IF NOT EXISTS idx_rotation_active_products
    #         ON product_rotation_daily (product_id, warehouse_id)
    #         WHERE flag_no_rotation = FALSE AND stock_on_hand > 0;
    #     """)
    #
    #     _logger.info("ROTACION: Indices PostgreSQL creados/verificados correctamente")

    # =========================================================================
    # CALCULO PEREZOSO DE BODEGAS SUGERIDAS (Lazy Calculation)
    # =========================================================================

    # Constantes para redistribucion
    MAX_SUGGESTED_WAREHOUSES = 5
    DEFAULT_WAREHOUSE_NAME = 'Bodega Matilde'  # Bodega por defecto si no hay sugerencias
    SALES_PERIOD_DAYS = 30  # Periodo para consulta de ventas

    @api.depends('product_id', 'warehouse_id', 'flag_no_rotation')
    def _compute_suggested_warehouses(self):
        """
        Calcula las bodegas sugeridas para redistribucion del producto.

        Este metodo usa calculo perezoso (lazy calculation):
        - Solo se ejecuta cuando se accede al registro en el formulario
        - NO se ejecuta durante el cron de actualizacion diaria
        - Optimizado para consultas rapidas con indices

        Logica de sugerencias:
        1. Busca bodegas donde el producto tiene rotacion activa (flag_no_rotation=False)
        2. Excluye la bodega actual del producto
        3. Obtiene ventas de los ultimos 30 dias para cada bodega
        4. Ordena por ventas DESC (mayor volumen primero), luego rotacion ASC
        5. Limita a MAX_SUGGESTED_WAREHOUSES (5) bodegas
        6. Si no hay bodegas activas, sugiere DEFAULT_WAREHOUSE_NAME
        """
        for record in self:
            suggested_warehouses = self.env['stock.warehouse']
            warehouses_data = []

            if record.flag_no_rotation and record.product_id:
                # Buscar otras bodegas donde el producto tiene rotacion activa
                # Traemos mas de 5 para luego ordenar por ventas
                active_rotations = self.search([
                    ('product_id', '=', record.product_id.id),
                    ('warehouse_id', '!=', record.warehouse_id.id),
                    ('flag_no_rotation', '=', False),  # Tiene rotacion activa
                    ('stock_on_hand', '>', 0),  # Tiene stock (indica que se vende ahi)
                ], order='days_without_rotation ASC', limit=20)

                if active_rotations:
                    # Obtener ventas de los ultimos 30 dias para cada bodega
                    for rot in active_rotations:
                        sales_30d = self._get_sales_last_30_days(
                            record.product_id.id,
                            rot.warehouse_id.id
                        )
                        warehouses_data.append({
                            'warehouse': rot.warehouse_id,
                            'stock': rot.stock_on_hand,
                            'days': rot.days_without_rotation,
                            'sales_30d': sales_30d,
                            'rotation_id': rot.id,
                        })

                    # Ordenar por ventas DESC (mayor volumen primero), luego por dias ASC
                    warehouses_data.sort(key=lambda x: (-x['sales_30d'], x['days']))

                    # Limitar a MAX_SUGGESTED_WAREHOUSES
                    warehouses_data = warehouses_data[:self.MAX_SUGGESTED_WAREHOUSES]
                    suggested_warehouses = self.env['stock.warehouse'].browse(
                        [d['warehouse'].id for d in warehouses_data]
                    )
                else:
                    # Buscar DEFAULT_WAREHOUSE_NAME como fallback
                    default_wh = self.env['stock.warehouse'].search([
                        ('name', 'ilike', self.DEFAULT_WAREHOUSE_NAME)
                    ], limit=1)

                    if default_wh and default_wh.id != record.warehouse_id.id:
                        suggested_warehouses = default_wh
                        # Obtener stock y ventas del producto en la bodega por defecto
                        stock_in_default = self._get_product_stock_in_warehouse(
                            record.product_id.id, default_wh.id
                        )
                        sales_in_default = self._get_sales_last_30_days(
                            record.product_id.id, default_wh.id
                        )
                        warehouses_data.append({
                            'warehouse': default_wh,
                            'stock': stock_in_default,
                            'days': None,  # No hay datos de rotacion
                            'sales_30d': sales_in_default,
                            'rotation_id': None,
                        })

            record.suggested_warehouse_ids = suggested_warehouses
            record.has_suggested_warehouses = bool(suggested_warehouses)
            record.suggested_warehouses_html = self._generate_suggested_warehouses_html(
                record, warehouses_data
            )

    def _get_sales_last_30_days(self, product_id, warehouse_id):
        """
        Obtiene las ventas de un producto en una bodega en los ultimos 30 dias.

        Intenta obtener el dato de product.sales.stats (O(1) si esta precalculado).
        Si no esta disponible, calcula desde product_warehouse_sale_summary.

        Args:
            product_id: ID del producto
            warehouse_id: ID de la bodega

        Returns:
            float: Total de ventas en los ultimos 30 dias
        """
        # Intentar obtener desde product.sales.stats (modelo precalculado)
        try:
            SalesStats = self.env['product.sales.stats']
            stat = SalesStats.search([
                ('product_id', '=', product_id),
                ('warehouse_id', '=', warehouse_id),
                ('period_days', '=', self.SALES_PERIOD_DAYS),
            ], limit=1)

            if stat:
                # mean_qty es ventas diarias promedio, multiplicar por dias
                return stat.mean_qty * self.SALES_PERIOD_DAYS

        except Exception:
            # El modelo no existe o hay error, continuar con fallback
            pass

        # Fallback: calcular directamente desde product_warehouse_sale_summary
        date_from = date.today() - timedelta(days=self.SALES_PERIOD_DAYS)
        self.env.cr.execute("""
            SELECT COALESCE(SUM(quantity_sold), 0)
            FROM product_warehouse_sale_summary
            WHERE product_id = %s
            AND warehouse_id = %s
            AND date >= %s
        """, (product_id, warehouse_id, date_from))
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _get_product_stock_in_warehouse(self, product_id, warehouse_id):
        """
        Obtiene el stock de un producto en una bodega especifica.

        Args:
            product_id: ID del producto
            warehouse_id: ID de la bodega

        Returns:
            float: Cantidad en stock
        """
        self.env.cr.execute("""
            SELECT COALESCE(SUM(sq.quantity), 0)
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sq.product_id = %s
            AND sl.warehouse_id = %s
            AND sl.usage = 'internal'
        """, (product_id, warehouse_id))
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _generate_suggested_warehouses_html(self, record, warehouses_data):
        """
        Genera el HTML con la tabla de bodegas sugeridas.

        Args:
            record: Registro de product.rotation.daily
            warehouses_data: Lista de dicts con datos de bodegas

        Returns:
            str: HTML formateado con tabla y botones
        """
        if not warehouses_data:
            return """
            <div class="alert alert-info" style="margin:10px 0;">
                <i class="fa fa-info-circle"></i>
                No hay bodegas sugeridas para redistribucion.
                El producto no tiene rotacion activa en otras bodegas.
            </div>
            """

        rows = []
        for data in warehouses_data:
            wh = data['warehouse']
            stock = data['stock']
            days = data['days']
            sales_30d = data.get('sales_30d', 0)

            days_text = f"{days}d" if days is not None else "N/A"
            days_style = "color:green;" if days is not None and days < 30 else ""

            # Estilo para ventas (verde si hay ventas, gris si no)
            sales_style = "color:green; font-weight:bold;" if sales_30d > 0 else "color:#999;"
            sales_text = f"{sales_30d:.0f}" if sales_30d > 0 else "0"

            # Boton de transferencia con data attributes para el JS
            transfer_btn = f"""
                <button type="button"
                        class="btn btn-sm btn-primary o_transfer_btn"
                        data-warehouse-id="{wh.id}"
                        data-warehouse-name="{wh.name}"
                        data-rotation-id="{record.id}">
                    <i class="fa fa-truck"></i> Transferir
                </button>
            """

            rows.append(f"""
            <tr>
                <td style="padding:8px;">{wh.name}</td>
                <td style="padding:8px; text-align:right;">{stock:.0f}</td>
                <td style="padding:8px; text-align:right; {sales_style}">{sales_text}</td>
                <td style="padding:8px; text-align:center; {days_style}">{days_text}</td>
                <td style="padding:8px; text-align:center;">{transfer_btn}</td>
            </tr>
            """)

        rows_html = "".join(rows)

        return f"""
        <div style="margin-top:10px;">
            <p><strong>Bodegas sugeridas para redistribuir este producto:</strong></p>
            <table class="table table-sm table-striped" style="width:100%;">
                <thead>
                    <tr style="background-color:#f5f5f5;">
                        <th style="padding:8px;">Bodega Destino</th>
                        <th style="padding:8px; text-align:right;">Stock</th>
                        <th style="padding:8px; text-align:right;">Ventas 30d</th>
                        <th style="padding:8px; text-align:center;">Rotacion</th>
                        <th style="padding:8px; text-align:center;">Accion</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <p class="text-muted" style="font-size:smaller;">
                <i class="fa fa-lightbulb-o"></i>
                Las bodegas se ordenan por volumen de ventas (30 dias), priorizando las de mayor demanda.
            </p>
        </div>
        """

    # =========================================================================
    # ACCIONES DE REDISTRIBUCION
    # =========================================================================

    def action_open_transfer_wizard(self):
        """
        Abre el wizard de transferencia para redistribuir el producto.
        """
        self.ensure_one()
        return {
            'name': _('Transferir Producto'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.rotation.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_rotation_id': self.id,
                'default_product_id': self.product_id.id,
                'default_source_warehouse_id': self.warehouse_id.id,
                'default_quantity': self.stock_on_hand,
            },
        }

    def action_quick_transfer(self, dest_warehouse_id, quantity=None):
        """
        Realiza una transferencia rapida del producto a otra bodega.

        Args:
            dest_warehouse_id: ID de la bodega destino
            quantity: Cantidad a transferir (si es None, transfiere todo el stock)

        Returns:
            dict: Accion para mostrar el picking creado
        """
        self.ensure_one()

        if quantity is None:
            quantity = self.stock_on_hand

        if quantity <= 0:
            raise UserError(_('La cantidad a transferir debe ser mayor a 0.'))

        if quantity > self.stock_on_hand:
            raise UserError(_(
                'La cantidad a transferir (%.2f) excede el stock disponible (%.2f).'
            ) % (quantity, self.stock_on_hand))

        dest_warehouse = self.env['stock.warehouse'].browse(dest_warehouse_id)
        if not dest_warehouse.exists():
            raise UserError(_('La bodega destino no existe.'))

        if dest_warehouse.id == self.warehouse_id.id:
            raise UserError(_('La bodega destino debe ser diferente a la bodega origen.'))

        # Obtener ubicaciones
        source_location = self.warehouse_id.lot_stock_id
        dest_location = dest_warehouse.lot_stock_id

        # Buscar o crear el tipo de operacion de transferencia interna
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.warehouse_id.id),
        ], limit=1)

        if not picking_type:
            raise UserError(_(
                'No se encontro un tipo de operacion de transferencia interna '
                'para la bodega %s.'
            ) % self.warehouse_id.name)

        # Crear el picking
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'origin': f'Redistribucion desde Analisis de Rotacion - {self.product_id.name}',
            'move_ids': [(0, 0, {
                'name': self.product_id.name,
                'product_id': self.product_id.id,
                'product_uom_qty': quantity,
                'product_uom': self.product_id.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            })],
        }

        picking = self.env['stock.picking'].create(picking_vals)

        # Confirmar el picking
        picking.action_confirm()

        _logger.info(
            f"ROTACION: Transferencia creada - Producto: {self.product_id.name}, "
            f"Cantidad: {quantity}, Origen: {self.warehouse_id.name}, "
            f"Destino: {dest_warehouse.name}, Picking: {picking.name}"
        )

        return {
            'name': _('Transferencia Creada'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # =========================================================================
    # CRON PRINCIPAL: ACTUALIZACION DIARIA INCREMENTAL
    # =========================================================================

    @api.model
    def _cron_update_rotation_daily(self):
        """
        Metodo principal del cron para actualizacion diaria incremental.

        Caracteristicas de eficiencia:
        - Solo procesa productos con actividad o cambios de stock
        - Usa operaciones SQL masivas (sin loops ORM)
        - Pre-agrega datos en CTEs para rendimiento
        - Usa UPSERT para insert/update atomico

        Objetivos de rendimiento:
        - 15,000+ productos
        - 300+ bodegas
        - < 60 segundos de ejecucion
        """
        start_time = datetime.now()
        _logger.info("=" * 60)
        _logger.info("ROTACION: Iniciando actualizacion diaria incremental")
        _logger.info("=" * 60)

        try:
            # Obtener compania principal (primera por ID, contiene todas las bodegas)
            main_company = self.env['res.company'].search([], limit=1, order='id')
            if not main_company:
                _logger.warning("ROTACION: No se encontro compania, omitiendo actualizacion")
                return False

            _logger.info(f"ROTACION: Procesando compania principal: {main_company.name}")

            # Procesar solo la compania principal
            result = self._process_company_rotation(main_company)
            total_inserted = result.get('inserted', 0)
            total_updated = result.get('updated', 0)
            total_deleted = result.get('deleted', 0)

            # Confirmar transaccion
            self.env.cr.commit()

            elapsed = (datetime.now() - start_time).total_seconds()
            _logger.info("=" * 60)
            _logger.info(f"ROTACION: Completado en {elapsed:.2f} segundos")
            _logger.info(f"  - Insertados: {total_inserted}")
            _logger.info(f"  - Actualizados: {total_updated}")
            _logger.info(f"  - Eliminados (sin stock): {total_deleted}")
            _logger.info("=" * 60)

            # Crear actividades para revisores si hay productos criticos
            self._create_review_activities()

            return True

        except Exception as e:
            _logger.error(f"ROTACION: Error durante actualizacion - {str(e)}")
            self.env.cr.rollback()
            raise

    def _process_company_rotation(self, company):
        """
        Procesa datos de rotacion para una compania.

        Este metodo ejecuta una consulta SQL optimizada que:
        1. Obtiene stock actual por producto/bodega
        2. Obtiene fechas de ultima venta (desde product_warehouse_sale_summary)
        3. Obtiene fechas de ultima transferencia (desde stock.move)
        4. Calcula dias sin actividad
        5. Establece flags basados en umbrales
        6. Ejecuta UPSERT masivo

        Args:
            company: Registro de res.company

        Returns:
            dict con conteos: inserted, updated, deleted
        """
        _logger.info(f"Procesando compania: {company.name} (ID: {company.id})")

        today = date.today()
        now = datetime.now()

        # Paso 1: Eliminar registros de productos que ya no tienen stock
        deleted = self._delete_zero_stock_records(company.id)

        # Paso 2: Ejecutar consulta principal de actualizacion incremental
        result = self._execute_incremental_update(company.id, today, now)

        _logger.info(f"  Compania {company.name}: insertados={result['inserted']}, "
                     f"actualizados={result['updated']}, eliminados={deleted}")

        return {
            'inserted': result['inserted'],
            'updated': result['updated'],
            'deleted': deleted
        }

    def _delete_zero_stock_records(self, company_id):
        """
        Elimina registros de productos que ya no tienen stock.

        Esto mantiene la tabla pequena al conservar solo productos
        que actualmente tienen inventario.

        Args:
            company_id: ID de la compania a procesar

        Returns:
            Numero de registros eliminados
        """
        self.env.cr.execute("""
            DELETE FROM product_rotation_daily prd
            WHERE prd.company_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM stock_quant sq
                JOIN stock_location sl ON sq.location_id = sl.id
                WHERE sq.product_id = prd.product_id
                AND sl.usage = 'internal'
                AND sq.company_id = %s
                AND sq.quantity > 0
            )
        """, (company_id, company_id))

        return self.env.cr.rowcount

    def _execute_incremental_update(self, company_id, today, now):
        """
        Ejecuta la actualizacion incremental principal usando SQL optimizado.

        Esta consulta usa CTEs para eficiencia:
        - current_stock: Productos con stock positivo por bodega
        - last_sales: Ultima fecha de venta por producto/bodega
        - last_transfers: Ultima fecha de transferencia por producto/bodega
        - rotation_data: Datos combinados con campos calculados

        El UPSERT final maneja inserciones y actualizaciones atomicamente.

        Logica del valor centinela 9999:
        - Si last_sale_date IS NULL -> days_without_sale = 9999 (nunca vendido)
        - Si last_transfer_date IS NULL -> days_without_transfer = 9999 (nunca transferido)
        - Si ambos son NULL -> days_without_rotation = 9999 (nunca movido)

        Args:
            company_id: ID de compania a procesar
            today: Fecha actual para calculos
            now: Datetime actual para updated_at

        Returns:
            dict con conteos de inserted y updated
        """

        # Consulta SQL optimizada con CTEs
        # IMPORTANTE: Usamos product_warehouse_sale_summary para ventas (tabla pre-agregada)
        # y stock_move solo para transferencias
        query = """
            WITH
            -- ================================================================
            -- CTE 1: Stock actual por producto/bodega
            -- Solo productos con stock positivo en ubicaciones internas
            -- ================================================================
            current_stock AS (
                SELECT
                    sq.product_id,
                    sw.id AS warehouse_id,
                    sq.company_id,
                    SUM(sq.quantity) AS stock_on_hand
                FROM stock_quant sq
                JOIN stock_location sl ON sq.location_id = sl.id
                JOIN stock_warehouse sw ON sl.warehouse_id = sw.id
                WHERE sq.company_id = %(company_id)s
                AND sl.usage = 'internal'
                AND sq.quantity > 0
                GROUP BY sq.product_id, sw.id, sq.company_id
                HAVING SUM(sq.quantity) > 0
            ),

            -- ================================================================
            -- CTE 2: Ultima fecha de venta por producto/bodega
            -- Fuente: product_warehouse_sale_summary (tabla pre-agregada, eficiente)
            -- ================================================================
            last_sales AS (
                SELECT
                    pwss.product_id,
                    pwss.warehouse_id,
                    MAX(pwss.date) AS last_sale_date
                FROM product_warehouse_sale_summary pwss
                WHERE pwss.warehouse_id IS NOT NULL
                AND pwss.quantity_sold > 0
                GROUP BY pwss.product_id, pwss.warehouse_id
            ),

            -- ================================================================
            -- CTE 3: Ultima fecha de transferencia por producto/bodega
            -- Fuente: stock.move (solo movimientos confirmados)
            -- Incluye: transferencias internas, recepciones, devoluciones, ajustes
            -- ================================================================
            last_transfers AS (
                SELECT
                    sm.product_id,
                    COALESCE(sw_src.id, sw_dest.id) AS warehouse_id,
                    MAX(sm.date::date) AS last_transfer_date
                FROM stock_move sm
                JOIN stock_location sl_src ON sm.location_id = sl_src.id
                JOIN stock_location sl_dest ON sm.location_dest_id = sl_dest.id
                LEFT JOIN stock_warehouse sw_src ON sl_src.warehouse_id = sw_src.id
                LEFT JOIN stock_warehouse sw_dest ON sl_dest.warehouse_id = sw_dest.id
                WHERE sm.company_id = %(company_id)s
                AND sm.state = 'done'
                AND (
                    -- Transferencia interna entre ubicaciones
                    (sl_src.usage = 'internal' AND sl_dest.usage = 'internal')
                    -- Recepcion de proveedor
                    OR (sl_src.usage = 'supplier' AND sl_dest.usage = 'internal')
                    -- Devolucion de cliente
                    OR (sl_src.usage = 'customer' AND sl_dest.usage = 'internal')
                    -- Ajuste de inventario (entrada)
                    OR (sl_src.usage = 'inventory' AND sl_dest.usage = 'internal')
                    -- Ajuste de inventario (salida)
                    OR (sl_src.usage = 'internal' AND sl_dest.usage = 'inventory')
                )
                GROUP BY sm.product_id, COALESCE(sw_src.id, sw_dest.id)
            ),

            -- ================================================================
            -- CTE 4: Combinar datos y calcular metricas
            -- Logica del valor 9999:
            --   - Si fecha es NULL -> dias = 9999 (significa "NUNCA")
            --   - Si fecha existe -> dias = HOY - fecha (0 = hoy, maxima rotacion)
            -- ================================================================
            rotation_data AS (
                SELECT
                    cs.product_id,
                    cs.warehouse_id,
                    cs.company_id,
                    cs.stock_on_hand,
                    ls.last_sale_date,
                    lt.last_transfer_date,
                    -- Ultima rotacion = la mas reciente de cualquier actividad
                    GREATEST(
                        COALESCE(ls.last_sale_date, '1900-01-01'::date),
                        COALESCE(lt.last_transfer_date, '1900-01-01'::date)
                    ) AS last_rotation_calc,
                    -- Dias sin venta: 9999 si NUNCA, dias reales si tiene fecha
                    CASE
                        WHEN ls.last_sale_date IS NULL THEN %(max_days_value)s
                        ELSE (%(today)s - ls.last_sale_date)
                    END AS days_without_sale,
                    -- Dias sin transferencia: 9999 si NUNCA, dias reales si tiene fecha
                    CASE
                        WHEN lt.last_transfer_date IS NULL THEN %(max_days_value)s
                        ELSE (%(today)s - lt.last_transfer_date)
                    END AS days_without_transfer
                FROM current_stock cs
                LEFT JOIN last_sales ls
                    ON cs.product_id = ls.product_id
                    AND cs.warehouse_id = ls.warehouse_id
                LEFT JOIN last_transfers lt
                    ON cs.product_id = lt.product_id
                    AND cs.warehouse_id = lt.warehouse_id
            ),

            -- ================================================================
            -- CTE 5: Datos finales con todos los campos calculados
            -- Logica de flags:
            --   - TRUE si dias = 9999 (nunca) O dias >= umbral
            -- ================================================================
            final_data AS (
                SELECT
                    rd.product_id,
                    rd.warehouse_id,
                    rd.company_id,
                    rd.stock_on_hand,
                    rd.last_sale_date,
                    rd.last_transfer_date,
                    -- Fecha de ultima rotacion (NULL si nunca hubo movimiento)
                    CASE
                        WHEN rd.last_rotation_calc = '1900-01-01'::date THEN NULL
                        ELSE rd.last_rotation_calc
                    END AS last_rotation_date,
                    rd.days_without_sale,
                    rd.days_without_transfer,
                    -- Dias sin rotacion: si ambos son 9999, resultado es 9999; sino el minimo real
                    CASE
                        WHEN rd.days_without_sale = %(max_days_value)s AND rd.days_without_transfer = %(max_days_value)s THEN %(max_days_value)s
                        WHEN rd.days_without_sale = %(max_days_value)s THEN rd.days_without_transfer
                        WHEN rd.days_without_transfer = %(max_days_value)s THEN rd.days_without_sale
                        ELSE LEAST(rd.days_without_sale, rd.days_without_transfer)
                    END AS days_without_rotation,
                    -- Flag sin ventas: TRUE si nunca (9999) O si >= umbral
                    (rd.days_without_sale = %(max_days_value)s OR rd.days_without_sale >= %(threshold_sale)s) AS flag_no_sales,
                    -- Flag sin transferencias: TRUE si nunca (9999) O si >= umbral
                    (rd.days_without_transfer = %(max_days_value)s OR rd.days_without_transfer >= %(threshold_transfer)s) AS flag_no_transfers,
                    -- Flag sin rotacion: calculado sobre el resultado de days_without_rotation
                    CASE
                        WHEN rd.days_without_sale = %(max_days_value)s AND rd.days_without_transfer = %(max_days_value)s THEN TRUE
                        WHEN rd.days_without_sale = %(max_days_value)s THEN rd.days_without_transfer >= %(threshold_rotation)s
                        WHEN rd.days_without_transfer = %(max_days_value)s THEN rd.days_without_sale >= %(threshold_rotation)s
                        ELSE LEAST(rd.days_without_sale, rd.days_without_transfer) >= %(threshold_rotation)s
                    END AS flag_no_rotation,
                    %(now)s AS updated_at
                FROM rotation_data rd
            )

            -- ================================================================
            -- UPSERT: Insertar nuevos registros o actualizar existentes
            -- ================================================================
            INSERT INTO product_rotation_daily (
                product_id,
                warehouse_id,
                company_id,
                stock_on_hand,
                last_sale_date,
                last_transfer_date,
                last_rotation_date,
                days_without_sale,
                days_without_transfer,
                days_without_rotation,
                flag_no_sales,
                flag_no_transfers,
                flag_no_rotation,
                updated_at,
                create_uid,
                create_date,
                write_uid,
                write_date
            )
            SELECT
                fd.product_id,
                fd.warehouse_id,
                fd.company_id,
                fd.stock_on_hand,
                fd.last_sale_date,
                fd.last_transfer_date,
                fd.last_rotation_date,
                fd.days_without_sale,
                fd.days_without_transfer,
                fd.days_without_rotation,
                fd.flag_no_sales,
                fd.flag_no_transfers,
                fd.flag_no_rotation,
                fd.updated_at,
                1,  -- create_uid (admin)
                fd.updated_at,
                1,  -- write_uid (admin)
                fd.updated_at
            FROM final_data fd
            ON CONFLICT (product_id, warehouse_id)
            DO UPDATE SET
                stock_on_hand = EXCLUDED.stock_on_hand,
                last_sale_date = EXCLUDED.last_sale_date,
                last_transfer_date = EXCLUDED.last_transfer_date,
                last_rotation_date = EXCLUDED.last_rotation_date,
                days_without_sale = EXCLUDED.days_without_sale,
                days_without_transfer = EXCLUDED.days_without_transfer,
                days_without_rotation = EXCLUDED.days_without_rotation,
                flag_no_sales = EXCLUDED.flag_no_sales,
                flag_no_transfers = EXCLUDED.flag_no_transfers,
                flag_no_rotation = EXCLUDED.flag_no_rotation,
                updated_at = EXCLUDED.updated_at,
                write_uid = EXCLUDED.write_uid,
                write_date = EXCLUDED.write_date;
        """

        params = {
            'company_id': company_id,
            'today': today,
            'now': now,
            'max_days_value': MAX_DAYS_VALUE,
            'threshold_sale': DAYS_NO_SALE_THRESHOLD,
            'threshold_transfer': DAYS_NO_TRANSFER_THRESHOLD,
            'threshold_rotation': DAYS_NO_ROTATION_THRESHOLD,
        }

        self.env.cr.execute(query, params)

        # PostgreSQL no indica directamente inserts vs updates en UPSERT
        total_affected = self.env.cr.rowcount

        # Obtener conteo actual para esta compania
        self.env.cr.execute("""
            SELECT COUNT(*) FROM product_rotation_daily WHERE company_id = %s
        """, (company_id,))
        current_count = self.env.cr.fetchone()[0]

        return {
            'inserted': 0,  # Se recalcula a nivel de resumen
            'updated': total_affected,
            'total': total_affected
        }

    # =========================================================================
    # ACCIONES MANUALES
    # =========================================================================

    @api.model
    def action_force_full_recalculation(self):
        """
        Fuerza un recalculo completo de todos los datos de rotacion.

        ADVERTENCIA: Este metodo solo debe usarse para:
        - Configuracion inicial
        - Recuperacion de datos
        - Migracion del sistema

        Para operaciones normales, usar el cron incremental.
        """
        _logger.warning("ROTACION: Iniciando recalculo COMPLETO (activacion manual)")

        # Truncar tabla para inicio limpio
        self.env.cr.execute("TRUNCATE TABLE product_rotation_daily RESTART IDENTITY;")

        # Ejecutar actualizacion incremental (insertara todos los registros)
        self._cron_update_rotation_daily()

        _logger.info("ROTACION: Recalculo completo finalizado")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recalculo Completado'),
                'message': _('Los datos de rotacion de productos han sido recalculados completamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # =========================================================================
    # METODOS AUXILIARES
    # =========================================================================

    def get_rotation_summary(self, company_id=None):
        """
        Obtiene un resumen de estadisticas de rotacion.

        Args:
            company_id: Filtro opcional por compania

        Returns:
            dict con estadisticas de resumen
        """
        domain = []
        if company_id:
            domain.append(('company_id', '=', company_id))

        total = self.search_count(domain)
        no_rotation = self.search_count(domain + [('flag_no_rotation', '=', True)])
        no_sales = self.search_count(domain + [('flag_no_sales', '=', True)])
        no_transfers = self.search_count(domain + [('flag_no_transfers', '=', True)])

        return {
            'total_products': total,
            'no_rotation': no_rotation,
            'no_sales': no_sales,
            'no_transfers': no_transfers,
            'rotation_percentage': round((total - no_rotation) / total * 100, 2) if total > 0 else 0,
        }

    @api.model
    def action_view_rotation_dashboard(self):
        """
        Retorna accion para abrir vista de analisis de rotacion.
        """
        return {
            'name': _('Analisis de Rotacion de Productos'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.rotation.daily',
            'view_mode': 'tree,kanban,form',
            'context': {
                'search_default_filter_no_rotation': 1,
            },
            'target': 'current',
        }

    # =========================================================================
    # CRON SEMANAL: LIMPIEZA DE DATOS
    # =========================================================================

    @api.model
    def _cron_weekly_cleanup(self):
        """
        Cron semanal de limpieza para asegurar integridad de datos.

        Este cron:
        1. Elimina registros de productos eliminados/inactivos
        2. Elimina registros de bodegas eliminadas/inactivas
        3. Elimina registros de companias inactivas
        4. Ejecuta ANALYZE para optimizar planificador de consultas
        """
        start_time = datetime.now()
        _logger.info("ROTACION: Iniciando limpieza semanal")

        try:
            # Eliminar registros de productos inactivos/eliminados
            self.env.cr.execute("""
                DELETE FROM product_rotation_daily prd
                WHERE NOT EXISTS (
                    SELECT 1 FROM product_product pp
                    WHERE pp.id = prd.product_id
                    AND pp.active = TRUE
                )
            """)
            deleted_products = self.env.cr.rowcount

            # Eliminar registros de bodegas inactivas/eliminadas
            self.env.cr.execute("""
                DELETE FROM product_rotation_daily prd
                WHERE NOT EXISTS (
                    SELECT 1 FROM stock_warehouse sw
                    WHERE sw.id = prd.warehouse_id
                    AND sw.active = TRUE
                )
            """)
            deleted_warehouses = self.env.cr.rowcount

            # Eliminar registros de companias inactivas
            self.env.cr.execute("""
                DELETE FROM product_rotation_daily prd
                WHERE NOT EXISTS (
                    SELECT 1 FROM res_company rc
                    WHERE rc.id = prd.company_id
                    AND rc.active = TRUE
                )
            """)
            deleted_companies = self.env.cr.rowcount

            # Analizar tabla para optimizador de consultas
            self.env.cr.execute("ANALYZE product_rotation_daily")

            self.env.cr.commit()

            elapsed = (datetime.now() - start_time).total_seconds()
            _logger.info(f"ROTACION: Limpieza semanal completada en {elapsed:.2f} segundos")
            _logger.info(f"  - Eliminados (productos inactivos): {deleted_products}")
            _logger.info(f"  - Eliminados (bodegas inactivas): {deleted_warehouses}")
            _logger.info(f"  - Eliminados (companias inactivas): {deleted_companies}")

            return True

        except Exception as e:
            _logger.error(f"ROTACION: Error durante limpieza semanal - {str(e)}")
            self.env.cr.rollback()
            raise

    # =========================================================================
    # ACTIVIDADES PARA REVISORES
    # =========================================================================

    # Numero de productos criticos a mostrar en la lista de la actividad
    ACTIVITY_PRODUCTS_LIMIT = 15

    @api.model
    def _create_review_activities(self):
        """
        Crea UNA actividad de revision por cada usuario del grupo 'Revisor de Rotacion'.

        Este metodo:
        1. Cuenta productos criticos (sin rotacion + con stock)
        2. Obtiene los 15 productos mas criticos para mostrar en la nota
        3. Obtiene usuarios del grupo revisor
        4. Crea UNA actividad por revisor con la lista de productos criticos

        La actividad esta anclada al primer producto critico pero contiene
        la lista completa de los 15 productos mas criticos en la nota.
        """
        try:
            # Obtener el conteo total de productos criticos
            total_critical = self.search_count([
                ('flag_no_rotation', '=', True),
                ('stock_on_hand', '>', 0)
            ])

            if total_critical == 0:
                _logger.info("ROTACION: No hay productos criticos, no se crean actividades")
                return

            # Obtener los primeros N productos mas criticos para mostrar en la nota
            critical_products = self.search([
                ('flag_no_rotation', '=', True),
                ('stock_on_hand', '>', 0)
            ], order='days_without_rotation DESC', limit=self.ACTIVITY_PRODUCTS_LIMIT)

            # Obtener usuarios del grupo revisor
            group_reviewer = self.env.ref(
                'product_rotation.group_rotation_reviewer',
                raise_if_not_found=False
            )

            if not group_reviewer:
                _logger.warning("ROTACION: Grupo de revisores no encontrado, no se crean actividades")
                return

            reviewer_users = group_reviewer.users
            if not reviewer_users:
                _logger.info("ROTACION: No hay usuarios en el grupo revisor")
                return

            # Obtener tipo de actividad
            activity_type = self.env.ref(
                'product_rotation.mail_activity_type_rotation_review',
                raise_if_not_found=False
            )

            if not activity_type:
                _logger.warning("ROTACION: Tipo de actividad no encontrado")
                return

            # Usar el primer producto critico como ancla para la actividad
            first_critical = critical_products[0]

            # Fecha de vencimiento: hoy (revision urgente)
            today = date.today()
            model_id = self.env['ir.model']._get('product.rotation.daily').id

            # Generar la nota con la lista de productos
            note = self._get_activity_note_with_list(critical_products, total_critical)
            summary = f"Revisar {total_critical} productos sin rotacion"

            activities_created = 0
            activities_updated = 0

            # Crear UNA actividad por cada revisor
            for user in reviewer_users:
                # Verificar si ya existe una actividad pendiente para este usuario
                # Buscar en cualquier producto de rotacion (no solo el primero)
                existing_activity = self.env['mail.activity'].search([
                    ('res_model', '=', 'product.rotation.daily'),
                    ('activity_type_id', '=', activity_type.id),
                    ('user_id', '=', user.id),
                ], limit=1)

                if existing_activity:
                    # Actualizar actividad existente (puede cambiar el producto ancla)
                    existing_activity.write({
                        'res_id': first_critical.id,
                        'note': note,
                        'summary': summary,
                        'date_deadline': today,
                    })
                    activities_updated += 1
                else:
                    # Crear nueva actividad
                    self.env['mail.activity'].create({
                        'res_model_id': model_id,
                        'res_id': first_critical.id,
                        'activity_type_id': activity_type.id,
                        'user_id': user.id,
                        'date_deadline': today,
                        'summary': summary,
                        'note': note,
                    })
                    activities_created += 1

            self.env.cr.commit()
            _logger.info(
                f"ROTACION: Actividades - creadas: {activities_created}, "
                f"actualizadas: {activities_updated}, "
                f"revisores: {len(reviewer_users)}, "
                f"total criticos: {total_critical}"
            )

        except Exception as e:
            _logger.error(f"ROTACION: Error creando actividades - {str(e)}")
            # No propagamos el error para no afectar el cron principal

    def _get_activity_note_with_list(self, critical_products, total_critical):
        """
        Genera la nota HTML con la lista de productos criticos.

        Args:
            critical_products: Recordset de los productos mas criticos
            total_critical: Total de productos criticos

        Returns:
            str: Nota HTML formateada con tabla de productos
        """
        # Construir filas de la tabla
        rows = []
        for idx, pr in enumerate(critical_products, 1):
            days = pr.days_without_rotation
            days_text = "NUNCA" if days == MAX_DAYS_VALUE else f"{days}d"
            days_class = "color:red; font-weight:bold;" if days == MAX_DAYS_VALUE or days >= 60 else ""

            product_name = pr.product_id.name or 'Sin nombre'
            product_ref = pr.product_id.default_code or '-'
            warehouse = pr.warehouse_id.name or '-'
            stock = pr.stock_on_hand

            rows.append(f"""
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding:6px; text-align:center;">{idx}</td>
                <td style="padding:6px; {days_class}">{days_text}</td>
                <td style="padding:6px;">{product_name[:40]}</td>
                <td style="padding:6px;">{product_ref}</td>
                <td style="padding:6px;">{warehouse}</td>
                <td style="padding:6px; text-align:right;">{stock:.0f}</td>
            </tr>""")

        rows_html = "".join(rows)
        remaining = total_critical - len(critical_products)
        remaining_text = f"<p style='color:gray;'>... y {remaining} productos mas</p>" if remaining > 0 else ""

        return f"""
<p><strong>Revision de Productos Sin Rotacion</strong></p>
<p>Se detectaron <strong style="color:red;">{total_critical}</strong> productos criticos (sin rotacion + con stock).</p>

<table style="width:100%; border-collapse: collapse; font-size:13px; margin-top:10px;">
    <thead>
        <tr style="background-color:#f5f5f5; border-bottom:2px solid #ddd;">
            <th style="padding:8px; text-align:center;">#</th>
            <th style="padding:8px; text-align:left;">Dias</th>
            <th style="padding:8px; text-align:left;">Producto</th>
            <th style="padding:8px; text-align:left;">Ref</th>
            <th style="padding:8px; text-align:left;">Bodega</th>
            <th style="padding:8px; text-align:right;">Stock</th>
        </tr>
    </thead>
    <tbody>
        {rows_html}
    </tbody>
</table>

{remaining_text}

<p style="margin-top:15px; padding:10px; background-color:#fff3cd; border-radius:4px;">
    <strong>Accion requerida:</strong> Revisar estos productos y decidir acciones sobre el inventario estancado.
    <br/><em>Ir a: Inventario > Analisis de Rotacion > Productos Criticos</em>
</p>
"""

    # =========================================================================
    # METODOS DE VISUALIZACION
    # =========================================================================

    def _get_rotation_status_color(self):
        """
        Obtiene indicador de color basado en estado de rotacion.
        Usado para kanban y otras visualizaciones.

        Returns:
            int: Indice de color (0-10)
                1 = Rojo (critico)
                2 = Naranja (alerta)
                3 = Amarillo (precaucion)
                10 = Verde (normal)
        """
        self.ensure_one()
        if self.flag_no_rotation:
            return 1  # Rojo - critico
        elif self.flag_no_sales and self.flag_no_transfers:
            return 2  # Naranja - alerta
        elif self.flag_no_sales or self.flag_no_transfers:
            return 3  # Amarillo - precaucion
        else:
            return 10  # Verde - normal
