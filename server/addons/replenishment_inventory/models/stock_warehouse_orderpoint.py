import math
from odoo import api, fields, models, _


class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    point_reorder = fields.Float(string='Punto de Reorden', default=0)

    # Campos para mostrar estadísticas rolling (read-only, calculados)
    rolling_mean_30d = fields.Float(
        string='Media 30d',
        compute='_compute_rolling_stats',
        digits=(16, 4),
        help='Media diaria de ventas/transferencias últimos 30 días'
    )
    rolling_stddev_30d = fields.Float(
        string='Desv. Est. 30d',
        compute='_compute_rolling_stats',
        digits=(16, 4),
        help='Desviación estándar últimos 30 días'
    )
    rolling_cv_30d = fields.Float(
        string='Coef. Var. 30d',
        compute='_compute_rolling_stats',
        digits=(16, 4),
        help='Coeficiente de variación = stddev/mean'
    )

    # -------------------------------------------------------------------------
    # Integración con Rolling Stats (Arquitectura 4 Capas)
    # -------------------------------------------------------------------------
    @api.depends('product_id', 'warehouse_id')
    def _compute_rolling_stats(self):
        """
        Calcula las estadísticas rolling desde la tabla precalculada.

        Usa product.sales.stats.rolling para obtener los valores
        sin necesidad de recalcular en tiempo real.
        """
        RollingStats = self.env.get('product.sales.stats.rolling')

        for record in self:
            if not RollingStats or not record.product_id or not record.warehouse_id:
                record.rolling_mean_30d = 0.0
                record.rolling_stddev_30d = 0.0
                record.rolling_cv_30d = 0.0
                continue

            # Obtener stats del warehouse
            # Para warehouses híbridos, usar 'combined'
            warehouse = record.warehouse_id
            record_type = 'combined' if self._is_hybrid_warehouse(warehouse) else 'sale'

            stats = RollingStats.get_stats(
                product_id=record.product_id.id,
                warehouse_id=record.warehouse_id.id,
                record_type=record_type,
                days=30
            )

            record.rolling_mean_30d = stats.get('mean', 0.0)
            record.rolling_stddev_30d = stats.get('stddev', 0.0)
            record.rolling_cv_30d = stats.get('cv', 0.0)

    def _is_hybrid_warehouse(self, warehouse):
        """
        Determina si un warehouse es híbrido (usa ventas + transferencias).

        Por defecto solo BODMA usa transferencias.
        Puede extenderse para otros warehouses.
        """
        return warehouse.code == 'BODMA'

    def get_replenishment_stats(self, days=30, record_type=None):
        """
        Obtiene estadísticas para cálculo de reabastecimiento.

        Este método es el punto de entrada para obtener mean/stddev
        para cálculos de punto de reorden, safety stock, etc.

        Args:
            days: Período (30, 60, o 90)
            record_type: 'sale', 'transfer', 'combined', o None (auto)

        Returns:
            dict: {mean, stddev, cv, total_qty, days_with_sales}
        """
        self.ensure_one()

        RollingStats = self.env.get('product.sales.stats.rolling')
        if not RollingStats:
            return self._fallback_calculate_stats(days)

        # Determinar tipo de registro automáticamente
        if record_type is None:
            warehouse = self.warehouse_id
            record_type = 'combined' if self._is_hybrid_warehouse(warehouse) else 'sale'

        stats = RollingStats.get_stats(
            product_id=self.product_id.id,
            warehouse_id=self.warehouse_id.id,
            record_type=record_type,
            days=days
        )

        # Si no hay stats precalculados, usar fallback
        if not stats.get('found', False):
            return self._fallback_calculate_stats(days)

        return stats

    def _fallback_calculate_stats(self, days=30):
        """
        Calcula estadísticas directamente si rolling stats no está disponible.

        Método de respaldo para cuando:
        - El módulo de 4 capas no está instalado
        - No hay datos precalculados para el producto/warehouse

        Args:
            days: Período de cálculo

        Returns:
            dict: {mean, stddev, cv, total_qty, days_with_sales}
        """
        ProductStats = self.env.get('product.sales.stats')
        if not ProductStats:
            return {
                'mean': 0.0,
                'stddev': 0.0,
                'cv': 0.0,
                'total_qty': 0.0,
                'days_with_sales': 0,
                'found': False
            }

        # Usar el método existente de product.sales.stats
        return ProductStats._compute_statistics(
            self.product_id.id,
            self.warehouse_id.id,
            days
        )

    def calculate_reorder_point(self, lead_time_days=7, service_level_z=1.65, days=30):
        """
        Calcula el punto de reorden usando las estadísticas rolling.

        Fórmula: ROP = (mean * lead_time) + (z * stddev * sqrt(lead_time))

        Args:
            lead_time_days: Tiempo de entrega del proveedor en días
            service_level_z: Factor Z para nivel de servicio
                             (1.65 = 95%, 2.33 = 99%)
            days: Período para estadísticas (30, 60, 90)

        Returns:
            float: Punto de reorden calculado
        """
        self.ensure_one()

        stats = self.get_replenishment_stats(days=days)

        mean = stats.get('mean', 0.0)
        stddev = stats.get('stddev', 0.0)

        if mean <= 0:
            return 0.0

        # Safety stock = z * stddev * sqrt(lead_time)
        safety_stock = service_level_z * stddev * math.sqrt(lead_time_days)

        # Reorder point = demanda durante lead time + safety stock
        reorder_point = (mean * lead_time_days) + safety_stock

        return round(reorder_point, 2)

    def calculate_max_qty(self, lead_time_days=7, review_period_days=7,
                          service_level_z=1.65, days=30):
        """
        Calcula la cantidad máxima (para sistemas min-max).

        Fórmula: Max = ROP + (mean * review_period)

        Args:
            lead_time_days: Tiempo de entrega
            review_period_days: Período de revisión del inventario
            service_level_z: Factor Z
            days: Período para estadísticas

        Returns:
            float: Cantidad máxima calculada
        """
        self.ensure_one()

        rop = self.calculate_reorder_point(
            lead_time_days=lead_time_days,
            service_level_z=service_level_z,
            days=days
        )

        stats = self.get_replenishment_stats(days=days)
        mean = stats.get('mean', 0.0)

        max_qty = rop + (mean * review_period_days)

        return round(max_qty, 2)

    # -------------------------------------------------------------------------
    # Utilidades para filtrar por Bodega Matilde
    # -------------------------------------------------------------------------
    def _is_matilde_orderpoint(self):
        """Determina si la regla corresponde a la Bodega Matilde.

        Se basa en el código del almacén (BODMA), siguiendo la convención
        ya usada en el módulo `sales_report` (búsqueda por código 'BODMA').
        """
        self.ensure_one()
        warehouse = self.location_id.warehouse_id or self.warehouse_id
        if not warehouse:
            return False
        return warehouse.code == 'BODMA'

    # -------------------------------------------------------------------------
    # Cálculo de qty_to_order basado en configuración del almacén
    # -------------------------------------------------------------------------
    @api.depends('qty_multiple', 'product_min_qty', 'product_max_qty', 'visibility_days',
                 'product_id', 'location_id', 'product_id.seller_ids.delay',
                 'point_reorder', 'warehouse_id.replenishment_alert_based_on')
    def _compute_qty_to_order(self):
        """
        Sobrescribe el cálculo de qty_to_order para usar la configuración del almacén.

        Si el almacén está configurado para usar 'reorder_point', compara con point_reorder.
        Si está configurado para usar 'min_qty' (default), compara con product_min_qty.
        """
        from odoo.tools import float_compare, float_is_zero

        for orderpoint in self:
            if not orderpoint.product_id or not orderpoint.location_id:
                orderpoint.qty_to_order = False
                continue

            qty_to_order = 0.0
            rounding = orderpoint.product_uom.rounding

            # Determinar qué valor usar según la configuración del almacén
            alert_based_on = orderpoint.warehouse_id.replenishment_alert_based_on or 'min_qty'

            if alert_based_on == 'reorder_point':
                threshold = orderpoint.point_reorder
            else:
                threshold = orderpoint.product_min_qty

            # Comparar forecast con el umbral configurado
            if float_compare(orderpoint.qty_forecast, threshold, precision_rounding=rounding) < 0:
                # Calcular cantidad a ordenar considerando visibility_days
                product_context = orderpoint._get_product_context(visibility_days=orderpoint.visibility_days)
                qty_forecast_with_visibility = orderpoint.product_id.with_context(product_context).read(['virtual_available'])[0]['virtual_available'] + orderpoint._quantity_in_progress()[orderpoint.id]
                qty_to_order = max(threshold, orderpoint.product_max_qty) - qty_forecast_with_visibility

                # Aplicar múltiplo de cantidad
                remainder = orderpoint.qty_multiple > 0.0 and qty_to_order % orderpoint.qty_multiple or 0.0
                if (float_compare(remainder, 0.0, precision_rounding=rounding) > 0
                        and float_compare(orderpoint.qty_multiple - remainder, 0.0, precision_rounding=rounding) > 0):
                    qty_to_order += orderpoint.qty_multiple - remainder

            orderpoint.qty_to_order = qty_to_order

    # -------------------------------------------------------------------------
    # Desactivar cotizaciones automáticas para Bodega Matilde
    # -------------------------------------------------------------------------
    def _procure_orderpoint_confirm(self, use_new_cursor=False, company_id=None, raise_user_error=True):
        """Sobrescribe el comportamiento estándar para excluir Bodega Matilde.

        - Para orderpoints de Bodega Matilde NO se generan movimientos/compras
          automáticas (ni por scheduler ni por acciones masivas).
        - El resto de bodegas se comportan igual que en el core.
        """
        # Filtrar las reglas que NO son de Bodega Matilde
        orderpoints = self.filtered(lambda op: not op._is_matilde_orderpoint())
        if not orderpoints:
            # No hay nada que procesar fuera de Matilde
            return {}

        return super(StockWarehouseOrderpoint, orderpoints)._procure_orderpoint_confirm(
            use_new_cursor=use_new_cursor,
            company_id=company_id,
            raise_user_error=raise_user_error,
        )
