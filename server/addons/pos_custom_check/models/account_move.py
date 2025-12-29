# -*- coding: utf-8 -*-

from odoo import api, fields, models
import datetime
import pytz

class AccountJournal(models.Model):
    _inherit = 'account.move'

    @api.model
    def get_value_for_note_credit(self, partner_id, pos_config_id):
        credit_moves = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('note_credit', '>', 0),
        ])

        current_time = datetime.datetime.now()
        processed_records = []

        for move in credit_moves:
            if move.note_credit:

                if move.create_date:
                    try:
                        invoice_date = move.create_date
                    except Exception:
                        invoice_date = None

                    if invoice_date:
                        invoice_date_tz_ec = self.convertir_a_hora_ecuador(invoice_date)
                        current_time_tz_ec = self.convertir_a_hora_ecuador(current_time)

                        # if invoice_date_tz_ec.date() != current_time_tz_ec.date():
                        #     move.write({'note_credit': 0})

            move_data = {
                'note_credit': move.note_credit,
            }
            processed_records.append(move_data)

        return processed_records


    def convertir_a_hora_ecuador(self, hora_utc):
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)


