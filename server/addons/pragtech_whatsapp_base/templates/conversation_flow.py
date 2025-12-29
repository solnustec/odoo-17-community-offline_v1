import json
import logging
from odoo.http import request

from .asesor_flow import AsesorFlow
from .branch_flow import BranchFlow
from .buyProduct_flow import BuyProductFlow
from .dutyPharmacy_flow import DutyPharmacy
from .getDelivery import GetDelivery
from .invoice_flow import InvoiceFlow
from .meta_api import MetaAPi
from .saveOdoo import SaveOdoo
from ..templates.workPlace_flow import WorkPlace_Flow
from ..utils.user_session import UserSession

_logger = logging.getLogger(__name__)


class ConversationFlow:

    @classmethod
    def manejar_respuesta_interactiva(cls, numero, body):
        """Maneja la interacción con los botones del menú y flujo de compra."""
        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)
            SaveOdoo.save_interacction(body)

            # Salir de la conversación
            if body in ["salir_conversacion"]:
                session.sudo().write({'orden': ''})
                user_session.update_session(numero, state="manejar_salida")
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('salida')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            # Finalizar
            if body in ["finalizar"]:
                session.sudo().write({'orden': ''})
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('salida')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            # Regresar al menú principal
            if body == "regresar_menu":
                user_session.update_session(numero, state="menu_principal")
                session.sudo().write({'orden': ''})
                MetaAPi.enviar_mensaje_lista(numero)
                return

            # Flujo de sucursal cercana
            if body == "sucursal-cercana":
                BranchFlow.solicitar_ubicacion(numero)
                return

            # Flujo de farmacia de turno
            if body == "farmacia-turno":
                DutyPharmacy.farmacia_turno(numero)
                return

            # Regresar paso en promociones
            if body == "regresar_paso":
                user_session.update_session(numero, state="menu_secundario")
                MetaAPi.enviar_mensaje_con_botones(numero)
                return

            # Solicitar cédula o RUC
            if body == "solicitar_cedula_ruc":
                InvoiceFlow.solicitar_ced_ruc(numero)
                return

            # Solicitar cédula o RUC
            if body == "confirmar_datos":
                InvoiceFlow.manejar_orden(numero)
                return

            # Solicitar cédula o RUC
            if body == "eliminar_producto":
                InvoiceFlow.enviar_resumen_producto(numero)
                return

            # Manejar orden
            # if body == "manejar_orden":
            #     InvoiceFlow.manejar_orden(numero)
            #     return

            # Manejar orden
            if body == "recibir_email":
                InvoiceFlow.solicitar_email(numero)
                return

            if body == "manejar_datos_factura":
                InvoiceFlow.manejar_orden(numero)
                return

            if body == "confirmar_datos_factura":
                MetaAPi.confirmar_datos_factura(numero)
                return

            # Editar orden
            if body == "editar_orden":
                user_session.update_session(numero, state="editar_orden")
                InvoiceFlow.edit_order(numero)
                return

            # tipo envio
            if body == "tipo_envio":
                user_session.update_session(numero, state="tipo_envio")
                MetaAPi.botones_tipo_envio(numero)
                return

            # tipo pago
            if body == "tipo_pago":
                user_session.update_session(numero, state="tipo_pago")
                InvoiceFlow.manejar_pago(numero)
                return

            # Agregar producti
            # if body == "continuar_compra":
            #     user_session.update_session(numero, state="continuar_compra")
            #     BuyProductFlow.start_flow(numero)
            #     return

            # Continuar compra
            if body == "continuar_compra":
                user_session.update_session(numero, state="continuar_compra")
                BuyProductFlow.start_flow(numero)
                return

            # Confirmar orden factura
            if body == "confirmar_orden_factura":
                user_session.update_session(numero, state="confirmar_orden_factura")
                MetaAPi.botones_confirmar_compra(numero)
                return

            # # Manejar pago
            # if body == "confirmar_pago":
            #     InvoiceFlow.manejar_orden(numero)
            #     return

            # Acepta/rechaza condiciones
            if body == "acepta_condiciones":
                session.sudo().write({'privacy_polic': True})
                user_session.update_session(numero, state="menu_principal")
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('tiempo_envio')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                MetaAPi.enviar_mensaje_lista(numero)
                return

            if body == "rechaza_condiciones":
                user_session.update_session(numero, state="salir_politicas")
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('rechaza_condiciones')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            if body == "cotizar-receta":
                AsesorFlow.procesar_cotizacion(numero)
                return

            if body == "cotizar-receta-movil":
                from .appmovil_flow import AsesorMovilFlow
                user_session = UserSession(request.env)
                sale_order = None
                orden_data = {}

                if not sale_order:
                    partner = request.env['res.partner'].sudo().create({
                        'name': 'Chatbot Prueba',
                        'vat': '1101152001121',
                        'email': '',
                        'street': '',
                        'phone': '0939098358',
                        'mobile': '0939098358',
                    })
                    vals = {
                        'partner_id': partner.id,
                        'state': 'draft',
                        'website_id': 1,
                        'is_order_chatbot': True,
                        'x_numero_chatbot': numero,
                        'x_modo_compra': 'compra_asesor',
                        'x_channel': 'canal digital',
                        'digital_media': 'chatbot'
                    }
                    sale_order = request.env['sale.order'].sudo().create(vals)
                    orden_data["sale_order_id"] = sale_order.id
                else:
                    sale_order = request.env['sale.order'].sudo().browse(orden_data["sale_order_id"])
                    sale_order.sudo().write({
                        'x_numero_chatbot': numero,
                    })
                AsesorMovilFlow.procesar_cotizacion_movil(numero)

                return

            # Opciones de menú dinámicas
            opciones_menu = {
                # "cotizar-receta": AsesorFlow.procesar_cotizacion,
                "trabaja-con-nosotros": WorkPlace_Flow.plaza_trabajo,
                "promociones": BuyProductFlow.start_flow
            }
            if body in opciones_menu:
                opciones_menu[body](numero)
                return

            # Pago e envío
            if body == "ir_a_pagar":
                InvoiceFlow.manejar_envio(numero)
                return

            # Mapas de envíos y pagos
            envios_map = {"envio_domicilio": "Domicilio", "envio_local": "Retiro local"}
            pagos_map = {"pago_tarjeta": "Tarjeta", "pago_efectivo": "Efectivo", "pago_transferencia": "Transferencia",
                         # "pago_codigo":"Ahorita!/Deuna!"
                         "pago_codigo": "Ahorita!",
                         # "pago_codigo": "Ahorita!",
                         "pago_codigo_deuna": "Deuna!"
                         }

            # Selección de ciudad
            if body in cls.ciudades_map():
                ciudad = cls.ciudades_map()[body]
                cls.enviar_datos_sucursal(numero, body)
                InvoiceFlow.update_invoice_field(numero, "ciudad_retiro", ciudad['nombre'])
                InvoiceFlow.solicitar_ced_ruc(numero)
                return

            # Selección de tipo de envío
            if body in envios_map:
                tipo_envio = envios_map[body]
                InvoiceFlow.update_sale_order_field_by_number(numero, "x_tipo_entrega", tipo_envio)
                InvoiceFlow.update_invoice_field(numero, "tipo_envio", tipo_envio)
                InvoiceFlow.manejar_pago(numero)
                return

            # Selección de tipo de pago
            if body in pagos_map:
                tipo_pago = pagos_map[body]
                InvoiceFlow.update_sale_order_field_by_number(numero, "x_tipo_pago", tipo_pago)
                InvoiceFlow.update_invoice_field(numero, "tipo_pago", tipo_pago)
                MetaAPi.enviar_mensaje_texto(numero, f"Has seleccionado *{tipo_pago}* como método de pago.")

                orden_data = {}
                if session.orden:
                    try:
                        orden_data = json.loads(session.orden)
                    except Exception:
                        _logger.warning("Error parsing session orden for %s", numero)

                tipo_envio = orden_data.get("tipo_envio")
                if tipo_envio == "Retiro local":
                    if tipo_pago in ["Transferencia", "Tarjeta", "Ahorita!", "Deuna!","Efectivo"]:
                        MetaAPi.mostrar_ciudades_disponibles(numero)
                        user_session.update_session(numero, state="manejar_local_ciudad")
                    else:
                        cls.enviar_datos_sucursal(numero, "cuxibamba-loja")
                        InvoiceFlow.solicitar_ced_ruc(numero)
                elif tipo_envio == "Domicilio":
                    InvoiceFlow.solicitar_ced_ruc(numero)
                return

            # Confirmar o cancelar compra
            if body == "confirmar_compra":
                InvoiceFlow.handle_pay(numero)
                return

            if body == "cancelar_compra":
                user_session.update_session(numero, state="salir")
                order_data = json.loads(session.orden) if session.orden else {}
                sale_order_id = order_data.get("sale_order_id", 0)
                sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
                sale_order.sudo().action_cancel()
                session.sudo().write({'orden': ''})
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message(
                    'cancelar_compra') or "❌ Has cancelado tu compra. ¡Gracias por visitarnos! 👋"
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

        except Exception as e:
            _logger.exception("Error al manejar respuesta interactiva para %s", numero)
            try:
                error_msg = request.env['whatsapp_messages_user'].sudo().get_message(
                    'error_general') or "Lo siento, ha ocurrido un error interno."
                MetaAPi.enviar_mensaje_texto(numero, error_msg)
            except Exception:
                pass

    @classmethod
    def enviar_datos_sucursal(cls, numero, ciudad_id):
        """Envía la información de la sucursal seleccionada."""
        try:
            ciudad_info = cls.ciudades_map().get(ciudad_id)
            if ciudad_info:
                MetaAPi.enviar_mensaje_texto(
                    numero,
                    f"Puedes retirar tu compra en la siguiente sucursal:\n"
                    f"📍 *{ciudad_info['nombre']}*\n"
                    f"Dirección: {ciudad_info['direccion']}\n"
                    f"🔗 Indicaciones aquí: {ciudad_info['mapa']}"
                )
        except Exception as e:
            _logger.exception("Error al enviar datos de sucursal para %s", numero)
            try:
                error_msg = request.env['whatsapp_messages_user'].sudo().get_message(
                    'error_general') or "Lo siento, ha ocurrido un error al enviar la información de la sucursal."
                MetaAPi.enviar_mensaje_texto(numero, error_msg)
            except Exception:
                pass

    @staticmethod
    def ciudades_map():
        """Mapa de ciudades y sus detalles."""
        return {
            "cuxibamba-loja": {
                "nombre": "Farmacias Cuxibamba Loja",
                "direccion": "18 de Noviembre Y Azuay esquina",
                "mapa": "https://maps.app.goo.gl/KJ4UiCVSFxeQjpjB7"
            },
            "cuxibamba-riobamba": {
                "nombre": "Farmacias Cuxibamba Riobamba",
                "direccion": "Calle Guayaquil y Colón esquina",
                "mapa": "https://maps.app.goo.gl/KJ4UiCVSFxeQjpjB7"
            },
            "cuxibamba-ambato": {
                "nombre": "Farmacias Cuxibamba Ambato",
                "direccion": "Av. Cevallos y Martínez",
                "mapa": "https://maps.app.goo.gl/KJ4UiCVSFxeQjpjB7"
            }
        }

    @staticmethod
    def handle_order_by_asesor(cls, number, order_id):
        chatbot_session = request.env['whatsapp.chatbot'].sudo().search([('number', '=', number)], limit=1)

        if chatbot_session:
            orden_data = json.loads(chatbot_session.orden or "{}")
            sale_order_id = orden_data.get("sale_order_id")

            if sale_order_id:
                sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
                sale_order.write({'x_channel': 'canal digital'})
                sale_order.write({'x_numero_chatbot': number})
                sale_order.write({'x_modo_compra': 'compra_asesor'})
                sale_order.write({'digital_media': 'chatbot'})
                sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
                if sale_order.exists():
                    InvoiceFlow.manejar_envio(number)
                    return
            else:
                _logger.error(f"Sale Order ID no encontrado en la sesión para el número {number}")
                return

        _logger.error(f"Session no encontrada para el número {number}")
        return
