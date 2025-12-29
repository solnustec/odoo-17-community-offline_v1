from odoo import http
from odoo.http import request
import json
from datetime import datetime

import logging

_logger = logging.getLogger(__name__)


class StockPickingController(http.Controller):

    @http.route('/api/stock_picking/create', type='http', auth='public', methods=['POST'], csrf=False)
    def create_stock_picking(self, **kwargs):
        # try:
        # Obtener los datos del cuerpo de la solicitud
        data = json.loads(request.httprequest.data)

        # Validar campos obligatorios
        required_fields = ['location_id', 'location_dest_id', 'scheduled_date']
        for field in required_fields:
            if field not in data:
                return self._json_response({'status': 'error', 'message': f'Missing required field: {field}'}, 400)

        # Verificar si existe una transferencia con el mismo key_transfer
        existing_picking = None
        if 'key_transfer' in data and data['key_transfer']:
            existing_picking = request.env['stock.picking'].sudo().search([
                ('key_transfer', '=', str(data['key_transfer'])),
                ('picking_type_id.code', '=', 'internal')
            ], limit=1)

        # Si existe, actualizar según corresponda
        if existing_picking:
            response = self._handle_existing_picking(existing_picking, data)
            if response:
                return response

        # Buscar almacén por external_id y obtener información completa
        def get_warehouse_info(external_id):
            warehouse = request.env['stock.warehouse'].sudo().search([
                ('external_id', '=', str(external_id))
            ], limit=1)
            if not warehouse:
                return None, None, None

            # Buscar la ubicación interna con replenish_location = True
            stock_location = request.env['stock.location'].sudo().search([
                ('usage', '=', 'internal'),
                ('warehouse_id', '=', warehouse.id),
                ('replenish_location', '=', True),
                ('company_id', '=', warehouse.company_id.id),
            ], limit=1)

            # Si no se encuentra una ubicación con replenish_location, usar lot_stock_id
            if not stock_location:
                stock_location = warehouse.lot_stock_id

            return warehouse.id, stock_location.id, warehouse.company_id.id

        # Convertir external_id a warehouse_id, location_id y company_id
        warehouse_id_origin, location_id, company_id_origin = get_warehouse_info(data['location_id'])
        warehouse_id_dest, location_dest_id, company_id_dest = get_warehouse_info(data['location_dest_id'])

        if not location_id or not location_dest_id:
            return self._json_response(
                {'status': 'error', 'message': 'Invalid external_id for warehouse or location not found'}, 400)

        # Verificar que ambas ubicaciones pertenezcan a la misma empresa
        if company_id_origin != company_id_dest:
            return self._json_response({
                'status': 'error',
                'message': 'Origin and destination warehouses must belong to the same company'
            }, 400)

        # Buscar el picking_type de tipo "internal" para el almacén de origen
        stock_picking_type = request.env['stock.picking.type'].sudo().search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse_id_origin)
        ], limit=1)

        if not stock_picking_type:
            return self._json_response({
                'status': 'error',
                'message': f'No internal transfer type found for warehouse ID {warehouse_id_origin}'
            }, 400)

        employee = request.env['hr.employee'].sudo().search([
            ('id_employeed_old', '=', str(data.get('user_id', '')))
        ], limit=1)

        # Crear la transferencia interna (stock.picking)
        stock_picking_vals = {
            'picking_type_id': stock_picking_type.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
            'scheduled_date': datetime.strptime(data['scheduled_date'], '%Y-%m-%d %H:%M:%S'),
            'company_id': company_id_origin,
            'state': 'draft',
            'key_transfer': data.get('key_transfer', ''),
            'origin': data.get('origin', ''),
            'user_id': employee.user_id.id if employee and employee.user_id else 2
        }

        # Agregar type_transfer si existe en los datos
        if 'type_transfer' in data:
            stock_picking_vals['type_transfer'] = data['type_transfer']

        # Agregar note si existe en los datos
        if 'note' in data:
            stock_picking_vals['note'] = data['note']

        stock_picking = request.env['stock.picking'].sudo().with_context(
            force_company=company_id_origin
        ).create(stock_picking_vals)

        # Procesar las líneas de movimiento (stock.move)
        if 'move_lines' in data and isinstance(data['move_lines'], list):
            for line in data['move_lines']:
                product_id = None

                if 'product_template_id' in line:
                    product_template = request.env['product.template'].sudo().search([
                        ('id_database_old', '=', str(line['product_template_id']))
                    ], limit=1)

                    if not product_template:
                        return self._json_response({
                            'status': 'error',
                            'message': f'Invalid id_database_old: {line["product_template_id"]}'
                        }, 400)

                    product_variant = request.env['product.product'].sudo().search(
                        [('product_tmpl_id', '=', product_template.id)],
                        limit=1
                    )
                    if not product_variant:
                        return self._json_response({
                            'status': 'error',
                            'message': f'No product variant found for product_template_id: {product_template.id}'
                        }, 400)

                    product_id = product_variant.id

                elif 'product_id' in line:
                    product = request.env['product.product'].sudo().browse(int(line['product_id']))
                    if not product.exists():
                        return self._json_response({
                            'status': 'error',
                            'message': f'Invalid product_id: {line["product_id"]}'
                        }, 400)
                    product_id = product.id

                # Si no se encontró ningún `product_id`, devolver error
                if not product_id:
                    return self._json_response({
                        'status': 'error',
                        'message': 'Missing product_id or product_template_id in move_lines'
                    }, 400)

                product = request.env['product.product'].sudo().browse(product_id)

                move_vals = {
                    'picking_id': stock_picking.id,
                    'product_id': product_id,
                    'product_uom_qty': line.get('product_uom_qty', 1.0),
                    'quantity': line.get('product_uom_qty', 1.0),
                    'product_uom': product.uom_id.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'name': product.name or "Product",
                    'company_id': company_id_origin,
                    'state': 'draft',
                }
                request.env['stock.move'].sudo().with_context(
                    force_company=company_id_origin
                ).create(move_vals)

        # Aplicar el estado según los parámetros recibidos
        cancel = data.get('cancel', False)
        state = data.get('state', 'done')  # Por defecto 'done' para mantener compatibilidad

        # Validar que cancel sea booleano
        if isinstance(cancel, str):
            cancel = cancel.lower() == 'true'

        final_state = 'draft'
        action_applied = 'created'

        # PRIORIDAD 1: Si cancel es True, cancelar
        if cancel:
            stock_picking.action_cancel()
            final_state = stock_picking.state
            action_applied = 'created_and_cancelled'
        # PRIORIDAD 2: Aplicar state
        elif state == 'done':
            stock_picking.button_validate()
            final_state = stock_picking.state
            action_applied = 'created_and_validated'
        # Si state es 'draft', dejar en draft
        elif state == 'draft':
            final_state = 'draft'
            action_applied = 'created_as_draft'

        return self._json_response({
            'status': 'success',
            'message': f'Stock picking {action_applied} successfully',
            'picking_id': stock_picking.id,
            'picking_name': stock_picking.name,
            'picking_type_id': stock_picking_type.id,
            'picking_type_name': stock_picking_type.name,
            'warehouse_id_origin': warehouse_id_origin,
            'warehouse_id_dest': warehouse_id_dest,
            'state': final_state,
            'company_id': stock_picking.company_id.id,
            'company_name': stock_picking.company_id.name,
            'action': action_applied
        }, 201)

        # except Exception as e:
        #     _logger.error(f"Error processing stock picking: {str(e)}", exc_info=True)
        #     return self._json_response({'status': 'error', 'message': str(e)}, 500)

    def _handle_existing_picking(self, existing_picking, data):
        """Maneja la actualización o cancelación de un picking existente"""
        # Normalizar cancel a booleano
        cancel = data.get('cancel', False)
        if isinstance(cancel, str):
            cancel = cancel.lower() == 'true'

        state = data.get('state', '')

        # PRIORIDAD 1: Manejo de cancelación
        if cancel:
            if existing_picking.state == 'done':
                return_picking_id = self._create_return_picking(existing_picking)
                if return_picking_id:
                    return self._json_response({
                        'status': 'success',
                        'message': 'Return picking created successfully',
                        'original_picking_id': existing_picking.id,
                        'original_picking_name': existing_picking.name,
                        'return_picking_id': return_picking_id['picking_id'],
                        'return_picking_name': return_picking_id['picking_name'],
                        'action': 'return_created'
                    }, 200)
                else:
                    return self._json_response({'status': 'error', 'message': 'Failed to create return picking'}, 400)

            elif existing_picking.state in ('draft', 'waiting', 'confirmed', 'assigned'):
                existing_picking.action_cancel()
                return self._json_response({
                    'status': 'success',
                    'message': 'Stock picking cancelled successfully',
                    'picking_id': existing_picking.id,
                    'picking_name': existing_picking.name,
                    'state': existing_picking.state,
                    'action': 'cancelled'
                }, 200)

            else:
                return self._json_response({
                    'status': 'error',
                    'message': f'Cannot cancel picking in state: {existing_picking.state}'
                }, 400)

        # PRIORIDAD 2: Actualización de campos (solo en estados editables)
        if existing_picking.state not in ('draft', 'waiting', 'confirmed', 'assigned'):
            if state == 'done' and existing_picking.state == 'done':
                return self._json_response({
                    'status': 'info',
                    'message': 'Picking is already validated',
                    'picking_id': existing_picking.id,
                    'picking_name': existing_picking.name,
                    'state': existing_picking.state
                }, 200)

            return self._json_response({
                'status': 'error',
                'message': f'Cannot modify picking in state: {existing_picking.state}'
            }, 400)

        # Preparar valores para actualizar
        update_vals = {}
        updated_fields = {}

        # Actualizar ubicaciones si se proporcionan external_ids
        if 'location_id' in data and data['location_id']:
            warehouse = request.env['stock.warehouse'].sudo().search([
                ('external_id', '=', str(data['location_id']))
            ], limit=1)
            if warehouse:
                stock_location = request.env['stock.location'].sudo().search([
                    ('usage', '=', 'internal'),
                    ('warehouse_id', '=', warehouse.id),
                    ('replenish_location', '=', True),
                    ('company_id', '=', warehouse.company_id.id),
                ], limit=1)
                location_id = stock_location.id if stock_location else warehouse.lot_stock_id.id

                if existing_picking.location_id.id != location_id:
                    update_vals['location_id'] = location_id
                    updated_fields['location_id'] = location_id

        if 'location_dest_id' in data and data['location_dest_id']:
            warehouse = request.env['stock.warehouse'].sudo().search([
                ('external_id', '=', str(data['location_dest_id']))
            ], limit=1)
            if warehouse:
                stock_location = request.env['stock.location'].sudo().search([
                    ('usage', '=', 'internal'),
                    ('warehouse_id', '=', warehouse.id),
                    ('replenish_location', '=', True),
                    ('company_id', '=', warehouse.company_id.id),
                ], limit=1)
                location_dest_id = stock_location.id if stock_location else warehouse.lot_stock_id.id

                if existing_picking.location_dest_id.id != location_dest_id:
                    update_vals['location_dest_id'] = location_dest_id
                    updated_fields['location_dest_id'] = location_dest_id

        # Actualizar scheduled_date
        if 'scheduled_date' in data and data['scheduled_date']:
            scheduled_date = datetime.strptime(data['scheduled_date'], '%Y-%m-%d %H:%M:%S')
            update_vals['scheduled_date'] = scheduled_date
            updated_fields['scheduled_date'] = data['scheduled_date']

        # Actualizar user_id
        if 'user_id' in data and data['user_id']:
            employee = request.env['hr.employee'].sudo().search([
                ('id_employeed_old', '=', str(data['user_id']))
            ], limit=1)
            if employee and employee.user_id:
                user_id = employee.user_id.id
                if existing_picking.user_id.id != user_id:
                    update_vals['user_id'] = user_id
                    updated_fields['user_id'] = user_id

        # Actualizar note
        if 'note' in data:
            update_vals['note'] = data['note']
            updated_fields['note'] = data['note']

        # Actualizar type_transfer
        print("revisar el transfer", data)

        if 'type_transfer' in data:
            print("ingresa al type")
            update_vals['type_transfer'] = data['type_transfer']
            updated_fields['type_transfer'] = data['type_transfer']

        # Actualizar move_lines si se proporcionan
        if 'move_lines' in data and data['move_lines']:
            # Eliminar líneas existentes
            existing_picking.move_ids.unlink()

            move_lines_data = []
            for line in data['move_lines']:
                product_id = None

                if 'product_template_id' in line:
                    product_template = request.env['product.template'].sudo().search([
                        ('id_database_old', '=', str(line['product_template_id']))
                    ], limit=1)

                    if product_template:
                        product_variant = request.env['product.product'].sudo().search(
                            [('product_tmpl_id', '=', product_template.id)],
                            limit=1
                        )
                        if product_variant:
                            product_id = product_variant.id

                elif 'product_id' in line:
                    product = request.env['product.product'].sudo().browse(int(line['product_id']))
                    if product.exists():
                        product_id = product.id

                if product_id:
                    product = request.env['product.product'].sudo().browse(product_id)
                    move_lines_data.append((0, 0, {
                        'name': product.name,
                        'product_id': product_id,
                        'product_uom_qty': float(line.get('product_uom_qty', 1.0)),
                        'product_uom': product.uom_id.id,
                        'location_id': update_vals.get('location_id', existing_picking.location_id.id),
                        'location_dest_id': update_vals.get('location_dest_id', existing_picking.location_dest_id.id),
                        'picking_id': existing_picking.id,
                        'company_id': existing_picking.company_id.id,
                        'state': 'draft',
                    }))

            if move_lines_data:
                update_vals['move_ids'] = move_lines_data
                updated_fields['move_lines'] = len(data['move_lines'])

        # Aplicar actualizaciones si hay cambios
        if update_vals:
            existing_picking.write(update_vals)

        # PRIORIDAD 3: Validación del picking
        if state == 'done':
            existing_picking.button_validate()
            action = 'updated_and_validated' if updated_fields else 'validated'
            message = 'Stock picking updated and validated successfully' if updated_fields else 'Stock picking validated successfully'
        else:
            action = 'updated' if updated_fields else 'no_changes'
            message = 'Stock picking updated successfully' if updated_fields else 'No changes detected in the picking'

        return self._json_response({
            'status': 'success' if updated_fields or state == 'done' else 'info',
            'message': message,
            'picking_id': existing_picking.id,
            'picking_name': existing_picking.name,
            'state': existing_picking.state,
            'updated_fields': updated_fields,
            'action': action
        }, 200)

    def _json_response(self, data, status=200):
        """Método auxiliar para crear respuestas JSON"""
        return http.Response(
            json.dumps(data),
            content_type="application/json",
            status=status
        )

    def _create_return_picking(self, picking):
        """
        Crea un picking de retorno para una transferencia completada.
        Basado en la lógica del wizard stock.return.picking
        """
        try:
            # Crear el wizard de retorno
            return_wizard = request.env['stock.return.picking'].sudo().with_context(
                active_id=picking.id,
                active_model='stock.picking'
            ).create({
                'picking_id': picking.id
            })

            # El wizard automáticamente crea las líneas de retorno en _onchange
            # Si no se crean automáticamente, las creamos manualmente
            if not return_wizard.product_return_moves:
                return_move_lines = []
                for move in picking.move_ids.filtered(lambda m: m.state == 'done' and m.product_qty > 0):
                    return_move_lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'quantity': move.product_qty,
                        'move_id': move.id,
                        'uom_id': move.product_uom.id,
                    }))

                if return_move_lines:
                    return_wizard.write({'product_return_moves': return_move_lines})

            # Crear el picking de retorno
            new_picking_id, pick_type_id = return_wizard._create_returns()

            # Obtener el nuevo picking creado
            new_picking = request.env['stock.picking'].sudo().browse(new_picking_id)

            # Validar automáticamente el retorno si está configurado
            if new_picking and new_picking.state in ('draft', 'waiting', 'confirmed', 'assigned'):
                new_picking.button_validate()

            return {
                'picking_id': new_picking_id,
                'picking_name': new_picking.name,
                'picking_type_id': pick_type_id,
                'state': new_picking.state
            }

        except Exception as e:
            _logger.error(f"Error creating return picking: {str(e)}", exc_info=True)
            return None