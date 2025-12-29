# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging
import json
import uuid

_logger = logging.getLogger(__name__)


def _to_float(v, default=0.0):
    """Convierte un valor a tipo float"""
    if v is None:
        return float(default)
    s = str(v).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return float(default)


class PaymentezWebhookController(http.Controller):

    @http.route(['/webhook/nuvei', '/webhook/paymentez'], type='json', auth='public', methods=['POST'], csrf=False)
    def paymentez_webhook(self, **kwargs):
        raw_body = request.httprequest.data.decode("utf-8") or ""
        _logger.info(f"Webhook Paymentez recibido: {raw_body[:500]}...")

        try:
            payload = json.loads(raw_body)
        except Exception as e:
            _logger.error(f"Error parseando JSON del webhook: {str(e)}")
            return {"ok": False, "error": "invalid_json", "detail": str(e)}

        txn = payload.get("transaction", {})
        txn_id = txn.get("id")
        txn_status = txn.get("status")
        ltp_id = txn.get("ltp_id")
        reference = payload.get("reference") or txn.get("dev_reference") or txn_id or "SIN_REFERENCIA"
        provider_reference = f"paymentez-{txn.get('order_description', txn_id)}"


        # PASO 1: Guardar en nuvei.transaction (log de todas las transacciones)
        try:
            request.env['nuvei.transaction'].sudo().create_from_webhook(payload)
        except Exception as e:
            _logger.error(f"Error creando nuvei.transaction: {str(e)}")

        # PASO 2: Buscar transacción existente por ltp_id (transacciones de app móvil)
        if ltp_id:
            existing_tx = request.env['payment.transaction'].sudo().search([
                ('payment_transaction_id', '=', ltp_id),
                ('state', '=', 'pending'),
                ('is_app_transaction', '=', True)
            ], limit=1)

            if existing_tx:
                try:
                    if txn_status == '1':  # Aprobada
                        existing_tx.sudo().write({'state': 'done', 'card_info': raw_body})
                        existing_tx._set_payment_done()
                        return {
                            "ok": True,
                            "reference": existing_tx.reference,
                            "provider_reference": provider_reference,
                            "transaction_id": txn_id,
                            "state": "done",
                            "message": "Transacción existente actualizada"
                        }
                    elif txn_status in ['2', '4', '5']:  # Cancelada, Rechazada, Expirada
                        existing_tx.sudo().write({'state': 'error', 'card_info': raw_body})
                        return {
                            "ok": False,
                            "reference": existing_tx.reference,
                            "error": "payment_failed",
                            "status": txn_status,
                            "message": "Pago rechazado/cancelado"
                        }
                except Exception as e:
                    _logger.error(f"Error actualizando transacción existente: {str(e)}")

        # PASO 3: Solo procesar pagos APROBADOS (status = '1') para crear nueva transacción
        if txn_status != '1':
            return {
                "ok": False,
                "error": "payment_not_approved",
                "status": txn_status,
                "detail": f"Estado de pago: {txn_status}"
            }

        # PASO 4: Recuperar el proveedor Paymentez
        payment_provider = request.env['payment.provider'].sudo().search(
            [('code', '=', 'paymentez')], limit=1
        )
        if not payment_provider:
            payment_provider = request.env['payment.provider'].sudo().search(
                [('name', 'ilike', 'Paymentez')], limit=1
            )

        if not payment_provider:
            msg = "Proveedor Paymentez no encontrado"
            _logger.error(msg)
            return {"ok": False, "error": "provider_not_found", "detail": msg}

        # PASO 5: Recuperar el método de pago (card)
        payment_method = request.env['payment.method'].sudo().search(
            [('code', '=', 'card'), ('active', '=', True)], limit=1
        )

        if not payment_method:
            msg = "Método de pago 'card' no encontrado"
            _logger.error(msg)
            return {"ok": False, "error": "payment_method_not_found", "detail": msg}

        # PASO 6: Buscar la orden de venta utilizando el transaction_id
        sale_order = request.env['sale.order'].sudo().search([
            ('transaction_id', '=', reference)
        ], limit=1)

        if not sale_order:
            # Intentar buscar por dev_reference o order_description
            alt_ref = txn.get("dev_reference") or txn.get("order_description")
            if alt_ref:
                sale_order = request.env['sale.order'].sudo().search([
                    '|',
                    ('transaction_id', '=', alt_ref),
                    ('name', '=', alt_ref)
                ], limit=1)

        if not sale_order:
            msg = f"Orden de venta no encontrada para reference: {reference}"
            _logger.error(msg)
            return {"ok": False, "error": "order_not_found", "detail": msg}


        # PASO 7: Verificar si ya existe una transacción de pago para esta orden
        existing_payment_tx = request.env['payment.transaction'].sudo().search([
            ('sale_order_ids', 'in', [sale_order.id]),
            ('state', '=', 'done'),
            ('provider_id', '=', payment_provider.id)
        ], limit=1)

        if existing_payment_tx:
            return {
                "ok": True,
                "reference": existing_payment_tx.reference,
                "provider_reference": existing_payment_tx.provider_reference,
                "transaction_id": txn_id,
                "state": "done",
                "message": "Transacción ya procesada anteriormente"
            }

        # PASO 8: Crear la transacción de pago con referencia única
        partner = sale_order.partner_id
        unique_reference = f"{sale_order.name}-{txn_id or uuid.uuid4().hex[:8]}"

        # Verificar que la referencia sea única
        ref_exists = request.env['payment.transaction'].sudo().search([
            ('reference', '=', unique_reference)
        ], limit=1)
        if ref_exists:
            unique_reference = f"{sale_order.name}-{uuid.uuid4().hex[:8]}"

        try:
            payment_tx_vals = {
                'amount': _to_float(txn.get("amount")) or sale_order.amount_total,
                'currency_id': sale_order.currency_id.id or request.env.ref("base.USD").id,
                'partner_id': partner.id,
                'payment_method_id': payment_method.id,
                'reference': unique_reference,
                'provider_reference': provider_reference,
                'sale_order_ids': [(6, 0, [sale_order.id])],
                'provider_id': payment_provider.id,
                'state': 'draft',  # Empezar en draft, luego cambiar a done
                'operation': 'online_redirect',
            }

            # Agregar card_info si el campo existe
            if hasattr(request.env['payment.transaction'], 'card_info'):
                payment_tx_vals['card_info'] = raw_body

            payment_tx = request.env['payment.transaction'].sudo().create(payment_tx_vals)

            # Cambiar estado a done y ejecutar post-procesamiento
            payment_tx.sudo().write({'state': 'done'})
            payment_tx._set_payment_done()

            return {
                "ok": True,
                "reference": payment_tx.reference,
                "provider_reference": provider_reference,
                "transaction_id": txn_id,
                "payment_transaction_id": payment_tx.id,
                "state": "done",
            }

        except Exception as e:
            _logger.error(f"Error creando payment.transaction: {str(e)}", exc_info=True)
            return {
                "ok": False,
                "error": "create_transaction_failed",
                "detail": str(e)
            }

    @http.route('/api/nuvei/status/<string:transaction_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_payment_status(self, transaction_id, **kwargs):
        """
        Consulta el estado de un pago usando transaction_id almacenado en card_info
        """
        try:
            # Buscar la transacción de pago usando el transaction_id
            payment_tx = request.env['payment.transaction'].sudo().search([('reference', '=', transaction_id)], limit=1)

            if not payment_tx:
                _logger.error(f"Transacción no encontrada para transaction_id: {transaction_id}")
                return {"ok": False, "error": "payment_transaction_not_found", "transaction_id": transaction_id}

            card_info = payment_tx.card_info
            card_info_json = json.loads(card_info)

            # Obtener el status de la transacción en el card_info
            status = card_info_json.get("transaction", {}).get("status", "")


            # Validar el estado del pago
            if status == '1':
                return {
                    "ok": True,
                    "status": "approved",
                    "message": "Pago aprobado y orden confirmada."
                }
            elif status == '2':
                return {
                    "ok": False,
                    "status": "cancelled",
                    "message": "Pago cancelado."
                }
            elif status == '4':
                return {
                    "ok": False,
                    "status": "rejected",
                    "message": "Pago rechazado. Intenta nuevamente."
                }
            elif status == '5':
                return {
                    "ok": False,
                    "status": "expired",
                    "message": "El pago ha expirado. Intenta nuevamente."
                }
            else:
                return {
                    "ok": False,
                    "status": "pending",
                    "message": "Pago pendiente. Esperando confirmación."
                }

        except Exception as e:
            _logger.error(f"Error al consultar estado de la transacción: {str(e)}")
            return {"ok": False, "error": "unknown_error", "message": str(e)}
