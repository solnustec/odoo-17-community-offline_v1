import hashlib
import base64
import json
import time
import uuid
import requests
import logging
from odoo.http import request

_logger = logging.getLogger(__name__)


def get_app_config():
    """Recupera los parámetros de configuración de Paymentez."""
    app_code = request.env['ir.config_parameter'].sudo().get_param('paymentez_app_code')
    app_key = request.env['ir.config_parameter'].sudo().get_param('paymentez_app_secret')
    paymentez_url = request.env['ir.config_parameter'].sudo().get_param('paymentez_app_url')
    return app_code, app_key, paymentez_url


def generate_token(app_code, app_key):
    """Genera el token de autenticación para Paymentez."""
    timestamp = str(int(time.time()))
    key_time = app_key + timestamp
    uniq_token = hashlib.sha256(key_time.encode()).hexdigest()
    str_union = f"{app_code};{timestamp};{uniq_token}"
    token = base64.b64encode(str_union.encode()).decode()
    return token


def create_payment_link(amount, description, user_email, name, last_name, cedula):
    """Crea el enlace de pago utilizando la API de Paymentez."""
    app_code, app_key, paymentez_url = get_app_config()
    token = generate_token(app_code, app_key)
    dev_reference = str(uuid.uuid4())

    data = {
        "user": {
            "id": str(cedula),
            "email": user_email,
            "name": name,
            "last_name": last_name
        },
        "order": {
            "dev_reference": dev_reference,
            "description": description,
            "amount": float(amount),
            "tax_percentage": 0,
            "taxable_amount": 0,
            "installments_type": 0,
            "currency": "USD"
        },
        "configuration": {
            "partial_payment": True,
            "expiration_time": 7200,
            "allowed_payment_methods": ["Card"],
            "success_url": "https://www.paymentez.com.ec/inicio",
            "failure_url": "https://www.paymentez.com.ec/inicio",
            "pending_url": "http://192.168.13.53:4200/summary",
            "review_url": "http://192.168.13.53:4200/summary"
        }
    }

    headers = {
        "Auth-Token": token,
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(paymentez_url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        status_code = e.response.status_code if e.response else "No response"
        error_text = e.response.text if e.response else "Sin respuesta"
        raise
