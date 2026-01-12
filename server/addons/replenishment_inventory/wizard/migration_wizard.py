# -*- coding: utf-8 -*-
"""
Wizard para Migración de Datos Históricos

Permite ejecutar la migración de datos desde la interfaz de Odoo
sin necesidad de usar el shell.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ReplenishmentMigrationWizard(models.TransientModel):
    _name = 'replenishment.migration.wizard'
    _description = 'Wizard de Migración de Reabastecimiento'

    days_back = fields.Integer(
        string='Días de Historial',
        default=90,
        required=True,
        help='Cantidad de días hacia atrás para migrar datos históricos'
    )
    batch_size = fields.Integer(
        string='Tamaño de Lote',
        default=5000,
        required=True,
        help='Cantidad de registros a procesar por lote'
    )
    action_type = fields.Selection([
        ('migrate', 'Migrar Datos Históricos'),
        ('recalculate', 'Recalcular Rolling Stats'),
        ('recalculate_global', 'Recalcular Stats Globales (Bodega Principal)'),
        ('recalculate_orderpoints', 'Recalcular MAX/MIN (Orderpoints)'),
        ('verify', 'Verificar Migración'),
        ('cleanup', 'Limpiar y Reiniciar (PELIGROSO)'),
    ], string='Acción', default='migrate', required=True)

    # Campos de resultado (solo lectura)
    result_text = fields.Text(
        string='Resultado',
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Configuración'),
        ('done', 'Completado'),
    ], default='draft')

    # Estadísticas actuales
    daily_stats_count = fields.Integer(
        string='Registros en Daily Stats',
        compute='_compute_stats'
    )
    rolling_stats_count = fields.Integer(
        string='Registros en Rolling Stats',
        compute='_compute_stats'
    )
    queue_count = fields.Integer(
        string='Eventos en Cola',
        compute='_compute_stats'
    )

    @api.depends('state')
    def _compute_stats(self):
        """Calcula estadísticas actuales de las tablas."""
        for wizard in self:
            try:
                self.env.cr.execute(
                    "SELECT COUNT(*) FROM product_sales_stats_daily"
                )
                wizard.daily_stats_count = self.env.cr.fetchone()[0]

                self.env.cr.execute(
                    "SELECT COUNT(*) FROM product_sales_stats_rolling"
                )
                wizard.rolling_stats_count = self.env.cr.fetchone()[0]

                self.env.cr.execute(
                    "SELECT COUNT(*) FROM product_replenishment_queue"
                )
                wizard.queue_count = self.env.cr.fetchone()[0]
            except Exception:
                wizard.daily_stats_count = 0
                wizard.rolling_stats_count = 0
                wizard.queue_count = 0

    def action_execute(self):
        """Ejecuta la acción seleccionada."""
        self.ensure_one()
        Migration = self.env['replenishment.data.migration']

        if self.action_type == 'migrate':
            result = Migration.migrate_to_new_architecture(
                days_back=self.days_back,
                batch_size=self.batch_size
            )
            self.result_text = self._format_migration_result(result)

        elif self.action_type == 'recalculate':
            RollingStats = self.env['product.sales.stats.rolling']
            result = RollingStats.recalculate_all_stats(batch_size=self.batch_size)
            self.result_text = self._format_recalculate_result(result)

        elif self.action_type == 'recalculate_global':
            RollingStats = self.env['product.sales.stats.rolling']
            result = RollingStats.update_global_rolling_stats(batch_size=self.batch_size)
            self.result_text = self._format_global_result(result)

        elif self.action_type == 'recalculate_orderpoints':
            Processor = self.env['replenishment.queue.processor']
            result = Processor.recalculate_all_orderpoints(batch_size=self.batch_size)
            self.result_text = self._format_orderpoints_result(result)

        elif self.action_type == 'verify':
            result = Migration.verify_migration()
            self.result_text = self._format_verify_result(result)

        elif self.action_type == 'cleanup':
            result = Migration.cleanup_and_reset()
            self.result_text = self._format_cleanup_result(result)

        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset(self):
        """Reinicia el wizard para una nueva ejecución."""
        self.ensure_one()
        self.state = 'draft'
        self.result_text = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _format_migration_result(self, result):
        """Formatea el resultado de la migración."""
        lines = [
            "═" * 50,
            "  MIGRACIÓN COMPLETADA",
            "═" * 50,
            "",
            f"✓ Daily Stats creados: {result.get('daily_stats_created', 0):,}",
            f"✓ Rolling Stats creados: {result.get('rolling_stats_created', 0):,}",
        ]

        errors = result.get('errors', [])
        if errors:
            lines.extend([
                "",
                "⚠ ERRORES:",
            ])
            for error in errors:
                lines.append(f"  • {error}")
        else:
            lines.extend([
                "",
                "✓ Sin errores",
            ])

        return "\n".join(lines)

    def _format_recalculate_result(self, result):
        """Formatea el resultado del recálculo."""
        lines = [
            "═" * 50,
            "  RECÁLCULO COMPLETADO",
            "═" * 50,
            "",
            f"✓ Rolling Stats actualizados: {result.get('updated', 0):,}",
            f"✗ Errores: {result.get('errors', 0)}",
            "",
            "Los stddev ahora incluyen el piso Poisson (sqrt(mean)).",
        ]

        return "\n".join(lines)

    def _format_global_result(self, result):
        """Formatea el resultado del recálculo de stats globales."""
        lines = [
            "═" * 50,
            "  STATS GLOBALES COMPLETADO",
            "═" * 50,
            "",
            f"✓ Productos actualizados: {result.get('updated', 0):,}",
            f"✗ Errores: {result.get('errors', 0)}",
            "",
            "Las estadísticas globales (suma de todas las bodegas)",
            "ahora están disponibles para la bodega principal.",
            "",
            "Nota: Las stats se actualizan automáticamente con cada",
            "procesamiento de la cola. Este recálculo masivo solo es",
            "necesario para la carga inicial de datos históricos.",
        ]

        if result.get('message'):
            lines.extend([
                "",
                f"⚠ {result.get('message')}",
            ])

        return "\n".join(lines)

    def _format_orderpoints_result(self, result):
        """Formatea el resultado del recálculo de orderpoints."""
        lines = [
            "═" * 50,
            "  RECÁLCULO DE MAX/MIN COMPLETADO",
            "═" * 50,
            "",
            f"✓ Orderpoints actualizados: {result.get('updated', 0):,}",
            f"✓ Orderpoints creados: {result.get('created', 0):,}",
            f"✗ Errores: {result.get('errors', 0)}",
            "",
            "Los orderpoints ahora tienen MAX/MIN calculados",
            "usando las reglas de reabastecimiento.",
        ]

        return "\n".join(lines)

    def _format_verify_result(self, result):
        """Formatea el resultado de la verificación."""
        lines = [
            "═" * 50,
            "  VERIFICACIÓN DE MIGRACIÓN",
            "═" * 50,
            "",
            f"Estado: {'✓ OK' if result.get('status') == 'ok' else '⚠ ADVERTENCIA'}",
            "",
            "CONTADORES PRINCIPALES:",
        ]

        counts = result.get('counts', {})
        lines.append(f"  • Registros originales: {counts.get('original_records', 0):,}")
        lines.append(f"  • Daily stats: {counts.get('daily_stats', 0):,}")
        lines.append(f"  • Rolling stats (total): {counts.get('rolling_stats', 0):,}")

        # Desglose de rolling stats por tipo
        if counts.get('rolling_stats_sale', 0) > 0:
            lines.extend([
                "",
                "ROLLING STATS POR TIPO:",
                f"  • sale: {counts.get('rolling_stats_sale', 0):,}",
                f"  • transfer: {counts.get('rolling_stats_transfer', 0):,}",
                f"  • combined: {counts.get('rolling_stats_combined', 0):,}",
                f"  • global (bodega principal): {counts.get('rolling_stats_global', 0):,}",
            ])

        issues = result.get('issues', [])
        if issues:
            lines.extend([
                "",
                "PROBLEMAS DETECTADOS:",
            ])
            for issue in issues:
                if issue.startswith("  →"):
                    lines.append(f"    {issue}")
                else:
                    lines.append(f"  ⚠ {issue}")

        # Agregar conclusión sobre productos faltantes
        details = result.get('details', {})
        missing = details.get('missing_products', {})
        if missing and missing.get('total', 0) > 0:
            no_recent = missing.get('no_recent_sales', 0)
            total = missing.get('total', 0)
            if no_recent == total:
                lines.extend([
                    "",
                    "CONCLUSIÓN:",
                    "  ✓ Todos los productos faltantes NO tienen ventas",
                    "    en los últimos 90 días. Esto es NORMAL.",
                ])
            elif missing.get('inactive', 0) > 0:
                lines.extend([
                    "",
                    "CONCLUSIÓN:",
                    f"  ℹ {missing.get('inactive', 0)} productos faltantes están INACTIVOS.",
                    "    Considere si necesita migrar datos más antiguos.",
                ])

        return "\n".join(lines)

    def _format_cleanup_result(self, result):
        """Formatea el resultado de la limpieza."""
        lines = [
            "═" * 50,
            "  LIMPIEZA COMPLETADA",
            "═" * 50,
            "",
            "REGISTROS ELIMINADOS:",
        ]

        for table, count in result.items():
            if isinstance(count, int):
                lines.append(f"  • {table}: {count:,}")
            else:
                lines.append(f"  • {table}: {count}")

        lines.extend([
            "",
            "⚠ Las tablas han sido vaciadas.",
            "  Ejecuta una nueva migración para poblarlas.",
        ])

        return "\n".join(lines)
