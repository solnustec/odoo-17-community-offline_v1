# -*- coding: utf-8 -*-
import json
import logging
import requests
from datetime import datetime

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosMigrationWizard(models.TransientModel):
    """
    Wizard para ejecutar migración inicial desde PRINCIPAL.

    Permite descargar todos los datos maestros del servidor PRINCIPAL
    a la base de datos OFFLINE local, sin requerir configuración previa.
    """
    _name = 'pos.migration.wizard'
    _description = 'Wizard de Migración Inicial POS'

    # Configuración de conexión
    cloud_url = fields.Char(
        string='URL del Servidor PRINCIPAL',
        required=True,
        help='URL completa del servidor Odoo principal (ej: https://principal.miempresa.com)'
    )
    api_key = fields.Char(
        string='API Key',
        help='Clave de autenticación (opcional si el servidor no requiere)'
    )

    # Opciones de migración
    migrate_categories = fields.Boolean(
        string='Categorías de Productos',
        default=True
    )
    migrate_uom = fields.Boolean(
        string='Unidades de Medida',
        default=True
    )
    migrate_taxes = fields.Boolean(
        string='Impuestos',
        default=True
    )
    migrate_fiscal_positions = fields.Boolean(
        string='Posiciones Fiscales',
        default=True
    )
    migrate_payment_methods = fields.Boolean(
        string='Métodos de Pago',
        default=True
    )
    migrate_partners = fields.Boolean(
        string='Clientes/Contactos',
        default=True
    )
    migrate_pricelists = fields.Boolean(
        string='Listas de Precios',
        default=True
    )
    migrate_products = fields.Boolean(
        string='Productos',
        default=True
    )
    migrate_loyalty = fields.Boolean(
        string='Programas de Lealtad',
        default=True
    )

    # Estado
    state = fields.Selection([
        ('config', 'Configuración'),
        ('progress', 'En Progreso'),
        ('done', 'Completado'),
        ('error', 'Error'),
    ], default='config', string='Estado')

    progress_message = fields.Text(
        string='Progreso',
        readonly=True
    )
    result_message = fields.Text(
        string='Resultado',
        readonly=True
    )

    batch_size = fields.Integer(
        string='Tamaño de Lote',
        default=500,
        help='Cantidad de registros a procesar por lote'
    )

    def action_test_connection(self):
        """Prueba la conexión con el servidor PRINCIPAL."""
        self.ensure_one()

        if not self.cloud_url:
            raise UserError('Ingrese la URL del servidor PRINCIPAL')

        url = self.cloud_url.rstrip('/')

        try:
            response = requests.get(
                f'{url}/pos_offline_sync/ping',
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Conexión Exitosa',
                            'message': f'Servidor: {url}\nVersión: {data.get("version", "N/A")}',
                            'type': 'success',
                            'sticky': False,
                        }
                    }

            raise UserError(f'El servidor respondió con código {response.status_code}')

        except requests.exceptions.ConnectionError:
            raise UserError(f'No se puede conectar a {url}. Verifique la URL y la conexión de red.')
        except requests.exceptions.Timeout:
            raise UserError('Tiempo de espera agotado. El servidor no responde.')
        except Exception as e:
            raise UserError(f'Error de conexión: {str(e)}')

    def action_run_migration(self):
        """Ejecuta la migración completa."""
        self.ensure_one()

        if not self.cloud_url:
            raise UserError('Ingrese la URL del servidor PRINCIPAL')

        self.write({
            'state': 'progress',
            'progress_message': 'Iniciando migración...\n',
        })

        try:
            result = self._execute_migration()

            # Formatear resultado
            message = self._format_result(result)

            self.write({
                'state': 'done' if result.get('success') else 'error',
                'result_message': message,
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

        except Exception as e:
            _logger.error(f'Error en migración: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())

            self.write({
                'state': 'error',
                'result_message': f'Error: {str(e)}',
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

    def _execute_migration(self):
        """Ejecuta la migración usando la lógica del SyncManager."""
        result = {
            'success': True,
            'models_processed': {},
            'total_records': 0,
            'errors': [],
            'start_time': datetime.now().isoformat(),
        }

        url = self.cloud_url.rstrip('/')

        # 1. Obtener manifiesto
        self._update_progress('Obteniendo información del servidor...')
        manifest = self._get_manifest(url)

        if not manifest.get('success'):
            result['success'] = False
            result['errors'].append(manifest.get('error', 'Error obteniendo manifiesto'))
            return result

        sync_order = manifest.get('sync_order', [])

        # Mapeo de nombres a modelos
        model_mapping = {
            'product_categories': ('product.category', self.migrate_categories),
            'uom': ('uom.uom', self.migrate_uom),
            'taxes': ('account.tax', self.migrate_taxes),
            'fiscal_positions': ('account.fiscal.position', self.migrate_fiscal_positions),
            'payment_methods': ('pos.payment.method', self.migrate_payment_methods),
            'partners': ('res.partner', self.migrate_partners),
            'pricelists': ('product.pricelist', self.migrate_pricelists),
            'product_templates': ('product.template', self.migrate_products),
            'products': ('product.product', self.migrate_products),
            'pricelist_items': ('product.pricelist.item', self.migrate_pricelists),
            'loyalty_programs': ('loyalty.program', self.migrate_loyalty),
            'loyalty_rules': ('loyalty.rule', self.migrate_loyalty),
            'loyalty_rewards': ('loyalty.reward', self.migrate_loyalty),
        }

        # 2. Procesar cada modelo en orden
        for entity_name in sync_order:
            mapping = model_mapping.get(entity_name)
            if not mapping:
                continue

            model_name, enabled = mapping
            if not enabled:
                continue

            total_for_model = manifest.get('manifest', {}).get(entity_name, 0)
            if total_for_model == 0:
                continue

            self._update_progress(f'Descargando {entity_name}: {total_for_model} registros...')

            model_result = self._migrate_model(url, model_name, total_for_model)

            result['models_processed'][entity_name] = model_result
            result['total_records'] += model_result.get('imported', 0) + model_result.get('updated', 0)

            if model_result.get('errors'):
                result['errors'].extend(model_result['errors'][:5])  # Limitar errores

        result['end_time'] = datetime.now().isoformat()
        return result

    def _get_manifest(self, url):
        """Obtiene el manifiesto desde el servidor."""
        try:
            payload = {}
            if self.api_key:
                payload['api_key'] = self.api_key

            response = requests.post(
                f'{url}/pos_offline_sync/migration/manifest',
                json=payload,
                timeout=30
            )

            data = response.json()
            # Log del manifiesto para diagnóstico
            _logger.info(f'[MIGRACIÓN] Manifiesto recibido: {data.get("manifest", {})}')
            return data

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _migrate_model(self, url, model_name, total):
        """Migra un modelo completo por lotes."""
        result = {
            'model': model_name,
            'total': total,
            'imported': 0,
            'updated': 0,
            'errors': [],
        }

        _logger.info(f'[MIGRACIÓN] Iniciando {model_name}: total esperado = {total}')

        offset = 0
        batch_size = self.batch_size or 500

        while offset < total:
            try:
                payload = {
                    'model': model_name,
                    'limit': batch_size,
                    'offset': offset,
                }
                if self.api_key:
                    payload['api_key'] = self.api_key

                response = requests.post(
                    f'{url}/pos_offline_sync/migration/pull_batch',
                    json=payload,
                    timeout=60
                )

                data = response.json()
                _logger.info(f'[MIGRACIÓN] Lote {model_name} offset={offset}: '
                           f'recibidos={data.get("count", 0)}, '
                           f'total_server={data.get("total", 0)}, '
                           f'has_more={data.get("has_more", False)}')

                if not data.get('success'):
                    result['errors'].append(f'Error en lote {offset}: {data.get("error")}')
                    break

                records = data.get('records', [])
                if not records:
                    _logger.warning(f'[MIGRACIÓN] Sin registros en lote {model_name} offset={offset}')
                    break

                # Importar lote
                batch_result = self._import_batch(model_name, records)
                result['imported'] += batch_result.get('created', 0)
                result['updated'] += batch_result.get('updated', 0)

                _logger.info(f'[MIGRACIÓN] Lote procesado: '
                           f'creados={batch_result.get("created", 0)}, '
                           f'actualizados={batch_result.get("updated", 0)}, '
                           f'errores={len(batch_result.get("errors", []))}')

                if batch_result.get('errors'):
                    result['errors'].extend(batch_result['errors'][:3])

                offset += len(records)
                self._update_progress(f'  {model_name}: {offset}/{total}')

                if not data.get('has_more'):
                    break

            except Exception as e:
                _logger.error(f'[MIGRACIÓN] Excepción en lote {offset}: {str(e)}')
                result['errors'].append(f'Error en lote {offset}: {str(e)}')
                break

        _logger.info(f'[MIGRACIÓN] Fin {model_name}: creados={result["imported"]}, '
                   f'actualizados={result["updated"]}, errores={len(result["errors"])}')

        return result

    def _import_batch(self, model_name, records):
        """Importa un lote de registros."""
        result = {'created': 0, 'updated': 0, 'errors': []}

        if model_name not in self.env:
            result['errors'].append(f'Modelo {model_name} no existe')
            return result

        SyncManager = self.env['pos.sync.manager'].sudo()
        Model = self.env[model_name].sudo()

        for record_data in records:
            try:
                with self.env.cr.savepoint():
                    existing = SyncManager._find_existing_for_migration(
                        Model, model_name, record_data
                    )

                    vals = SyncManager._prepare_migration_vals(model_name, record_data)

                    if existing:
                        existing.write(vals)
                        result['updated'] += 1
                    else:
                        Model.create(vals)
                        result['created'] += 1

            except Exception as e:
                error_msg = f'{model_name} id={record_data.get("id")}: {str(e)}'
                result['errors'].append(error_msg)

        return result

    def _update_progress(self, message):
        """Actualiza el mensaje de progreso."""
        current = self.progress_message or ''
        self.write({
            'progress_message': current + message + '\n'
        })
        # Commit para que se vea en la UI (aunque en wizard no siempre funciona)
        self.env.cr.commit()

    def _format_result(self, result):
        """Formatea el resultado para mostrar al usuario."""
        lines = []

        if result.get('success'):
            lines.append('*** MIGRACIÓN COMPLETADA ***\n')
        else:
            lines.append('*** MIGRACIÓN CON ERRORES ***\n')

        lines.append(f"Total de registros: {result.get('total_records', 0)}\n")
        lines.append("\nDetalle por modelo:")

        for entity, data in result.get('models_processed', {}).items():
            created = data.get('imported', 0)
            updated = data.get('updated', 0)
            lines.append(f"  - {entity}: {created} creados, {updated} actualizados")

        if result.get('errors'):
            lines.append("\nErrores encontrados:")
            for error in result['errors'][:10]:
                lines.append(f"  ! {error}")

            if len(result['errors']) > 10:
                lines.append(f"  ... y {len(result['errors']) - 10} errores más")

        return '\n'.join(lines)

    def action_close(self):
        """Cierra el wizard."""
        return {'type': 'ir.actions.act_window_close'}
