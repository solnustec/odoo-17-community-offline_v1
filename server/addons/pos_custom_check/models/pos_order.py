# -*- coding: utf-8 -*-
import json
from typing import re

from odoo import api, fields, models, tools, _
import logging
from datetime import timedelta
import pytz
import random
from datetime import datetime, time
from odoo.exceptions import ValidationError, AccessError
from odoo.exceptions import UserError
import math
from datetime import date
from odoo.http import request
from collections import defaultdict
from odoo.osv.expression import AND

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    check_info_json = fields.Text('Check Info JSON', default='{}')
    card_info_json = fields.Text('Card Info JSON', default='{}')
    key_order = fields.Char(string='Clave de la Orden',
                            help="Campo personalizado para almacenar una clave única.")
    date_invoices = fields.Char(string='Fecha de la factura', readonly=False, required=False)

    # Pagos Digitales
    payment_transaction_id = fields.Char(string='Transaction ID')
    payment_transfer_number = fields.Char(string='Transfer Number')
    payment_bank_name = fields.Char(string='Banco (Pago Digital)')
    orderer_identification = fields.Char(string='Orderer Identification')
    digital_media = fields.Char(string='Medio digital', index=True)
    credit_institution_id = fields.Many2one('institution.client', string='Institución de crédito usada',
        readonly=True,
    )

    # Autorización manual de pago digital
    self_authorized = fields.Boolean(
        string='Autorizado manualmente',
        default=False,
        help='Indica si el pago digital fue autorizado manualmente por el empleado'
    )
    self_authorized_by = fields.Many2one(
        'res.users',
        string='Autorizado por',
        help='Usuario que autorizó el pago manualmente'
    )
    self_authorization_date = fields.Datetime(
        string='Fecha de autorización'
    )

    @api.model
    def get_payment_methods_for_order(self, order_id):
        order = self.browse(order_id)
        if order.amount_total < 0:
            payment_methods = order.payment_ids.mapped(
                'payment_method_id.name')
            return payment_methods
        else:
            return []

    @api.model
    def get_order_payment_methods(self, order_id):
        """
        Obtiene los métodos de pago de una orden con la institución de crédito correcta.
        Corregido para buscar correctamente la institución en múltiples fuentes.
        """
        order = self.browse(order_id)

        payment_methods = []
        for payment in order.payment_ids:
            credit_institution_id = False

            if payment.selecteInstitutionCredit:
                try:
                    credit_institution_id = int(payment.selecteInstitutionCredit)
                except (ValueError, TypeError):
                    pass

            if not credit_institution_id and order.credit_institution_id:
                credit_institution_id = order.credit_institution_id.institution_id.id

                if payment.payment_method_id.code_payment_method == 'CREDITO':
                    payment.sudo().write({
                        'selecteInstitutionCredit': str(credit_institution_id)
                    })

            # 3. Último fallback: Buscar por partner si es método CREDITO
            if not credit_institution_id and payment.payment_method_id.code_payment_method == 'CREDITO':
                institution_client = self.env['institution.client'].sudo().search([
                    ('partner_id', '=', order.partner_id.id)
                ], limit=1)
                if institution_client:
                    credit_institution_id = institution_client.institution_id.id

            payment_methods.append({
                'payment_method_id': payment.payment_method_id.id,
                'payment_method_name': payment.payment_method_id.name,
                'amount': payment.amount,
                'order_date': self.convertir_a_hora_ecuador(order.create_date),
                'credit_institution_id': credit_institution_id,
            })
        return payment_methods

    # funcion que se ejcuta luego de generar la order de venta del pos
    def _generate_pos_order_invoice(self):
        moves = self.env['account.move']

        for order in self:

            if order.account_move:
                moves += order.account_move
                continue

            if not order.partner_id:
                raise UserError(_('Please provide a partner for the sale.'))

            move_vals = order._prepare_invoice_vals()
            new_move = order._create_invoice(move_vals)

            order.write({'account_move': new_move.id, 'state': 'invoiced'})
            new_move.sudo().with_company(order.company_id).with_context(
                skip_invoice_sync=True)._post()

            moves += new_move
            payment_moves = order._apply_invoice_payments(order.session_id.state == 'closed')


            # Send and Print
            # if self.env.context.get('generate_pdf', True):
            #     template = self.env.ref(new_move._get_mail_template())
            #     new_move.with_context(skip_invoice_sync=True)._generate_pdf_and_send_invoice(template)

            if order.session_id.state == 'closed':  # If the session isn't closed this isn't needed.
                # If a client requires the invoice later, we need to revers the amount from the closing entry, by making a new entry for that.
                order._create_misc_reversal_move(payment_moves)

        if not moves:
            return {}

        return {
            'name': _('Customer Invoice'),
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_move_form').id,
            'res_model': 'account.move',
            'context': "{'move_type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'target': 'current',
            'res_id': moves and moves.ids[0] or False,
        }

    @api.model
    def create_from_ui(self, orders, draft=False):
        """Crear orden desde la UI del POS y procesar información de pagos."""
        order_ids = super(PosOrder, self).create_from_ui(orders, draft)
        global note_invoice
        global is_chatboot
        global order_id
        global id_credit_intitution
        id_credit_intitution = False
        if not order_ids or len(order_ids) == 0:
            return order_ids

        institution_id_to_save = False

        for st_line in orders[0].get('data').get('statement_ids', []):
            st_values = st_line[2]
            credit_value = st_values.get('selecteInstitutionCredit')

            if credit_value not in (False, None, "", 0):
                id_credit_intitution = credit_value
                institution_id_to_save = credit_value
                break

        order_id = order_ids[0].get('id')

        if institution_id_to_save:
            pos_order = self.browse(order_id)

            institution = self.env['institution'].sudo().search([
                ('id', '=', int(institution_id_to_save))
            ], limit=1)

            if institution:
                institution_client = self.env['institution.client'].sudo().search([
                    ('institution_id', '=', institution.id),
                    ('partner_id', '=', pos_order.partner_id.id)
                ], limit=1)

                if institution_client:
                    pos_order.write({
                        'credit_institution_id': institution_client.id
                    })

                    # ======== NUEVO: Guardar también en los payments ========
                    for payment in pos_order.payment_ids:
                        if payment.payment_method_id.code_payment_method == 'CREDITO':
                            payment.sudo().write({
                                'selecteInstitutionCredit': str(institution.id)
                            })

                else:
                    pass
            else:
                pass

        if orders[0].get('data', {}).get('invoice_note') is not None:
            note_invoice = orders[0].get('data')['invoice_note']
        else:
            note_invoice = ""

        for index, order_data in enumerate(orders):
            data_order_pre = order_data.get('data')
            if data_order_pre and 'lines' in data_order_pre:
                lines = data_order_pre['lines']
                updated_lines = self._generate_reward_lines(lines)
                orders[index]['data']['lines'] = updated_lines
                if orders[index]['data']['lines'][0][2]:
                    if orders[index]['data']['lines'][0][2].get('sale_order_origin_id'):
                        if orders[index]['data']['lines'][0][2].get('sale_order_origin_id').get(
                                'x_channel'):
                            if orders[index]['data']['lines'][0][2].get('sale_order_origin_id').get(
                                    'x_channel') and \
                                    orders[index]['data']['lines'][0][2].get(
                                        'sale_order_origin_id').get(
                                        'x_channel') == "canal digital":
                                is_chatboot = True
                    else:
                        is_chatboot = False

        global efectivo_total
        global total_tarjeta
        global total_cheque
        global total_efectivo
        global type_payment
        global method
        global method_payment_list
        global efectivo_tarjeta
        global efectivo_efectivo
        global encargado
        global id_institution
        global discount_credit_intitution

        # ID DEL PUNTO DE VENTA
        pos_session_id = self._context.get('pos_session_id')
        if not pos_session_id:
            # Obtener la sesión activa manualmente si no está en el contexto
            pos_session = self.env['pos.session'].search(
                [('state', '=', 'opened')], limit=1)
            if not pos_session:
                raise ValueError(
                    "No se encontró 'pos_session_id' en el contexto ni una sesión activa.")
        else:
            pos_session = self.env['pos.session'].browse(pos_session_id)

        pos_config = pos_session.config_id
        institution_id = 0

        for order_data in order_ids:
            pos_order = self.browse(order_data['id'])
            pos_order.action_pos_order_paid()

            if pos_order.amount_total < 0 or pos_order.name.endswith('REEMBOLSO'):
                sale_return = abs(pos_order[0]['amount_total'])
                move = pos_order.account_move
                pto_emision = ""
                if move:
                    pto_emision = move.name

                original_order = pos_order.refunded_order_ids
                original_institution_client = None
                institution = None
                should_return_to_institution = False

                if original_order and original_order.credit_institution_id:
                    original_institution_client = original_order.credit_institution_id
                    institution = original_institution_client.institution_id

                if not institution and original_order:
                    for payment in original_order.payment_ids:
                        if payment.selecteInstitutionCredit:
                            try:
                                inst_id = int(payment.selecteInstitutionCredit)
                                institution = self.env['institution'].sudo().browse(inst_id)
                                if institution.exists():
                                    original_institution_client = self.env['institution.client'].sudo().search([
                                        ('institution_id', '=', institution.id),
                                        ('partner_id', '=', pos_order.partner_id.id)
                                    ], limit=1)
                                    break
                            except (ValueError, TypeError):
                                pass

                # Método 3: Buscar desde el payment actual del reembolso
                if not institution:
                    for payment in pos_order.payment_ids:
                        if payment.selecteInstitutionCredit:
                            try:
                                inst_id = int(payment.selecteInstitutionCredit)
                                institution = self.env['institution'].sudo().browse(inst_id)
                                if institution.exists():
                                    original_institution_client = self.env['institution.client'].sudo().search([
                                        ('institution_id', '=', institution.id),
                                        ('partner_id', '=', pos_order.partner_id.id)
                                    ], limit=1)
                                    break
                            except (ValueError, TypeError):
                                pass

                import calendar

                today = date.today()

                # Obtener la fecha de la factura original
                if original_order and original_order.date_order:
                    invoice_date = original_order.date_order.date() if hasattr(
                        original_order.date_order, 'date') else original_order.date_order
                else:
                    invoice_date = today  # Fallback si no hay orden original


                if institution:
                    # Obtener el día de corte configurado (0 si es None)
                    raw_court_day = institution.court_day or 0

                    if raw_court_day == 0:
                        should_return_to_institution = True

                    else:
                        # Calcular el PRÓXIMO día de corte después de la fecha de factura
                        invoice_day = invoice_date.day
                        invoice_month = invoice_date.month
                        invoice_year = invoice_date.year

                        # Determinar en qué mes cae el próximo día de corte
                        if invoice_day < raw_court_day:
                            next_cut_month = invoice_month
                            next_cut_year = invoice_year
                        else:
                            next_cut_month = invoice_month + 1
                            next_cut_year = invoice_year
                            if next_cut_month > 12:
                                next_cut_month = 1
                                next_cut_year += 1

                        # Obtener el último día del mes donde cae el próximo corte
                        last_day_of_cut_month = calendar.monthrange(next_cut_year, next_cut_month)[1]

                        effective_cut_day = min(raw_court_day, last_day_of_cut_month)

                        # Construir la fecha del próximo día de corte
                        next_cut_date = date(next_cut_year, next_cut_month, effective_cut_day)

                        if today < next_cut_date:
                            should_return_to_institution = True

                        else:
                            should_return_to_institution = False

                else:
                    should_return_to_institution = False

                if should_return_to_institution and original_institution_client:
                    new_available = original_institution_client.available_amount + sale_return

                    # Validar que no exceda el cupo asignado
                    if new_available > original_institution_client.sale:
                        new_available = original_institution_client.sale

                    original_institution_client.sudo().write({'available_amount': new_available})

                else:
                    # DESPUÉS del día de corte o sin institución: Registrar como anticipo
                    if move:
                        move.sudo().write({'note_credit': sale_return})

                invoice_id = pos_order.account_move.reversed_entry_id.pos_order_ids
                invoice_normal = pos_order.refunded_order_ids.key_order

                if invoice_id:
                    order = self.env['pos.order'].search([
                        ('id', '=', invoice_id.id),
                    ], limit=1)
                else:
                    order = self.env['pos.order'].search([
                        ('id', '=', pos_order[0].id),
                    ], limit=1)

                if order:
                    if should_return_to_institution:
                        refund_type = "Abono cxc"
                    else:
                        refund_type = self.get_type_note_credit(pos_order)

                    refund_data = {
                        "credit_note": invoice_normal,
                        "type": refund_type,
                        "status": "create",
                        "pto_emision": pto_emision.replace("NotCr ", ""),
                        "note": note_invoice,
                        "institution_id": institution.id if institution else None,
                        "returned_to_institution": should_return_to_institution,
                    }

                    pos_config = pos_session.config_id

                    self.env['json.note.credit'].create({
                        'json_data': json.dumps([refund_data], indent=4),
                        'pos_order_id': pos_session.config_id.id,
                        'id_point_of_sale': pos_config.point_of_sale_id,
                        'date_invoices': invoice_date.isoformat(),
                        'db_key': invoice_normal,
                    })
                else:
                    pass

                continue

            global employee
            global institutionMixto
            global institutionMixtoCheque
            global id_institution_cheque
            global bodega_id
            global serie_id
            global warehouse
            for index, order_data in enumerate(order_ids):
                order_front_data = orders[index].get("data", {})
                pos_session_id = order_front_data.get('pos_session_id')
                pos_session = self.env['pos.session'].sudo().browse(pos_session_id)
                warehouse = pos_session.config_id.picking_type_id.warehouse_id

                # POINT OF SALE EMPLOYEE
                user = self.env['res.users'].sudo().browse(pos_session.user_id.id)
                bodega_id = pos_session.config_id.point_of_sale_id
                # bodega_id = user[0].allowed_pos.point_of_sale_id
                serie_id = pos_session.config_id.point_of_sale_series
                # serie_id = user[0].allowed_pos.point_of_sale_series
                employee = user.employee_ids[:1]

            efectivo_entregado = 0.0
            # Buscar los pagos relacionados con la orden
            pagos = self.env['pos.payment'].search(
                [('pos_order_id', '=', pos_order.id)])

            # Verificar si hubo pagos en efectivo y acumular su monto
            method_payment_list = []
            for pago in pagos:

                payment_method = pago.payment_method_id
                if "CREDITO" in payment_method.name:
                    partner_id = orders[0].get('data').get('partner_id')
                    if len(orders[0].get('data', {}).get('statement_ids',
                                                         [])) > 1:
                        discount_credit_intitution = \
                            orders[0].get('data').get('statement_ids')[0][
                                2].get('amount')
                    else:
                        discount_credit_intitution = \
                            orders[0].get('data').get('statement_ids')[0][
                                2].get('amount')
                    if partner_id:
                        institution_client = self.env['institution.client'].search([
                            ('partner_id', '=', partner_id),
                            ('institution_id', '=', id_credit_intitution)
                        ], limit=1)

                        if institution_client:
                            new_sale_value = institution_client[0].available_amount - discount_credit_intitution
                            institution_id = institution_client.institution_id

                            institution_client.write(
                                {'available_amount': new_sale_value})

                            for payment in pos_order.payment_ids:
                                if payment.payment_method_id.code_payment_method == 'CREDITO':
                                    payment.write({
                                        'selecteInstitutionCredit': str(institution_client.institution_id.id)
                                    })

                        else:
                            pass
                    else:
                        pass

                if "efectivo" in payment_method.name.lower() or "efect" in payment_method.name.lower():
                    efectivo_entregado += pago.amount
                    efectivo_total = pago.amount
                    obj_tarjeta = {
                        "type": 12,
                        "method": "efectivo",
                        "efectivo_total": efectivo_total,
                    }
                    method_payment_list.append(obj_tarjeta)
                elif "tarjeta" == payment_method.name.lower():
                    total_tarjeta = pago.amount
                    efectivo_total = pago.amount
                    obj_tarjeta = {
                        "type": 8,
                        "method": "tarjeta",
                        "efectivo_total": efectivo_total,
                    }
                    method_payment_list.append(obj_tarjeta)

                elif "CTACLIENTE" == payment_method.code_payment_method:
                    total_tarjeta = pago.amount
                    efectivo_total = pago.amount
                    obj_cuenta_cliente = {
                        "type": 4,
                        "method": "cambio",
                        "efectivo_total": efectivo_total,
                    }
                    method_payment_list.append(obj_cuenta_cliente)
                elif "CREDITO" == payment_method.name:
                    efectivo_entregado += pago.amount
                    efectivo_total = pago.amount
                    obj_credit = {
                        "type": 11,
                        "method": "credito",
                        "efectivo_total": efectivo_total,
                    }
                    method_payment_list.append(obj_credit)
                else:
                    total_cheque = pago.amount
                    efectivo_total = pago.amount
                    obj_cheque = {
                        "type": 9,
                        "method": "cheque",
                        "efectivo_total": efectivo_total,
                    }
                    method_payment_list.append(obj_cheque)

            if len(method_payment_list) > 2:
                type_payment = method_payment_list[2].get('type')
                method = method_payment_list[2].get('method')
                efectivo_tarjeta = method_payment_list[2].get(
                    'efectivo_total')
                efectivo_efectivo = method_payment_list[1].get(
                    'efectivo_total')
            elif len(method_payment_list) > 1:
                type_payment = method_payment_list[1].get('type')
                method = method_payment_list[1].get('method')
                efectivo_tarjeta = method_payment_list[1].get(
                    'efectivo_total')
                efectivo_efectivo = method_payment_list[0].get(
                    'efectivo_total')
            elif len(method_payment_list) > 0:
                type_payment = method_payment_list[0].get('type')
                method = method_payment_list[0].get('method')
                efectivo_tarjeta = method_payment_list[0].get(
                    'efectivo_total')
                efectivo_efectivo = 0.0
            else:
                type_payment = None
                method = None
                efectivo_tarjeta = 0.0
                efectivo_efectivo = 0.0
            if pos_order:
                check_info_list = []
                card_info_list = []
                check_info_dict = {}
                card_info_dict = {}

                # Buscar la orden que coincide con el nombre
                ref_order = [o['data'] for o in orders if
                             o['data'].get(
                                 'name') == pos_order.pos_reference]

                # Extraer información de pagos de la UI
                for order in ref_order:
                    if len(order.get('statement_ids', [])) == 2:
                        institutionMixto = order.get('statement_ids', [])[0][2].get(
                            'institution_card')
                        institutionMixtoCheque = order.get('statement_ids', [])[0][2].get(
                            'institution_cheque')
                    else:
                        id_institution_cheque = order.get('statement_ids', [])[0][2].get(
                            'institution_cheque')
                    for payment_id in order.get('statement_ids', []):
                        check_number = payment_id[2].get('check_number')
                        owner_name = payment_id[2].get('owner_name')
                        bank_account = payment_id[2].get('bank_account')
                        bank_name = payment_id[2].get('bank_name')
                        id_institution = payment_id[2].get(
                            'institution_cheque')

                        # Tarjeta
                        number_voucher = payment_id[2].get(
                            'number_voucher')
                        type_card = payment_id[2].get('type_card')
                        number_lote = payment_id[2].get('number_lote')
                        holder_card = payment_id[2].get('holder_card')
                        bin_tc = payment_id[2].get('bin_tc')
                        id_institution = payment_id[2].get(
                            'institution_card')

                        # Cambio
                        amount = payment_id[2].get('amount')

                        # Agregar datos del cheque si existen
                        if check_number:
                            check_info = {
                                'check_number': check_number,
                                'check_owner': owner_name,
                                'check_bank_account': bank_account,
                                'bank_id': int(
                                    bank_name) if bank_name else False,
                            }
                            check_info_list.append(check_info)

                        # Agregar datos de la tarjeta si existen
                        if number_voucher:
                            card_info = {
                                'number_voucher': number_voucher,
                                'type_card': type_card,
                                'number_lote': number_lote,
                                'holder_card': holder_card,
                                'bin_tc': bin_tc,
                            }
                            card_info_list.append(card_info)

                # Guardar los datos en los campos JSON del registro POS
                pos_order.write({
                    'check_info_json': json.dumps(check_info_list),
                    'card_info_json': json.dumps(card_info_list),
                })

                for payment_id in ref_order[0].get('statement_ids', []):
                    data = payment_id[2]
                    if data.get('payment_transaction_id') or data.get(
                            'payment_transfer_number') or data.get(
                        'payment_bank_name') or data.get('orderer_identification'):

                        write_data = {
                            'payment_transaction_id': data.get('payment_transaction_id'),
                            'payment_transfer_number': data.get('payment_transfer_number'),
                            'payment_bank_name': data.get('payment_bank_name'),
                            'orderer_identification': data.get('orderer_identification'),
                        }

                        # Agregar datos de autorización manual si existen
                        if data.get('self_authorized'):
                            write_data['self_authorized'] = True
                            write_data['self_authorized_by'] = data.get('self_authorized_by')
                            write_data['self_authorization_date'] = fields.Datetime.now()

                        pos_order.write(write_data)
                        break

                for check in pos_order.payment_ids:
                    for check_list in check_info_list:
                        if check.payment_method_id.allow_check_info:
                            if check.id not in check_info_dict and check_list not in check_info_dict.values():
                                check_info_dict.update({
                                    check.id: check_list
                                })

                # Escribir la información de cheque en los pagos
                for check in pos_order.payment_ids:
                    if check.id in check_info_dict:
                        check.write(check_info_dict[check.id])

                # Actualizar la información de tarjeta en los pagos
                for card in pos_order.payment_ids:
                    for card_list in card_info_list:
                        if card.payment_method_id.allow_check_info:
                            if card.id not in card_info_dict and card_list not in card_info_dict.values():
                                card_info_dict.update({
                                    card.id: card_list
                                })

                # Escribir la información de tarjeta en los pagos
                for card in pos_order.payment_ids:
                    if card.id in card_info_dict:
                        card.write(card_info_dict[card.id])

                # LOGICA PARA BASE ANTIGUA
                # Iterar sobre las órdenes y obtener cada una como diccionario

                data_order = json.dumps(orders)
                # DATA DE LA VENTA
                global cliente
                global data_card
                global amount_total
                global amount_return
                global pagos_info
                global amount_tax
                global efectivo
                global iva
                global subtx
                global subt0
                global subtotal
                global product_reward
                global cupon
                subt0 = 0
                data_card = None
                for order in orders:
                    order_data = order.get('data', {})
                    cliente = self.env['res.partner'].browse(
                        order_data.get('partner_id'))
                    amount_total = order_data.get('amount_total')
                    amount_return = order_data.get('amount_return')
                    amount_tax = order_data.get('amount_tax')
                    digital_media = order_data.get('digital_media')
                    if not digital_media and order_data.get('lines'):
                        for line in order_data.get('lines', []):
                            sale_order_origin = line[2].get('sale_order_origin_id')
                            if sale_order_origin and sale_order_origin.get('id'):
                                sale_order = self.env['sale.order'].browse(sale_order_origin['id'])
                                if sale_order:
                                    digital_media = sale_order.digital_media
                                    break
                    cupon = self.get_is_order_with_coupon(order_data.get('lines', []))

                    # updated_lines = self._generate_reward_lines_chatbot(order_data.get('lines', []))

                cliente_info = {
                    "id": int(cliente.id_database_old),
                    "ruc": cliente.vat,
                    "name": cliente.name.upper(),
                    "comercio": cliente.name.upper(),
                    "address": cliente.street if cliente.street else "",
                    "phone": cliente.phone if cliente.phone else "",
                    "email": cliente.email if cliente.phone else "",
                    "city": cliente.city if cliente.city else "",
                    "fechanac": "20191122",
                }

                for payment in order_data.get('statement_ids', []):
                    payment_data = payment[2]
                    payment_method_id = payment_data.get(
                        'payment_method_id')
                    payment_method = self.env['pos.payment.method'].browse(
                        payment_method_id)

                    check_number_check = None
                    bank_account_check = None
                    owner_name_check = None
                    bank_id = None
                    if check_number_check is None and payment_data.get(
                            'check_number') is not False:
                        check_number_check = payment_data.get(
                            'check_number')

                    if bank_account_check is None and payment_data.get(
                            'bank_account') is not False:
                        bank_account_check = payment_data.get(
                            'bank_account')

                    if owner_name_check is None and payment_data.get(
                            'owner_name') is not False:
                        owner_name_check = payment_data.get('owner_name')

                    if bank_id is None and payment_data.get(
                            'bank_id') is not False:
                        bank_id = payment_data.get('bank_id')
                    # buscar la institucion con los datos que vienen desde el front (en el pago)
                    # Función auxiliar para validar ID de institución
                    def get_valid_institution_id(value):
                        """Retorna el ID de institución si es válido (no None, no False, no 0, no '0', no '000000000000'), sino None"""
                        if value is None or value is False:
                            return None
                        try:
                            int_val = int(value)
                            if int_val <= 0:
                                return None
                            return value
                        except (TypeError, ValueError):
                            return None

                    # Buscar el primer ID de institución válido
                    payment_institution_id = (
                        get_valid_institution_id(payment_data.get('institution_card')) or
                        get_valid_institution_id(payment_data.get('institution_discount')) or
                        get_valid_institution_id(payment_data.get('institution_cheque')) or
                        get_valid_institution_id(payment_data.get('selecteInstitutionCredit'))
                    )

                    # Calcular idinst_value una sola vez para usar en todo el bloque
                    # Siempre será -1 si no hay institución válida, evitando idinst: 0
                    try:
                        idinst_value = int(payment_institution_id) if payment_institution_id else -1
                        if idinst_value <= 0:
                            idinst_value = -1
                    except (TypeError, ValueError):
                        idinst_value = -1

                    idInstituion = False
                    institution_client = self.env['institution.client']

                    if payment_institution_id:
                        try:
                            int_id = int(payment_institution_id)
                            if int_id > 0:
                                formatted_institution_id = f"{int_id:012d}"
                            else:
                                formatted_institution_id = False
                        except (TypeError, ValueError):
                            formatted_institution_id = False

                        if formatted_institution_id and formatted_institution_id != "000000000000":
                            idInstituion = self.env['institution'].sudo().search(
                                [('id_institutions', '=', formatted_institution_id)],
                                limit=1
                            )

                    if idInstituion:
                        institution_client = self.env['institution.client'].search(
                            [('institution_id', '=', idInstituion.id)],
                            limit=1
                        )
                    else:
                        institution_client = self.env['institution.client']
                    # if "tarjeta" in payment_method.name.lower():
                    if isinstance(payment_method.name,
                                  str) and 'tarjeta' in payment_method.name.lower().strip():
                        select_card = payment_data.get('type_card')

                        try:
                            id_card = self.env['credit.card'].browse(int(select_card))
                        except (TypeError, ValueError):
                            id_card = self.env['credit.card']

                        if len(method_payment_list) > 1:
                            pagos_info = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": efectivo_efectivo,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "val_tc": efectivo_tarjeta,
                                "voucher_tc": payment_data.get(
                                    'number_voucher'),
                                "idbank_tc": int(id_card.code_card),
                                "lote_tc": payment_data.get(
                                    'number_voucher'),
                                "titular_tc": cliente.name,
                                "bin_tc": payment_data.get('bin_tc'),
                                "nOportunidad": 1,
                                "lPacifico": 0,
                            }
                            data_card = pagos_info
                        else:
                            pagos_info = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": 0.0,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "val_tc": amount_total,
                                "voucher_tc": payment_data.get(
                                    'number_voucher'),
                                "idbank_tc": int(id_card.code_card),
                                "lote_tc": payment_data.get(
                                    'number_voucher'),
                                "titular_tc": cliente.name,
                                "bin_tc": payment_data.get('bin_tc'),
                                "nOportunidad": 1,
                                "lPacifico": 0,
                            }
                            data_card = pagos_info

                    elif "efectivo" in payment_method.name.lower().strip() and data_card is None or "efect" in payment_method.name.lower().strip() and data_card is None:
                        if institution_client:
                            efectivo = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": math.trunc(
                                    efectivo_total * 100) / 100,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "nOportunidad": 0,
                                "lPacifico": 0
                            }
                            data_card = efectivo
                        else:
                            efectivo = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": math.trunc(
                                    efectivo_total * 100) / 100,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "nOportunidad": 0,
                                "lPacifico": 0
                            }
                            data_card = efectivo
                    elif "anticipo" in payment_method.name.lower():
                        if len(method_payment_list) > 1:
                            if amount_return > 0:
                                client_account_info = {
                                    "cambio": amount_return,
                                    "idinst": idinst_value,
                                    "efectivo": method_payment_list[1].get('efectivo_total'),
                                    "efectivo_nc": method_payment_list[2].get('efectivo_total'),
                                    "anticipo": 0.0,
                                    "alcance_nc": 0.0,
                                    "nro_ret": "",
                                    "nOportunidad": 0,
                                    "lPacifico": 0
                                }
                            elif amount_return == 0:
                                client_account_info = {
                                    "cambio": amount_return,
                                    "idinst": idinst_value,
                                    "efectivo": method_payment_list[0].get('efectivo_total'),
                                    "efectivo_nc": method_payment_list[1].get('efectivo_total'),
                                    "anticipo": 0.0,
                                    "alcance_nc": 0.0,
                                    "nro_ret": "",
                                    "nOportunidad": 0,
                                    "lPacifico": 0
                                }
                        else:
                            client_account_info = {
                                "cambio": 0,
                                "idinst": idinst_value,
                                "efectivo": method_payment_list[0].get('efectivo_total'),
                                "efectivo_nc": method_payment_list[0].get('efectivo_total'),
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "nOportunidad": 0,
                                "lPacifico": 0
                            }
                        data_card = client_account_info

                    elif "credito" in payment_method.name.lower() or "crédito" in payment_method.name.lower():
                        institution_client = self.env['institution.client'].search([
                            ('partner_id', '=', cliente.id),
                            ('institution_id', '=', id_credit_intitution)
                        ], limit=1)

                        credit = institution_client.institution_id.type_credit_institution == 'credit' if institution_client.institution_id else False
                        if len(method_payment_list) > 1:

                            client_account_info = {
                                "cambio": 0,
                                "credito": discount_credit_intitution,
                                "idinst": int(institution_client.institution_id.id_institutions),
                                "efectivo": round((efectivo_efectivo - amount_return), 2),
                                "efectivo_nc": 0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "nOportunidad": 0,
                                "lPacifico": 0,
                            }
                        else:
                            client_account_info = {
                                "cambio": 0,
                                "credito": discount_credit_intitution,
                                "idinst": int(institution_client.institution_id.id_institutions),
                                # enviar id de la institucion
                                "efectivo": 0.0,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "nOportunidad": 0,
                                "lPacifico": 0,
                            }

                        data_card = client_account_info
                    elif "cheque" in payment_method.name.lower().strip() or "cheques" in payment_method.name.lower().strip() or "cheque / transf'" in payment_method.name.lower().strip():
                        id_bank = self.env['res.bank'].sudo().search([('id', '=', bank_id)],
                                                                     limit=1)
                        if len(method_payment_list) > 1:
                            cheque_info = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": efectivo_efectivo,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "val_ch": efectivo_tarjeta,
                                "nro_ch": check_number_check,
                                "idbank_ch": int(id_bank.x_id_base_antigua),
                                "cta_ch": bank_account_check,
                                "fecha_ch": datetime.now().strftime("%Y%m%d"),
                                "titular_ch": owner_name_check,
                                "nOportunidad": 1,
                                "lPacifico": 0
                            }
                            data_card = cheque_info

                        else:
                            cheque_info = {
                                "cambio": amount_return,
                                "idinst": idinst_value,
                                "efectivo": 0.0,
                                "efectivo_nc": 0.0,
                                "anticipo": 0.0,
                                "alcance_nc": 0.0,
                                "nro_ret": "",
                                "val_ch": amount_total,
                                "nro_ch": check_number_check,
                                "idbank_ch": int(id_bank.x_id_base_antigua),
                                "cta_ch": bank_account_check,
                                "fecha_ch": datetime.now().strftime("%Y%m%d"),
                                "titular_ch": owner_name_check,
                                "nOportunidad": 1,
                                "lPacifico": 0
                            }
                            data_card = cheque_info

                productos_info_cdet = {
                    "fields": [
                        "iditem",
                        "cantidad",
                        "precio",
                        "piva",
                        "descuento",
                        "promocion",
                        "pdesc"
                    ],
                    "data": []
                }

                res = self.procesar_lineas_orden(order_data.get('lines', []))
                sub15 = res['subtotales'].get('sub15', 0.0)
                sub0 = res['subtotales'].get('sub0', 0.0)

                productos_info_cdet["data"] = res['lineas']

                zona_horaria_ecuador = pytz.timezone('America/Guayaquil')
                fecha_hora_ecuador = datetime.now(zona_horaria_ecuador)

                # Sumar 3 minutos a la hora actual
                l_sync_date = fecha_hora_ecuador + timedelta(minutes=3)
                formato_fecha_hora = fecha_hora_ecuador.strftime(
                    '%Y-%m-%d %H:%M:%S')
                fecha_hora_lsync = l_sync_date.strftime(
                    '%Y-%m-%d %H:%M:%S')
                warehouse_id = pos_config.get_pos_by_ware_and_pos_c(warehouse,
                                                                    pos_session.config_id)
                # clave_acceso = ""
                # if order_data.get("to_invoice"):
                #     tipo_comprobante = "01"
                #     ruc = "1191751422001"
                #     ambiente = "2"
                #     serie = warehouse_id.get('point_of_sale_series')
                #     numero_comprobante = order_id
                #     codigo_numerico = random.randint(10000000, 99999999)
                #     tipo_emision = random.randint(1, 9)

                # Generar la clave de acceso una vez y reutilizarla
                # clave_acceso = self.generar_clave_acceso(
                #     datetime.now(), tipo_comprobante, ruc, ambiente,
                #     serie,
                #     numero_comprobante, codigo_numerico, tipo_emision
                # )
                id_pos_order = self.env['pos.order'].sudo().search([(
                    'access_token', '=', order_data.get('access_token'))], limit=1)
                factura = {
                    "idcustomer": int(cliente.id_database_old),
                    "iduser": employee.id_employeed_old,
                    "t_init": formato_fecha_hora,
                    "subtotal": sub0 + sub15,
                    "iva": amount_tax,
                    "total": amount_total,
                    "descuento": res['total_discount'],
                    "nota": ".",
                    "idbodega": bodega_id,
                    "formapago": type_payment if order_data.get('to_invoice') else 0,
                    "l_sync": 0,  # Siempre 0
                    "l_close": 1,  # Cerrado
                    "l_auth": 0,  # Siempre 0
                    "l_void": 0,  # No es nulo
                    "l_file": 0,  # Archivo generado
                    "nprint": 1,  # Número de impresiones
                    "serie": serie_id,
                    "ccust": cliente_info,
                    "cfp": data_card if order_data.get('to_invoice') else {
                        "idinst": institution_id.id_institutions},
                    "cdet": productos_info_cdet,
                    "t_close": formato_fecha_hora,
                    "t_sync": fecha_hora_lsync,
                    "piva": 15,
                    "claveacceso": None,
                    "l_cust": 1,
                    "is_fe": 1 if order_data.get('to_invoice') else 0,
                    "subtx": abs(sub15),
                    "subt0": abs(sub0),
                    "tipo": 3 if not order_data.get("to_invoice") else 1,
                    "is_chatboot": is_chatboot,
                    "digital_media": digital_media or "",
                    "cupon": cupon or False
                }

                # if order_data.get("to_invoice"):
                #     pos_order.write({'key_order': clave_acceso})

                json_storage_model = self.env['json.storage']
                pos_config = pos_session.config_id
                point_of_sale_id = pos_config.point_of_sale_id

                # Buscar el cliente basado en el vat (client_invoice)
                client_vat = cliente.vat
                partner = self.env['res.partner'].search([('vat', '=', client_vat)], limit=1)
                idcustomer_value = int(
                    partner.id_database_old) if partner and partner.id_database_old else -1

                # Actualizar el diccionario factura con el idcustomer correcto
                factura['idcustomer'] = idcustomer_value

                # Crear el nuevo registro en json.storage
                json_storage_model.sudo().create({
                    'json_data': json.dumps([{"factura": factura}],
                                            indent=4),
                    'employee': f"{employee.name}",
                    'pos_order_id': bodega_id,
                    'id_point_of_sale': (warehouse_id or {}).get('external_id', ""),
                    'client_invoice': cliente.vat,
                    'pos_order': id_pos_order.id,
                    'id_database_old_invoice_client': cliente.id_database_old,
                })

        for item in order_ids:
            order = self.browse(item['id'])
            item['sri_authorization'] = order.sri_authorization or False
        return order_ids

    @staticmethod
    def modulo_11(clave):
        """Calcula el dígito verificador usando el algoritmo módulo 11."""
        factores = [2, 3, 4, 5, 6, 7]
        suma = 0

        # Recorrer la clave de derecha a izquierda y aplicar los factores.
        for i, c in enumerate(reversed(clave)):
            factor = factores[i % len(factores)]
            suma += int(c) * factor

        # Obtener el residuo de la suma.
        residuo = suma % 11
        digito_verificador = 11 - residuo

        # Si el resultado es 11 o 10, el dígito debe ser 0.
        return 0 if digito_verificador in [11, 10] else digito_verificador

    def generar_clave_acceso(self, fecha_emision, tipo_comprobante, ruc,
                             ambiente,
                             serie, numero_comprobante, codigo_numerico,
                             tipo_emision):
        """Genera la clave de acceso de 49 dígitos para el SRI."""

        # Asegurar que los campos estén correctamente formateados
        fecha_emision_str = fecha_emision.strftime('%d%m%Y')
        ruc = str(ruc).zfill(
            13)  # Rellenar con ceros a la izquierda si es necesario
        serie = str(serie).zfill(6)  # La serie debe tener 6 dígitos
        numero_comprobante = str(numero_comprobante).zfill(9)  # 9 dígitos
        codigo_numerico = '12345678'

        # Crear la clave base (sin el dígito verificador)
        clave = (
            f"{fecha_emision_str}"
            f"{str(tipo_comprobante).zfill(2)}"
            f"{ruc}"
            f"{ambiente}"
            f"{serie}"
            f"{numero_comprobante}"
            f"{codigo_numerico}"
            f"{tipo_emision}"
        )

        # Calcular el dígito verificador usando el módulo 11
        digito_verificador = self.modulo_11(clave)

        # Agregar el dígito verificador al final de la clave
        clave_acceso = f"{clave}{digito_verificador}"

        # Verificar que la clave generada sea de 49 caracteres exactos
        if len(clave_acceso) != 49:
            raise ValueError(
                "La clave de acceso debe tener exactamente 49 caracteres.")
        return clave_acceso

    @api.constrains('partner_id', 'amount_total', 'session_id')
    def _check_payment_restriction(self):
        for order in self:
            if order.partner_id and order.partner_id.name == 'Consumidor Final':
                if order.amount_total > 1.0:
                    raise ValidationError(
                        'El monto máximo para Consumidor Final es de $1.')
                allowed_payment_method = order.session_id.config_id.payment_method_ids.filtered(
                    lambda pm: pm.is_cash_count)
                if not allowed_payment_method:
                    raise ValidationError(
                        'Solo se permite el método de pago en efectivo para Consumidor Final.')

    @api.model
    def _order_fields(self, ui_order):
        fields = super(PosOrder, self)._order_fields(ui_order)

        order_lines = fields.get('lines', [])
        new_reward_lines = self._generate_reward_lines(order_lines)
        fields['lines'] = new_reward_lines

        return fields

    def _generate_reward_lines(self, lines):

        updated_lines = []
        for line in lines:
            line_data = line[2]

            if line_data.get('reward_product_id') and line_data.get('discount') == 100:
                reward_product_id = line_data.get('reward_product_id')
                if reward_product_id:
                    # price_unit = 0
                    qty = line_data.get('qty', 1)
                    price_subtotal = line_data.get('price_unit', 0) * qty
                    price_subtotal_incl = price_subtotal
                    new_line = [
                        0, 0, {
                            'product_id': reward_product_id,
                            'qty': qty,
                            'price_unit': line_data.get('price_unit', 0),
                            'price_subtotal': price_subtotal,
                            'price_subtotal_incl': price_subtotal_incl,
                            'tax_ids': line_data.get('tax_ids', []),
                            'full_product_name': line_data.get('full_product_name', ''),
                            'name': line_data.get('name', ''),
                            'reward_product_id': reward_product_id,
                            'original_id_reward': line_data.get('product_id', ''),
                            'coupon_id': line_data.get('coupon_id', ''),
                            'is_reward_line': True,
                            'product_free': True,
                            'discount': 100,
                            'reward_id': line_data.get('reward_id', ''),
                            'product_uom_id': line_data.get('product_uom_id'),
                        }
                    ]
                    updated_lines.append(new_line)
            else:
                updated_lines.append(line)

        return updated_lines

    def search_product_id_old(self, product_id):
        return self.env['product.product'].browse(product_id)

    def convertir_a_hora_ecuador(self, hora_utc):
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)

    def get_type_note_credit(self, order):
        if len(order.payment_ids) == 1:
            if order.payment_ids[0].payment_method_id.is_cash_count:
                return "Devolucion en efectivo"
            elif order.payment_ids[
                0].payment_method_id.code_payment_method == 'CTACLIENTE':
                return "Cambio"
            elif order.payment_ids[
                0].payment_method_id.code_payment_method == 'CREDITO':
                return "Abono cxc"
            else:
                return "Anulacion de vaucher"
        else:
            return "Anulacion de vaucher"

    def refund_insitutions(self, orders, pos_order):

        pagos = self.env['pos.payment'].search(
            [('pos_order_id', '=', pos_order.id)])

        for pago in pagos:
            payment_method = pago.payment_method_id
            if "CREDITO" in payment_method.name:
                partner_id = orders[0].get('data').get('partner_id')
                if len(orders[0].get('data', {}).get('statement_ids', [])) > 1:
                    discount_credit_intitution = \
                        orders[0].get('data').get('statement_ids')[0][2].get(
                            'amount')
                else:
                    discount_credit_intitution = \
                        orders[0].get('data').get('statement_ids')[0][2].get(
                            'amount')
                if partner_id:
                    institution_client = self.env['institution.client'].search([('partner_id', '=', partner_id)], limit=1)

                    if institution_client:
                        new_sale_value = institution_client[0].available_amount - discount_credit_intitution

                        institution_client.write(
                            {'available_amount': new_sale_value})
                    else:
                        pass
                else:
                    pass

    def _auto_apply_rewards(self):
        if self._context.get('channel') == 'chatbot':
            rewards = self.env['loyalty.reward'].search([
                ('is_main_chat_bot', '=', True),
            ])
            for order in self:
                for rw in rewards:
                    order._apply_reward(rw)
            return
        return super(PosOrder, self)._auto_apply_rewards()

    @api.model
    def search_paid_order_ids(self, config_id, domain, limit, offset):
        """Search for 'paid' orders that satisfy the given domain, limit and offset.
        By default, shows only today's orders unless other filters are specified."""

        # Default domain to exclude draft/canceled orders
        default_domain = [('state', '!=', 'draft'), ('state', '!=', 'cancel')]

        # Initialize domain if None
        if domain is None:
            domain = []

        # Add today's date filter only if no date filter exists and domain is empty
        if not any(d[0] == 'date_order' for d in domain) and not domain:
            today = fields.Date.context_today(self)
            start_of_day = fields.Datetime.to_datetime(f"{today} 00:00:00")
            end_of_day = fields.Datetime.to_datetime(f"{today} 23:59:59")
            domain += [
                ('date_order', '>=', start_of_day),
                ('date_order', '<=', end_of_day)
            ]

        # Build final domain
        if not domain:
            real_domain = AND([[('config_id', '=', config_id)], default_domain])
        else:
            real_domain = AND([domain, [('config_id', '=', config_id)], default_domain])

        # Search orders
        orders = self.search(real_domain, limit=limit, offset=offset, order='date_order desc')

        # Filter by POS currency
        pos_config = self.env['pos.config'].browse(config_id)
        orders = orders.filtered(lambda order: order.currency_id == pos_config.currency_id)

        # Search order lines (including refunds)
        orderlines = self.env['pos.order.line'].search([
            '|',
            ('refunded_orderline_id.order_id', 'in', orders.ids),
            ('order_id', 'in', orders.ids)
        ])

        # Track last modification time for each order
        orders_info = defaultdict(lambda: datetime.min)
        for orderline in orderlines:
            key_order = (orderline.order_id.id if orderline.order_id in orders
                         else orderline.refunded_orderline_id.order_id.id)
            if orders_info[key_order] < orderline.write_date:
                orders_info[key_order] = orderline.write_date

        # Include orders that might not have lines
        for order in orders:
            if order.id not in orders_info:
                orders_info[order.id] = order.write_date

        totalCount = len(orders) if limit else self.search_count(real_domain)

        return {
            'ordersInfo': sorted(orders_info.items(), key=lambda x: x[1], reverse=True),
            'totalCount': totalCount
        }

    def get_is_order_with_coupon(self, lines):
        return any(int(line[2].get('coupon_id', 0) or 0) > 1 for line in lines)

    def _get_product_iditem(self, product):
        """
        Obtiene el iditem (id_database_old) del producto de forma robusta.
        Busca primero en product.product, luego en product.template.

        Args:
            product: Registro de product.product

        Returns:
            int: El id_database_old como entero, o 0 si no existe
        """
        # Primero intentar obtener del product.product
        id_db_old = product.id_database_old

        # Si no existe, intentar del template
        if not id_db_old and product.product_tmpl_id:
            id_db_old = product.product_tmpl_id.id_database_old

        # Convertir a entero de forma segura
        if id_db_old:
            try:
                return int(id_db_old)
            except (ValueError, TypeError):
                return 0
        return 0

    def procesar_lineas_orden(self, lineas_entrada):
        """
        Procesa líneas de orden fusionando productos normales con sus recompensas

        Args:
            lineas_entrada: Lista de tuplas [0, 0, {datos_linea}]

        Returns:
            dict: Formato de salida con fields y data, incluyendo subtotales
        """

        # Separar líneas por tipo
        productos_normales = []
        productos_gratis = []
        total_discount = 0

        # Diccionario para acumular subtotales por tasa de IVA
        subtotales_iva = {}

        for linea in lineas_entrada:
            datos = linea[2]

            # Verificar primero si es producto gratis
            if datos.get('reward_product_id', False) and datos.get('discount', 0) == 100:
                productos_gratis.append(datos)
            else:
                productos_normales.append(datos)

        # Construir líneas de salida
        lineas_salida = []

        # Procesar productos normales (con descuento incluido)
        for producto in productos_normales:

            precio_unit = abs(producto['price_unit'])
            cantidad = producto.get('qty', False) or producto['qty_to_invoice']

            # Calcular el valor del descuento aplicado
            porcentaje_descuento = abs(producto.get('discount', 0))
            precio_subtotal = precio_unit * cantidad
            descuento_total = (precio_subtotal * porcentaje_descuento) / 100
            total_discount += descuento_total

            # Calcular subtotal después del descuento
            subtotal_con_descuento = precio_subtotal - descuento_total

            # Obtener producto para impuestos
            product = self.env['product.product'].browse(producto['product_id'])
            tasa_iva = sum(tax.amount for tax in product.taxes_id)

            # Acumular en el subtotal correspondiente
            if tasa_iva not in subtotales_iva:
                subtotales_iva[tasa_iva] = 0.0
            subtotales_iva[tasa_iva] += subtotal_con_descuento

            # Verificar si tiene cupón
            coupon_id = producto.get('coupon_id')

            linea_normal = self.crear_linea_salida(
                producto,
                cantidad,
                precio_unit,
                descuento_total,
                coupon_id=coupon_id if coupon_id and coupon_id > 0 else False
            )
            lineas_salida.append(linea_normal)

        # Procesar productos gratis como líneas independientes
        for producto_gratis in productos_gratis:

            # Obtener el producto relacionado usando reward_product_id
            product_id = producto_gratis['reward_product_id']
            product = self.env['product.product'].browse(product_id)

            cantidad_gratis = producto_gratis.get('qty', False) or producto_gratis['qty_to_invoice']
            precio_producto = abs(product.product_tmpl_id.list_price)
            total_product_free = float(cantidad_gratis) * float(precio_producto)

            # Obtener información de impuestos
            piva = sum(tax.amount for tax in product.taxes_id)

            # Acumular en el subtotal correspondiente (productos gratis también cuentan)
            if piva not in subtotales_iva:
                subtotales_iva[piva] = 0.0
            # Los productos gratis tienen valor 0 en el subtotal
            # Si quieres contarlos, usa: subtotales_iva[piva] += 0.0

            coupon_id = producto_gratis.get('coupon_id')

            tipo_promocion = 3
            if coupon_id:
                cupon = self.env['loyalty.card'].browse(coupon_id)
                if cupon.exists() and cupon.program_id.program_type == 'coupons':
                    tipo_promocion = 4

            # tipo_promocion = 4 if (coupon_id and coupon_id > 0) else 3

            pdesc = producto_gratis.get('discount', 99.99)

            linea_producto_gratis = [
                self._get_product_iditem(product),
                cantidad_gratis,
                precio_producto,
                piva,
                total_product_free,
                tipo_promocion,
                pdesc
            ]

            lineas_salida.append(linea_producto_gratis)

        # Preparar subtotales en formato sub0, sub12, sub15, etc.
        subtotales = {}
        for tasa_iva, subtotal in subtotales_iva.items():
            # Convertir tasa de IVA a entero (0%, 12%, 15%, etc.)
            clave_subtotal = f"sub{int(tasa_iva)}"
            subtotales[clave_subtotal] = round(subtotal, 2)

        # Asegurar que sub0 exista aunque sea 0
        if 'sub0' not in subtotales:
            subtotales['sub0'] = 0.0

        return {
            'lineas': lineas_salida,
            'total_discount': round(total_discount, 2),
            'subtotales': subtotales
        }

    def crear_linea_salida(self, producto, cantidad, precio_unit, descuento, coupon_id=False):
        """
        Crea una línea en el formato de salida requerido
        """
        product = self.env['product.product'].browse(producto['product_id'])

        piva = sum(tax.amount for tax in product.taxes_id)

        pdesc = producto['discount']

        tipo_promocion = 0
        if coupon_id:
            cupon = self.env['loyalty.card'].browse(coupon_id)
            if cupon.exists() and cupon.program_id.program_type == 'coupons':
                tipo_promocion = 4

        return [
            self._get_product_iditem(product),  # iditem
            cantidad,  # cantidad
            precio_unit,  # precio
            piva,  # piva
            descuento,  # valor del descuento en dinero
            tipo_promocion,  # promocion (valor fijo)
            pdesc  # pdesc (porcentaje descuento)
        ]
