from odoo import models, fields, api
import json
from datetime import datetime


class NuveiTransaction(models.Model):
    _name = 'nuvei.transaction'
    _description = 'Transacciones recibidas desde Nuvei (LinkToPay)'
    _order = 'create_date desc'

    transaction_id = fields.Char(string='ID Transacción', required=True, index=True)
    dev_reference = fields.Char(string='Referencia Comercial')
    order_description = fields.Char(string='Descripción del Pedido')
    amount = fields.Float(string='Monto')
    status = fields.Selection([
        ('1', 'Aprobada'),
        ('2', 'Cancelada'),
        ('4', 'Rechazada'),
        ('5', 'Expirada'),
    ], string='Estado')
    status_detail = fields.Char(string='Detalle del Estado')
    authorization_code = fields.Char(string='Código de Autorización')
    message = fields.Char(string='Mensaje')
    date = fields.Datetime(string='Fecha de Transacción')
    paid_date = fields.Datetime(string='Fecha de Pago')
    ltp_id = fields.Char(string='LinkToPay ID')
    stoken = fields.Char(string='Stoken')
    application_code = fields.Char(string='Código de Aplicación')
    terminal_code = fields.Char(string='Código de Terminal')

    user_id_string = fields.Char(string='ID del Usuario')
    user_email = fields.Char(string='Email del Usuario')

    # Información técnica
    raw_data = fields.Text(string='JSON Completo', help="Payload recibido en bruto")

    @api.model
    def create_from_webhook(self, data):
        transaction = data.get('transaction', {})
        user = data.get('user', {})
        # update transaction if exists
        # verify if transaction_id exists
        # existing_transaction = self.search([('transaction_id', '=', transaction.get('id'),
        #                                      ('status', '=', transaction.get('status')))], limit=1)
        # if not existing_transaction:
        return self.create({
            'transaction_id': transaction.get('id'),
            'dev_reference': transaction.get('dev_reference'),
            'order_description': transaction.get('order_description'),
            'amount': transaction.get('amount'),
            'status': transaction.get('status'),
            'status_detail': transaction.get('status_detail'),
            'authorization_code': transaction.get('authorization_code'),
            'message': transaction.get('message'),
            'date': self._parse_date(transaction.get('date')),
            'paid_date': self._parse_date(transaction.get('paid_date')),
            'ltp_id': transaction.get('ltp_id'),
            'stoken': transaction.get('stoken'),
            'application_code': transaction.get('application_code'),
            'terminal_code': transaction.get('terminal_code'),
            'user_id_string': user.get('id'),
            'user_email': user.get('email'),
            'raw_data': json.dumps(data),
        })

    def _parse_date(self, date_str):
        """Convierte fechas de formato 'DD/MM/YYYY HH:MM:SS' a datetime ISO"""
        if not date_str:
            return False
        try:
            return datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
        except Exception:
            return False

    def get_card_from_raw(self):
        """Retorna el objeto `card` del JSON guardado en `raw_data`."""
        self.ensure_one()
        if not self.raw_data:
            return False
        try:
            payload = json.loads(self.raw_data) if isinstance(self.raw_data, str) else self.raw_data
            return payload.get('card', False)
        except json.JSONDecodeError:
            return False
        except Exception:
            return False
