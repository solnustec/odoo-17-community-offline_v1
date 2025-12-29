from __future__ import annotations
import base64
import time
from odoo.http import request
from shapely.geometry import Point, shape

from .dutyPharmacy_flow import DutyPharmacy
from .getBranch import GetBranch, obtener_provincia_por_coordenadas
from .getDelivery import GetDelivery
from .meta_api import MetaAPi
import json
from collections import defaultdict
import re
from odoo.tools import float_is_zero
from .saveOdoo import SaveOdoo
from ..services.paymentez.paymentez import create_payment_link
from ..utils.user_session import UserSession
import requests
import logging
import os
import unicodedata

_logger = logging.getLogger(__name__)


class InvoiceFlow:
    @classmethod
    def update_invoice_field(cls, numero, field, value):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        orden_data = {}
        if session.orden:
            try:
                orden_data = json.loads(session.orden)
            except Exception:
                orden_data = {}
        orden_data[field] = value
        user_session.update_session(numero, orden=json.dumps(orden_data))

    @classmethod
    def update_sale_order_field_by_number(cls, numero, field_name, field_value):
        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)

            if not session or not session.orden:
                _logger.error(f"Session not found or order not available for numero {numero}")
                return False

            # Obtener los datos de la orden
            orden_data = json.loads(session.orden)
            sale_order_id = orden_data.get("sale_order_id")

            if not sale_order_id:
                _logger.error(f"No sale_order_id found in session for numero {numero}")
                return False

            # Buscar la venta usando el sale_order_id
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)

            if not sale_order.exists():
                _logger.error(f"Sale Order {sale_order_id} not found.")
                return False

            # Actualizar el campo en el sale.order
            sale_order.write({field_name: field_value})

            return True

        except Exception as e:
            _logger.error(f"Error updating Sale Order {sale_order_id}: {str(e)}")
            return False

    @classmethod
    def get_sale_order_field_by_number(cls, numero, field_name):
        try:
            # Obtener la sesión asociada al número de WhatsApp
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)

            if not session or not session.orden:
                _logger.error(f"Session not found or order not available for numero {numero}")
                return None

            # Obtener los datos de la orden
            orden_data = json.loads(session.orden)
            sale_order_id = orden_data.get("sale_order_id")

            if not sale_order_id:
                _logger.error(f"No sale_order_id found in session for numero {numero}")
                return None

            # Buscar el sale.order usando el sale_order_id
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)

            if not sale_order.exists():
                _logger.error(f"Sale Order {sale_order_id} not found.")
                return None

            # Verificar si el campo existe en el modelo sale.order
            if field_name not in sale_order._fields:
                _logger.error(f"Field {field_name} does not exist in sale.order.")
                return None

            # Obtener el valor del campo y devolverlo
            return getattr(sale_order, field_name, None)

        except Exception as e:
            _logger.error(f"Error fetching field {field_name} for Sale Order {sale_order_id}: {str(e)}")
            return None

    @classmethod
    def get_order_id(cls, numero):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        if session and session.orden:
            try:
                orden_data = json.loads(session.orden)
                return orden_data.get("sale_order_id")
            except Exception:
                return None
        return None

    @classmethod
    def solicitar_ced_ruc(cls, numero):
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_cedula_ruc')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="solicitar_cedula_ruc")
        return

    @classmethod
    def manejar_cedula_ruc(cls, numero, mensaje_texto):
        if not mensaje_texto.isdigit() or len(mensaje_texto) not in [10, 13]:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('cedula_ruc_invalido')
            MetaAPi.enviar_mensaje_texto(
                numero,
                mensaje
            )
            return

        tipo_documento = "Cédula" if len(mensaje_texto) == 10 else "RUC"
        cls.update_invoice_field(numero, "tipo_documento", tipo_documento)
        cls.update_invoice_field(numero, "documento", mensaje_texto)

        partner = request.env['res.partner'].sudo().search(
            [('vat', '=', mensaje_texto)], limit=1
        )

        if partner:
            cls.update_invoice_field(numero, "nombres_completo", partner.name)
            direccion = f"{partner.street or ''} {partner.street2 or ''}".strip()
            cls.update_invoice_field(numero, "direccion_factura", direccion)
            cls.update_invoice_field(numero, "ciudad_factura", partner.city)
            cls.update_invoice_field(numero, "email", partner.email)
            mensaje_asociado = f"Los datos de facturación son: *{partner.name}*"
            MetaAPi.enviar_mensaje_texto(numero, mensaje_asociado)
            UserSession(request.env).update_session(numero, state="confirmar_datos_factura")
            MetaAPi.confirmar_datos_factura(numero)
        else:
            cls.solicitar_nombres(numero)
        return

    @classmethod
    def solicitar_nombres(cls, numero):
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_nombres')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="solicitar_nombres")
        return

    @classmethod
    def manejar_nombre(cls, numero, mensaje_texto):
        nombre_limpio = mensaje_texto.strip()

        if not nombre_limpio:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('nombre_vacio')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            cls.solicitar_nombres(numero)
            return

        if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$", nombre_limpio):
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('nombre_invalido')
            MetaAPi.enviar_mensaje_texto(numero,
                                         f"Dato incorrecto.\n"
                                         f"_Ejemplo: María José Pérez_")
            cls.solicitar_nombres(numero)
            return

        cls.update_invoice_field(numero, "nombres_completo", nombre_limpio)

        # Mostrar botones de confirmación antes de pasar al email
        UserSession(request.env).update_session(numero, state="confirmar_nombre")
        MetaAPi.confirmar_nombre_botones(numero, nombre_limpio)
        return

    @classmethod
    def manejar_confirmacion_nombre(cls, numero, accion):
        """Maneja la respuesta de confirmación/modificación del nombre"""
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)

        if accion == "confirmar_nombre":
            # Si confirma, proceder a solicitar email
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_email_nuevo')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            user_session.update_session(numero, state="solicitar_email")
        elif accion == "modificar_nombre":
            # Si desea modificar, volver a solicitar el nombre
            user_session.update_session(numero, state="confirmar_nombre")
            cls.solicitar_nombres(numero)
        return

    @classmethod
    def manejar_email(cls, numero, mensaje_texto):
        if "@" not in mensaje_texto or "." not in mensaje_texto:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('email_invalido')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            return
        cls.update_invoice_field(numero, "email", mensaje_texto.strip())
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_direccion')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="solicitar_direccion")
        return

    @classmethod
    def manejar_direccion(cls, numero, mensaje_texto):
        cls.update_invoice_field(numero, "direccion_factura", mensaje_texto.strip())
        UserSession(request.env).update_session(numero, state="tipo_envio")
        cls.manejar_orden(numero)
        return

    @classmethod
    def manejar_envio(cls, numero):
        UserSession(request.env).update_session(numero, state="tipo_envio")
        MetaAPi.botones_tipo_envio(numero)
        return

    @classmethod
    def manejar_pago(cls, numero, mensaje=None):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)

        orden_data = {}
        if session.orden:
            try:
                orden_data = json.loads(session.orden)
            except Exception:
                orden_data = {}

        tipo_envio = orden_data.get("tipo_envio", "")
        user_session.update_session(numero, state="tipo_pago")
        total = 0.0

        if total < 1:
            if tipo_envio == "domicilio":
                return MetaAPi.botones_tipo_pago(numero)
            elif tipo_envio == "retiro local":
                return MetaAPi.botones_tipo_pago_tarjeta(numero)

        if total < 200:
            return MetaAPi.botones_tipo_pago(numero)

    @classmethod
    def validar_email(cls, email):
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @classmethod
    def edit_order(cls, number):
        UserSession(request.env).update_session(number, state="editar_orden")
        MetaAPi.edit_order(number)
        return

    @classmethod
    def enviar_resumen_producto(cls, number):
        # Obtener la orden de la sesión del usuario
        user_session = UserSession(request.env)
        session = user_session.get_session(number)
        order_data = json.loads(session.orden or "{}")
        sale_order_id = order_data.get("sale_order_id")

        if not sale_order_id:
            MetaAPi.enviar_mensaje_texto(number, "No se encontró la orden.")
            return

        # Obtener la orden
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)

        productos_base = sale_order.order_line.filtered(
            lambda l: l.product_id and not l.is_delivery and l.discount != 100)

        productos_para_eliminar = []

        for line in productos_base:
            productos_para_eliminar.append(line)

            if line.discount > 0:
                promo_line = sale_order.order_line.filtered(
                    lambda l: l.product_id == line.product_id and l.discount == 100
                )
                productos_para_eliminar.extend(promo_line)

        if not productos_para_eliminar:
            MetaAPi.enviar_mensaje_texto(number, "No tienes productos base para eliminar.")
            return

        mensaje = "Estos son los productos de tu orden:\n\n"
        for idx, line in enumerate(productos_para_eliminar, start=1):
            product = line.product_id
            cantidad = line.product_uom_qty

            mensaje += f"{idx}. {product.name} - {cantidad} unidades\n"

        mensaje += "\n\nPor favor, ingresa el número del producto que deseas eliminar."

        user_session.update_session(number, state="eliminar_producto_seleccionado")
        MetaAPi.enviar_mensaje_texto(number, mensaje)

        return

    @classmethod
    def manejar_eliminacion_producto(cls, number, selection_text):

        try:
            option = int(selection_text)
        except ValueError:
            MetaAPi.enviar_mensaje_texto(number, "Por favor, ingresa un número válido.")
            return

        user_session = UserSession(request.env)
        session = user_session.get_session(number)
        order_data = json.loads(session.orden or "{}")
        sale_order_id = order_data.get("sale_order_id")

        if not sale_order_id:
            MetaAPi.enviar_mensaje_texto(number, "No se encontró la orden.")
            return

        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            MetaAPi.enviar_mensaje_texto(number, "Orden no válida.")
            return

        base_lines = sale_order.order_line.filtered(
            lambda l: l.product_id and not l.is_delivery and not l.display_type and l.discount != 100
        )

        if not base_lines:
            MetaAPi.enviar_mensaje_texto(number, "No tienes productos base para eliminar.")
            return

        if option < 1 or option > len(base_lines):
            MetaAPi.enviar_mensaje_texto(number, "Número de producto inválido. Por favor, intenta nuevamente.")
            return

        base_line = base_lines[option - 1]

        promo_lines = request.env['sale.order.line'].sudo().search([
            ('order_id', '=', sale_order.id),
            ('product_id', '=', base_line.product_id.id),
            ('is_delivery', '=', False),
            ('display_type', '=', False),
            ('id', '!=', base_line.id),
            ('discount', '!=', 0),
        ])

        ids_to_delete = promo_lines.ids + [base_line.id]

        detalles = []
        detalles.append(f"• {int(base_line.product_uom_qty)}× {base_line.product_id.name}")
        # for p in promo_lines:
        #     desc = f"{int(p.discount)}%" if p.discount else "promo"
        #     detalles.append(f"• {int(p.product_uom_qty)}× {p.product_id.name} (promoción {desc})")

        mensaje_prev = "Se eliminará el siguiente producto:\n\n" + "\n".join(detalles)
        MetaAPi.enviar_mensaje_texto(number, mensaje_prev)

        try:
            request.env['sale.order.line'].sudo().browse(ids_to_delete).unlink()
            request.env.cr.commit()
        except Exception as e:
            MetaAPi.enviar_mensaje_texto(number, "Ocurrió un error eliminando el producto. Intenta nuevamente.")
            return

        MetaAPi.enviar_mensaje_texto(number, "Listo ✅ Se eliminó el producto.")
        user_session.update_session(number, state="editar_orden")

        # 🔎 Recalcular las líneas de productos base
        base_lines_restantes = sale_order.order_line.filtered(
            lambda l: l.product_id and not l.is_delivery and not l.display_type and l.discount != 100
        )

        if not base_lines_restantes:
            from .buyProduct_flow import BuyProductFlow
            BuyProductFlow.start_flow(number)
        else:
            try:
                MetaAPi.enviar_mensaje_con_botones(number)
            except Exception:
                MetaAPi.enviar_mensaje_con_botones(
                    number,
                    "¿Qué deseas hacer ahora?\n\nEditar orden\nProceder al pago\nSalir"
                )

    @classmethod
    def solicitar_email(cls, numero):
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('recibir_email')
        MetaAPi.enviar_mensaje_texto(
            numero,
            mensaje
        )
        UserSession(request.env).update_session(numero, state="recibir_email")
        # MetaAPi.confirmar_datos_email(numero)
        # UserSession(request.env).update_session(numero, state="recibir_email")

    @classmethod
    def recibir_email(cls, numero, mensaje_texto):
        if not cls.validar_email(mensaje_texto):
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('email_invalido')
            MetaAPi.enviar_mensaje_texto(
                numero,
                mensaje
            )
            return

        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)
            order_data = json.loads(session.orden) if session.orden else {}
            cedula = order_data.get("documento", "")
            partner = request.env['res.partner'].sudo().search(
                [('vat', '=', cedula)], limit=1
            )

            if partner:
                partner.sudo().write({"email": mensaje_texto, 'country_id': 63})
            cls.update_invoice_field(numero, "email", mensaje_texto)
            MetaAPi.enviar_mensaje_texto(
                numero,
                f"Email *{mensaje_texto}* registrado correctamente"
            )
            UserSession(request.env).update_session(numero, state="manejar_datos_factura")
            cls.manejar_orden(numero)

        except Exception as e:
            _logger.error(f"Error al guardar el email para el número {numero}: {str(e)}")
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_email')
            MetaAPi.enviar_mensaje_texto(
                numero,
                mensaje
            )

    @classmethod
    def manejar_orden(cls, numero):
        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)
            if not session:
                _logger.error("No se pudo obtener la sesión del usuario")
                return
            order_data = {}
            try:
                order_data = json.loads(session.orden) if session.orden else {}
            except json.JSONDecodeError as e:
                _logger.error(f"Error al decodificar JSON de la orden: {str(e)}")
                order_data = {}

            sale_order_id = order_data.get("sale_order_id", 0)
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
            if not sale_order.exists():
                _logger.error(f"No se encontró la orden de venta con ID: {sale_order_id}")
                return

            doc = order_data.get("documento", "")
            email = order_data.get("email", "")

            if session.state != "manejar_datos_factura":
                if not email or not cls.validar_email(email):
                    mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_email')
                    MetaAPi.enviar_mensaje_texto(numero, mensaje)
                    MetaAPi.confirmar_datos_email(numero)
                    return

            UserSession(request.env).update_session(numero, state="manejar_orden")

            orden_data = {}
            if session.orden:
                try:
                    orden_data = json.loads(session.orden)
                except Exception as e:
                    _logger.error(f"Error al cargar datos adicionales: {str(e)}")
                    UserSession(request.env).update_session(numero, state="regresar_menu")
                    MetaAPi.enviar_mensaje_con_botones_salida(numero)
                    orden_data = {}

            partner = request.env['res.partner'].sudo().search([('vat', '=', doc)], limit=1)

            tipo_documento = order_data.get("tipo_documento", "").strip().upper()  # RUC, CÉDULA, PASAPORTE

            tipo_id = request.env['l10n_latam.identification.type'].sudo().search([
                ('name', 'ilike', tipo_documento)
            ], limit=1)

            if not partner:
                try:
                    nombres_completo = order_data.get("nombres_completo", "Cliente {}".format(doc))
                    partner_vals = {
                        'name': nombres_completo,
                        'l10n_latam_identification_type_id': tipo_id.id if tipo_id else False,
                        'vat': doc,
                        'email': email,
                        'street': order_data.get("direccion_factura", ""),
                        'city': order_data.get("ciudad_factura", ""),
                        'country_id': 63
                    }
                    partner = request.env['res.partner'].sudo().create(partner_vals)
                except Exception as e:
                    _logger.error("Error al crear partner: %s", str(e))
                    raise

            try:
                sale_order.write({
                    'partner_id': partner.id,
                    'partner_invoice_id': partner.id,
                    'partner_shipping_id': partner.id,
                })
            except Exception as e:
                _logger.error(f"Error al actualizar orden: {str(e)}")
                raise

            tipo_envio = orden_data.get("tipo_envio")
            if tipo_envio == "Retiro local":
                cls.enviar_resumen_orden(numero, sale_order_id)
            else:
                UserSession(request.env).update_session(numero, state="solicitar_provincia")
                cls.solicitar_ubicacion_envio(numero)

        except Exception as e:
            _logger.error(f"Error inesperado en manejar_orden: {str(e)}")
            raise

    @classmethod
    def solicitar_ubicacion_envio(cls, numero):
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('solicitar_ubicacion_envio')
        try:
            UserSession(request.env).update_session(numero, state="solicitar_ubicacion_envio")
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            return
        except Exception as e:
            print(f"Error en solicitar_ubicacion: {str(e)}")
            mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message('branch_general_error')
            MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
            return False

    @classmethod
    def manejar_direccion_domicilio_texto(cls, numero, direccion_texto):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        cls.update_invoice_field(numero, 'direccion_texto', direccion_texto)
        user_session.update_session(numero, state="solicitar_ubicacion_envio")
        return

    @classmethod
    def manejar_direccion_domicilio_ubi(cls, numero, latitude, longitude):
        latitude = DutyPharmacy.safe_float(latitude)
        longitude = DutyPharmacy.safe_float(longitude)
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        info_provincia = cls.obtener_info_direccion(latitude, longitude)
        info_nominatim = cls.obtener_direccion_nominatim(latitude, longitude)
        provincia = info_provincia.get("provincia")
        if not provincia or not provincia.strip():
            provincia = obtener_provincia_por_coordenadas(latitude, longitude)

        direccion_completa = {
            "provincia": provincia,
            "ciudad": info_nominatim.get("ciudad", ""),
            "calle_principal": info_nominatim.get("calle_principal", ""),
            "calle_secundaria": info_nominatim.get("calle_secundaria", ""),
            "numero_casa": info_nominatim.get("numero_casa", "")
        }

        google_maps_link = GetBranch.generate_google_maps_link(latitude, longitude)
        cls.update_invoice_field(numero, 'link_direccion_gps', google_maps_link)
        order_data = json.loads(session.orden or "{}")
        sale_order_id = order_data.get("sale_order_id", 0)
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if sale_order:
            sale_order.write({'ubication_url': google_maps_link})
        else:
            _logger.warning(f"No se encontró sale.order para número {numero}")

        cls.update_invoice_field(numero, 'direccion_texto_gps', direccion_completa)
        provincia = direccion_completa.get("provincia", "")
        sale_order.sudo().write({
            'x_direccion_entrega': direccion_completa
        })
        cls.manejar_precio_provincia(numero, provincia, latitude, longitude)
        return

    @classmethod
    def obtener_info_direccion(cls, lat, lon):
        ruta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_json = os.path.join(ruta_actual, '..', 'static', 'src', 'geo', 'ec.json')
        try:
            with open(ruta_json, 'r', encoding='utf-8') as archivo:
                geo_data = json.load(archivo)
        except Exception as e:
            print("Error al leer el archivo JSON:", e)
            _logger.error("Error al leer el archivo JSON: %s", e)
            return {}
        punto = Point(lon, lat)
        for feature in geo_data.get('features', []):
            try:
                geometria = shape(feature.get('geometry'))
            except Exception as e:
                _logger.error("Error procesando la geometría: %s", e)
                continue
            if geometria.contains(punto):
                props = feature.get('properties', {})
                return {
                    "provincia": props.get("name", "")
                }
        return {}

    @classmethod
    def obtener_direccion_nominatim(cls, lat, lon):
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1
        }
        try:
            headers = {'User-Agent': 'odoo-17-module'}
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                return {
                    "calle_principal": address.get("road", ""),
                    "calle_secundaria": address.get("neighbourhood", ""),
                    "numero_casa": address.get("house_number", ""),
                    "ciudad": address.get("city", address.get("town", address.get("village", "")))
                }
            else:
                _logger.error("Error en consulta Nominatim: código %s", response.status_code)
        except Exception as ex:
            _logger.error("Excepción en llamada a Nominatim: %s", ex)
        return {
            "calle_principal": "",
            "calle_secundaria": "",
            "numero_casa": "",
            "ciudad": ""
        }


    @classmethod
    def manejar_precio_provincia(cls, numero, provincia, latitude, longitude):
        def eliminar_tildes(texto):
            # Normalizar el texto a forma NFKD y eliminar los diacríticos
            texto_normalizado = unicodedata.normalize('NFKD', texto)
            texto_sin_tildes = ''.join(c for c in texto_normalizado if not unicodedata.combining(c))
            return texto_sin_tildes.lower().strip()  # Convertir a minúsculas y eliminar espacios

        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        order_data = json.loads(session.orden or "{}")
        so_id = order_data.get("sale_order_id")
        direccion = order_data.get("direccion_texto_gps") or {}
        province_name = eliminar_tildes(direccion.get("provincia", ""))  # Limpiar tildes y pasar a minúsculas
        ciudad_name = direccion.get("ciudad", "").lower()
        google_maps_link = order_data.get("link_direccion_gps")
        cantones_loja = {
            "catamayo", "calvas", "celica", "chaguarpamba",
            "espíndola", "gonzanamá", "macará", "olmedo", "paltas",
            "pindal", "puyango", "quilanga", "saraguro",
            "sozoranga", "zapotillo","cariamanga"
        }

        shipping_methods = GetDelivery.get_all_shipping_methods()
        sale_order = request.env['sale.order'].sudo().browse(so_id)

        def agregar_linea_envio(sale_order, product_id, cost, nombre, is_delivery=True):
            existing = sale_order.order_line.filtered(lambda l: l.product_id.id == product_id or l.is_delivery)
            if existing:
                existing.write({
                    'price_unit': cost,
                    'product_uom_qty': 1,
                    'name': nombre,
                    'is_delivery': is_delivery
                })
            else:
                request.env['sale.order.line'].sudo().create({
                    'order_id': sale_order.id,
                    'product_id': product_id,
                    'product_uom_qty': 1,
                    'price_unit': cost,
                    'name': nombre,
                    'is_delivery': is_delivery
                })

        if province_name == "loja" and ciudad_name in cantones_loja:
            carrier_search = "envios a cantones de loja"
            user_session.update_session(numero, state="solicitar_provincia")

            for method in shipping_methods:
                if carrier_search.lower() in method["carrier_name"].lower():
                    InvoiceFlow.update_invoice_field(numero, 'precio_envio', method)
                    session = user_session.get_session(numero)
                    order_data = json.loads(session.orden or "{}")
                    ship = order_data.get("precio_envio", {})
                    product_id = ship.get("product_id")
                    cost = ship.get("fixed_price")

                    if product_id and cost is not None:
                        agregar_linea_envio(sale_order, product_id, cost, f"Envío: {ship.get('carrier_name', '')}")

                    sale_order.write({'x_direccion_entrega': direccion})
                    SaveOdoo.save_shipping_price_log(
                        sale_order.id,
                        numero,
                        google_maps_link,
                        province_name,
                        ciudad_name,
                        direccion.get("calle_principal", ""),
                        ship.get("fixed_price", 0.0),
                        0.0
                    )
                    InvoiceFlow.enviar_resumen_orden(numero, so_id)
                    return
        elif province_name == "loja" and ciudad_name == "loja":
            shipping_product = request.env['product.product'].sudo().search([
                ('default_code', '=', 'ENVIOSCHATBOT'),
                ('detailed_type', '=', 'service')
            ], limit=1)

            if not shipping_product.exists():
                tax_0_415B = request.env['account.tax'].sudo().search([
                    ('name', '=', 'IVA 0% (415 B)')
                ], limit=1)

                shipping_product = request.env['product.product'].sudo().create({
                    'name': 'Envios Chatbot',
                    'default_code': 'ENVIOSCHATBOT',
                    'detailed_type': 'service',
                    'list_price': 0.40,
                    'id_database_old': 28262,
                    'taxes_id': [(6, 0, [10])],
                    'is_delivery_product': True,
                })

                if tax_0_415B:
                    shipping_product.sudo().write({
                        'taxes_id': [(6, 0, [tax_0_415B.id])]
                    })

            ORIGEN_LAT, ORIGEN_LON = -4.000426, -79.20384
            distancia_km = GetDelivery.calculate_distance([ORIGEN_LAT, ORIGEN_LON, latitude, longitude])
            distancia_metros = distancia_km * 1000

            # Parámetros
            costo_minimo_bajo = 1.75
            costo_km = shipping_product.list_price
            fraccion_metros = 1000 / 8
            costo_por_fraccion = 0.05

            def calcular_costo_por_fracciones(metros_sobrantes):
                fraccion = int(metros_sobrantes // fraccion_metros)
                return min(fraccion * costo_por_fraccion, 0.40)

            if distancia_metros <= 3000:
                precio_envio = costo_minimo_bajo
            else:
                precio_envio = costo_minimo_bajo
                distancia_restante = distancia_metros - 3000

                km_adicionales = int(distancia_restante // 1000)
                precio_envio += km_adicionales * costo_km

                metros_sobrantes = distancia_restante % 1000
                precio_envio += calcular_costo_por_fracciones(metros_sobrantes)

            precio_envio = round(precio_envio, 2)

            cls.update_invoice_field(numero, 'precio_envio', precio_envio)
            cls.update_invoice_field(numero, 'distancia_km', distancia_km)
            cls.update_invoice_field(numero, 'envio_product_id', shipping_product.id)

            if shipping_product:
                agregar_linea_envio(
                    sale_order, shipping_product.id, precio_envio,
                    'Costo de envío calculado por distancia'
                )
            SaveOdoo.save_shipping_price_log(
                sale_order.id,
                numero,
                google_maps_link,
                province_name,
                ciudad_name,
                direccion.get("calle_principal", ""),
                precio_envio,
                distancia_km
            )
            InvoiceFlow.enviar_resumen_orden(numero, so_id)
            return
        else:
            for method in shipping_methods:
                if province_name in method["carrier_name"].lower():
                    InvoiceFlow.update_invoice_field(numero, 'precio_envio', method)
                    session = user_session.get_session(numero)
                    order_data = json.loads(session.orden or "{}")
                    ship = order_data.get("precio_envio", {})
                    product_id = ship.get("product_id")
                    cost = ship.get("fixed_price")

                    if product_id and cost is not None:
                        agregar_linea_envio(sale_order, product_id, cost, f"Envío: {ship.get('carrier_name', '')}")

                    sale_order.write({'x_direccion_entrega': direccion})
                    SaveOdoo.save_shipping_price_log(
                        sale_order.id,
                        numero,
                        google_maps_link,
                        province_name,
                        ciudad_name,
                        direccion.get("calle_principal", ""),
                        ship.get("fixed_price", 0.0),
                        0.0
                    )
                    InvoiceFlow.enviar_resumen_orden(numero, so_id)
                    return


    @classmethod
    def enviar_resumen_orden(cls, numero, sale_order_id):
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        chatbot_session = request.env['whatsapp.chatbot'].sudo().search([('number', '=', numero)], limit=1)

        # Whatsapp model data
        try:
            orden_data = json.loads(chatbot_session.orden) if chatbot_session.orden else {}
        except json.JSONDecodeError:
            _logger.error("Error decoding 'orden' JSON data.")
            orden_data = {}
        if not sale_order.exists():
            MetaAPi.enviar_mensaje_texto(numero, "⚠️ Orden no encontrada.")
            return

        partner = sale_order.partner_id

        tipo_envio = sale_order.x_tipo_entrega
        tipo_pago = sale_order.x_tipo_pago
        direccion_factura = partner.street or ""
        documento = partner.vat or ""
        tipo_documento = "Cédula" if len(documento) == 10 else "RUC"

        # Construir mensaje
        mensaje = (
            f"*Resumen de tu Orden*\n\n"
            f"*Cliente:* {partner.name}\n"
            f"*Documento:* {tipo_documento} {documento}\n"
            f"*Email:* {partner.email or '—'}\n"
            f"*Dirección Facturación:* {direccion_factura}\n\n"
            f"*Método de Pago:* {tipo_pago}\n"
            f"*Tipo de Envío:* {tipo_envio}\n"
        )

        if tipo_envio.lower() == "domicilio":
            link = ""
            if chatbot_session and chatbot_session.orden:
                try:
                    link = orden_data.get('link_direccion_gps', '')
                except Exception as e:
                    _logger.error(f"Error leyendo link_direccion_gps del chatbot: {str(e)}")

            if link:
                mensaje += f"*Dirección de Entrega:* {link}\n"

        mensaje += "\n*Productos:*\n"
        descuentos_totales = 0.0

        tipo_compra = sale_order.x_modo_compra or ''

        if tipo_compra == "compra_auto":
            for line in sale_order.order_line.filtered(lambda l: l.product_id and not l.is_delivery):
                tmpl = line.product_id.product_tmpl_id
                subtotal_linea = tmpl.price_with_tax or 0.0
                subtotal_linea_desc = tmpl.price_with_discount or 0.0
                descuento = line.discount or 0
                if line.price_subtotal > 0:
                    if descuento > 0 and descuento < 100:
                        mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name}: ~${subtotal_linea:.2f}~ → ${subtotal_linea_desc:.2f}\n"
                    else:
                        mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name}: ${subtotal_linea:.2f}\n"
                if descuento == 100:
                    mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name} _(Producto Gratis)_\n"
                else:
                    descuentos_totales += line.price_subtotal
        elif tipo_compra == "compra_asesor":
            lines = sale_order.order_line.filtered(
                lambda l: not getattr(l, 'is_delivery', False) and not l.display_type
            )
            currency = sale_order.currency_id
            prec = currency.rounding

            def keyify(s):
                s = re.sub(r'\[.*?\]\s*', '', s or '')
                return ' '.join(s.lower().strip().split())

            base_lines, promo_lines = [], []
            for l in lines:
                is_reward = (
                        getattr(l, 'is_reward_line', False)
                        or float_is_zero(l.price_total, precision_rounding=prec)
                        or float_is_zero(l.price_unit, precision_rounding=prec)
                        or l.price_unit < 0.0
                        or l.price_total < 0.0
                )
                (promo_lines if is_reward else base_lines).append(l)

            base_index = []
            for b in base_lines:
                keys = {
                    keyify(b.product_id.name),
                    keyify(b.product_id.display_name or ''),
                    keyify((b.name or '').splitlines()[0]),
                }
                base_index.append((b, {k for k in keys if k}))

            def find_base_for(text):
                t = keyify(text)
                best = None
                for b, keys in base_index:
                    for k in keys:
                        if k and (k in t or t in k):
                            if not best or len(k) > best[0]:
                                best = (len(k), b)
                return best[1] if best else None

            discounts_total = defaultdict(float)
            freebies = defaultdict(list)

            for p in promo_lines:
                name = p.name or ''
                nl = name.lower()
                target = name
                if 'producto gratis -' in nl:
                    target = name.split('-', 1)[-1].strip()
                elif ' en ' in nl:  # "22% en NOMBRE"
                    target = name.split(' en ', 1)[-1].strip()

                base = find_base_for(target)

                is_free = (
                        float_is_zero(p.price_total, precision_rounding=prec)
                        or float_is_zero(p.price_unit, precision_rounding=prec)
                        or (p.discount == 100)
                )

                if is_free:
                    nm = (p.product_id.name or target).strip()
                    (freebies[base.id] if base else freebies[0]).append((int(p.product_uom_qty), nm))
                else:
                    discount_line = discounts_total[base.id] if base else discounts_total[0]
                    discount_line += p.price_total  # negativo
                    if base:
                        discounts_total[base.id] = discount_line
                    else:
                        discounts_total[0] = discount_line


            for b in base_lines:
                base_total = b.price_total  # con IVA
                disc = discounts_total.get(b.id, 0.0)
                if not float_is_zero(disc, precision_rounding=prec):
                    nuevo_total = base_total + disc
                    mensaje += (
                        f"➡ {int(b.product_uom_qty)}x {b.product_id.name}: "
                        f"~${base_total:.2f}~ → ${nuevo_total:.2f}\n"
                    )

                else:
                    mensaje += f"➡ {int(b.product_uom_qty)}x {b.product_id.name}: ${base_total:.2f}\n"

                for qty, nm in freebies.get(b.id, []):
                    mensaje += f"➡ {qty}x {nm}\n"

            for qty, nm in freebies.get(0, []):
                mensaje += f"➡ {qty}x {nm}\n"

        envio_line = sale_order.order_line.filtered(lambda l: l.is_delivery)
        if envio_line:
            mensaje += f"\n*Precio envío:* ${envio_line.price_subtotal:.2f}"

        # subtotales
        mensaje += (
            f"\n*Subtotal:* ${sale_order.amount_untaxed:.2f}"
        )

        # Totales
        mensaje += (
            f"\n*IVA:* ${sale_order.amount_tax:.2f}\n"
            f"*Total a Pagar:* *${sale_order.amount_total:.2f}*"
        )

        # Enviar
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="confirmar_orden_factura")
        MetaAPi.botones_confirmar_compra(numero)

    @classmethod
    def handle_pay(cls, numero):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        order_data = json.loads(session.orden) if session.orden else {}
        so_id = order_data.get("sale_order_id")
        sale_order = request.env['sale.order'].sudo().browse(so_id)
        tipo_pago = sale_order.x_tipo_pago
        sale_order.action_confirm()

        if tipo_pago == "Transferencia":
            cls.procesar_pago_transferencia(numero)
        elif tipo_pago == "Efectivo":
            cls.procesar_pago_efectivo(numero)
        elif tipo_pago == "Tarjeta":
            cls.solicitar_nombres_tarjeta(numero)
        # elif tipo_pago == "Ahorita!":
        #     cls.procesar_pago_codigo(numero)
        # elif tipo_pago == "Ahorita!/Deuna!":
        #     cls.procesar_pago_codigo(numero)
        # elif tipo_pago == "Ahorita!":
        #     cls.procesar_pago_codigo(numero)
        # elif tipo_pago == "Deuna!":
        #     cls.send_message_deuna(numero)
        elif tipo_pago == "Ahorita!":
            DigitalPaymentConfig = request.env['digital.payment.config'].sudo()
            config = DigitalPaymentConfig.search([
                ('bank_name', '=', 'AHORITA BANCO DE LOJA'),
                ('enable_advanced_payments', '=', True),
            ], limit=1)
            if config:
                cls.send_message_ahorita(numero)
            else:
                cls.procesar_pago_codigo_ahorita(numero)
        elif tipo_pago == "Deuna!":
            DigitalPaymentConfig = request.env['digital.payment.config'].sudo()
            config = DigitalPaymentConfig.search([
                ('bank_name', '=', 'DEUNA BCO PICHINCHA'),
                ('enable_advanced_payments', '=', True),
            ], limit=1)
            if config:
                cls.send_message_deuna(numero)
            else:
                cls.procesar_pago_codigo(numero)
        else:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_metodo_pago')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)

    @classmethod
    def procesar_pago_transferencia(cls, numero):
        mensaje_transferencia = request.env['whatsapp_messages_user'].sudo().get_message('datos_transferencia')
        mensaje_comprobante = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_pago')

        UserSession(request.env).update_session(numero, state="confirmar_pago")
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        order_data = json.loads(session.orden or "{}")
        so_id = order_data.get("sale_order_id")
        sale_order = request.env['sale.order'].sudo().browse(so_id)
        sale_order.sudo().write({
            'x_tipo_pago': 'CHEQUE/TRANSF'
        })
        MetaAPi.enviar_mensaje_texto(numero, mensaje_transferencia)
        time.sleep(3)
        MetaAPi.enviar_mensaje_texto(numero, mensaje_comprobante)

    @classmethod
    def procesar_pago_codigo_ahorita(cls, numero):
        mensaje_transferencia = request.env['whatsapp_messages_user'].sudo().get_message('datos_pago_codigo')
        mensaje_comprobante = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_pago')

        cls.update_invoice_field(numero, "tipo_pago", "Ahorita!/Deuna!")

        image_url = "https://i.postimg.cc/rmqRCn00/CODIGO-QR-AHORITA.jpg"

        MetaAPi.enviar_mensaje_texto(numero, mensaje_transferencia)
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        order_data = json.loads(session.orden or "{}")
        so_id = order_data.get("sale_order_id")
        sale_order = request.env['sale.order'].sudo().browse(so_id)
        sale_order.sudo().write({
            'x_tipo_pago': 'CHEQUE/TRANSF'
        })
        UserSession(request.env).update_session(numero, state="confirmar_pago")
        MetaAPi.enviar_imagen_desde_url(numero, image_url)
        time.sleep(3)
        MetaAPi.enviar_mensaje_texto(numero, mensaje_comprobante)

    @classmethod
    def procesar_pago_codigo(cls, numero):
        mensaje_transferencia = request.env['whatsapp_messages_user'].sudo().get_message('datos_pago_codigo')
        mensaje_comprobante = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_pago')

        cls.update_invoice_field(numero, "tipo_pago", "Ahorita!/Deuna!")

        image_url = "https://i.postimg.cc/T1rHnZjG/CODIGOS-QR-2.jpg"

        MetaAPi.enviar_mensaje_texto(numero, mensaje_transferencia)
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        order_data = json.loads(session.orden or "{}")
        so_id = order_data.get("sale_order_id")
        sale_order = request.env['sale.order'].sudo().browse(so_id)
        sale_order.sudo().write({
            'x_tipo_pago': 'CHEQUE/TRANSF'
        })
        UserSession(request.env).update_session(numero, state="confirmar_pago")
        MetaAPi.enviar_imagen_desde_url(numero, image_url)
        time.sleep(3)
        MetaAPi.enviar_mensaje_texto(numero, mensaje_comprobante)

    @classmethod
    def send_message_deuna(cls, numero):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)

        order_data = json.loads(session.orden or "{}")
        sale_order_id = order_data.get("sale_order_id")
        if not sale_order_id:
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            return {'error': 'No se encontró la orden en la sesión.'}

        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            return {'error': 'La orden no existe.'}

        codigoPay = sale_order.x_tipo_pago

        if codigoPay != 'Deuna!':
            return {'status': 'skipped', 'message': 'Método de pago no es Deuna'}

        response_deuna = request.env['sale.order'].sudo().get_data_order(sale_order_id)

        if isinstance(response_deuna, dict) and 'error' in response_deuna:
            error_msg = f"No se pudo generar el pago: {response_deuna.get('error')}"
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            return {'error': error_msg}

        transaction_id = response_deuna.get('transactionId')
        deeplink = response_deuna.get('deeplink')
        qr = response_deuna.get('qr')

        if not transaction_id:
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            return {'error': 'No se recibió transactionId del proveedor.'}

        if not deeplink:
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            return {'error': 'No se recibió enlace de pago (deeplink).'}

        try:

            deuna_rec = request.env['deuna.post'].sudo().create({
                'order_id_name': sale_order.name,
                'transactionId': transaction_id,
                'status_payment': 'pendiente',
            })
        except Exception as e:
            return {'error': f'No se pudo registrar el pago en deuna.post: {e}'}

        sale_order.sudo().write({'x_tipo_pago': 'CHEQUE/TRANSF'})
        UserSession(request.env).update_session(numero, state="confirmar_pago")

        mensaje = f"✅ Por favor realiza tu pago aquí: {deeplink}"
        mensaje_comprobante = "Por favor envíanos una captura de pantalla del comprobante de pago."

        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        if qr:
            MetaAPi.enviar_imagen(numero, qr)
        MetaAPi.enviar_mensaje_texto(numero, mensaje_comprobante)

        return {'status': 'success', 'deeplink': deeplink, 'transactionId': transaction_id}

    @classmethod
    def send_message_ahorita(cls, numero):
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)

        try:
            order_data = json.loads(session.orden or "{}")
            sale_order_id = order_data.get("sale_order_id")
            if not sale_order_id:
                return {'status': 'error', 'message': 'Orden no encontrada en la sesión'}

            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
            if not sale_order.exists():
                return {'status': 'error', 'message': 'Orden no válida'}

            codigoPay = sale_order.x_tipo_pago
            if codigoPay != 'Ahorita!':
                return {'status': 'ignored'}

            from decimal import Decimal, ROUND_HALF_UP
            amount = Decimal(str(sale_order.amount_total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            user_id = 415472
            current_millis = int(time.time() * 1000)
            message_id = f"AHORITA-{current_millis}"
            transaction_id = f"generateByTransactionGW-{user_id}-{message_id}"

            payload = {
                "userId": user_id,
                "messageId": message_id,
                "transactionId": transaction_id,
                "deviceId": "127.0.0.1",
                "amount": str(amount),
            }

            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
            url = f"{base_url}/ahorita/generate_deeplink"
            headers = {'Content-Type': 'application/json'}

            response = requests.post(
                url, json=payload, headers=headers, timeout=30, verify=True
            )
            response.raise_for_status()

            rpc = response.json() or {}
            data = rpc.get('result', rpc) or {}
            dl = data.get('deeplink')
            deeplink = None
            deeplink_id = data.get('deeplink_id')
            qr = data.get('qr')

            if isinstance(dl, dict):
                deeplink = dl.get('deeplink') or dl.get('url')
                deeplink_id = dl.get('deeplink_id') or deeplink_id
            else:
                deeplink = dl

            if not deeplink or not deeplink_id:
                return {'status': 'error', 'message': 'Respuesta incompleta del generador de deeplink'}

            sale_order.sudo().write({'pay_ahorita_id': str(deeplink_id)})
            request.env['ahorita.post'].sudo().create({
                'order_id_name': str(sale_order_id),
                'transactionId': transaction_id,
                'deeplink': str(deeplink_id),
                'status_payment': 'pendiente',
                'data': data,
            })

            MetaAPi.enviar_mensaje_texto(
                numero,
                f"✅ Por favor realiza tu pago aquí: {deeplink}\n"
                f"O puedes escanear con la cámara de celular el siguiente código QR:"
            )
            if qr:
                MetaAPi.enviar_imagen(numero, qr)
            sale_order.sudo().write({'x_tipo_pago': 'CHEQUE/TRANSF'})

            UserSession(request.env).update_session(numero, state="confirmar_pago")
            MetaAPi.enviar_mensaje_texto(
                numero,
                "Por favor envíanos una captura de pantalla del comprobante de pago."
            )

            return {'status': 'success', 'deeplink': deeplink, 'deeplink_id': deeplink_id}

        except requests.RequestException as re:
            return {'status': 'error', 'message': str(re)}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @classmethod
    def procesar_pago_efectivo(cls, numero):
        UserSession(request.env).update_session(numero, state="confirmar_pago")
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('pago_efectivo')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)

    @classmethod
    def solicitar_nombres_tarjeta(cls, numero):
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('datos_tarjeta')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="solicitar_nombres_tarjeta")
        return

    @classmethod
    def dividir_nombre(cls, full_name: str) -> tuple[str, str]:
        parts = full_name.strip().split()
        n = len(parts)

        if n == 0:
            return "", ""
        if n == 1:
            return parts[0], ""
        if n == 2:
            return parts[0], parts[1]

        nombres = " ".join(parts[:-2])
        apellidos = " ".join(parts[-2:])
        return nombres, apellidos

    @classmethod
    def manejar_nombre_tarjeta(cls, numero, mensaje_texto):
        if not mensaje_texto or not mensaje_texto.strip():
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('nombre_vacio')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            return
        nombres, apellidos = cls.dividir_nombre(mensaje_texto)
        cls.update_invoice_field(numero, 'nombres', nombres)
        cls.update_invoice_field(numero, 'apellidos', apellidos)
        cls.procesar_pago_tarjeta(numero)
        return

    @classmethod
    def procesar_pago_tarjeta(cls, numero):
        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)
            order_data = json.loads(session.orden) if session.orden else {}
            email = order_data.get("email", "")
            documento = order_data.get("documento", "")
            nombre_tarjeta = order_data.get("nombres", "")
            apellido_tarjeta = order_data.get("apellidos", "")
            sale_order_id = order_data.get("sale_order_id", 0)
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
            if sale_order.exists():
                total_amount = sale_order.amount_total
            description_lines = [
                f"Pago por ${total_amount:.2f} USD en Farmacias Cuxibamba",
            ]

            description = " | ".join(description_lines)
            payment_data = create_payment_link(
                amount=total_amount,
                description=description,
                user_email=email,
                name=nombre_tarjeta,
                last_name=apellido_tarjeta,
                cedula=documento
            )
            if (payment_data and
                    "data" in payment_data and
                    "payment" in payment_data["data"] and
                    "payment_url" in payment_data["data"]["payment"]):
                payment_url = payment_data["data"]["payment"]["payment_url"]
                message = (
                    f"💳 Para completar tu pago, por favor ingresa al siguiente enlace:\n"
                    f"{payment_url}\n\n"
                    f"Total a pagar (IVA incluido): ${total_amount:.2f}"
                )
                if sale_order.exists():
                    transaction_id = payment_data["data"].get("order", {}).get("id")
                    # dev_reference = payment_data["data"].get("order", {}).get("dev_reference")

                    if transaction_id:
                        sale_order.write({
                            "transaction_id": transaction_id,
                            # "dev_reference": dev_reference
                        })
                message2 = request.env['whatsapp_messages_user'].sudo().get_message('fin_order')
                user_session.update_session(numero, state="confirmar_pago")
                MetaAPi.enviar_mensaje_texto(numero, message)
                time.sleep(3)
                MetaAPi.enviar_mensaje_texto(numero, message2)
            else:
                user_session.update_session(numero, state="salir")
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_enlace_pago')
                MetaAPi.enviar_mensaje_texto(
                    numero,
                    mensaje
                )
                MetaAPi.enviar_mensaje_con_botones_salida(numero)
        except Exception as e:
            user_session.update_session(numero, state="salir")
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_enlace_pago_nuvei')
            MetaAPi.enviar_mensaje_texto(
                numero,
                mensaje
            )
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            _logger.error(e)

    @classmethod
    def _download_whatsapp_file(cls, file_id: str, token: str) -> bytes | None:
        """Descarga binaria desde Graph API usando file_id."""
        try:
            url_meta = f"https://graph.facebook.com/v22.0/{file_id}"
            headers = {"Authorization": f"Bearer {token}"}
            r_meta = requests.get(url_meta, headers=headers, timeout=30)
            r_meta.raise_for_status()
            data = r_meta.json() or {}
            file_url = data.get("url")
            if not file_url:
                _logger.error("No se pudo resolver URL de descarga para file_id=%s", file_id)
                return None

            r_bin = requests.get(file_url, headers=headers, timeout=30)
            if r_bin.status_code != 200:
                _logger.error("Error al descargar el archivo %s: %s", file_id, r_bin.text)
                return None
            return r_bin.content
        except Exception:
            _logger.exception("Fallo descargando archivo WhatsApp file_id=%s", file_id)
            return None

    @classmethod
    def _attach_to_sale_order(cls, res_id: int, file_name: str, content: bytes, mimetype: str):
        """Crea adjunto en la orden de venta y postea mensaje."""
        vals = {
            'name': file_name,
            'datas': base64.b64encode(content).decode(),  # str base64
            'res_model': 'sale.order',
            'res_id': int(res_id),
            'type': 'binary',
            'mimetype': mimetype or 'application/octet-stream',
        }
        attachment = request.env['ir.attachment'].sudo().create(vals)
        so = request.env['sale.order'].sudo().browse(res_id)
        so.message_post(body="📎 Se ha recibido un comprobante de pago por WhatsApp.",
                        attachment_ids=[attachment.id])
        return attachment, so

    @classmethod
    def _jsonrpc_post(cls, endpoint: str, params: dict) -> tuple[dict, dict | None]:
        """
        Hace POST JSON-RPC y devuelve (result_dict, error_dict).
        error_dict != None si hubo error a nivel JSON-RPC o excepción HTTP.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": params or {},
                "id": None,
            }
            headers = {'Content-Type': 'application/json'}
            r = requests.post(endpoint, json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            resp = r.json() or {}
            if 'error' in resp:
                return {}, resp['error']
            return resp.get('result', {}) or {}, None
        except requests.RequestException as e:
            _logger.exception("Error HTTP al llamar %s", endpoint)
            return {}, {"message": str(e)}
        except Exception as e:
            _logger.exception("Error general llamando %s", endpoint)
            return {}, {"message": str(e)}

    @classmethod
    def _verify_deuna(cls, base_url: str, transaction_id: str) -> tuple[str, dict, dict | None]:
        """Consulta /deuna/payment/status y devuelve (STATUS_NORMALIZADO, result_dict, error_dict)."""
        endpoint = f"{base_url}/deuna/payment/status"
        result, err = cls._jsonrpc_post(endpoint, {"transaction_id": transaction_id})
        if err:
            return "", result, err
        status = (result.get('status') or '').upper()
        return status, result, None

    @classmethod
    def _verify_ahorita(cls, base_url: str, deeplink_id: str) -> tuple[str, dict, dict | None]:
        """Consulta /ahorita/payment/status y devuelve (status_lower, result_dict, error_dict)."""
        endpoint = f"{base_url}/ahorita/payment/status"
        result, err = cls._jsonrpc_post(endpoint, {"deeplink_id": deeplink_id})
        if err:
            return "", result, err
        status = (result.get('status') or '').strip().lower()
        return status, result, None

    @classmethod
    def handle_pay_method(cls, numero, message):
        try:
            user_session = UserSession(request.env)
            session = user_session.get_session(numero)

            if session.state != "confirmar_pago":
                _logger.info("Sesión no está en estado 'confirmar_pago' para el número: %s", numero)
                return

            order_data = json.loads(session.orden) if session.orden else {}
            res_id = int(order_data.get("sale_order_id") or 0)
            tipo_pago = (order_data.get("tipo_pago") or "").strip()

            sale_order = request.env['sale.order'].sudo().browse(res_id)
            if not res_id or not sale_order.exists():
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('not_found_order')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            file_payload = message.get("image") or message.get("document")
            file_type = "image" if "image" in message else ("document" if "document" in message else None)
            if not file_payload or not file_type:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_enviar_comprobante')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            file_id = file_payload.get("id")
            file_mime = file_payload.get("mime_type", "application/octet-stream")
            file_name = file_payload.get("filename", f"Comprobante_{file_type}_{file_id}")

            token = request.env['ir.config_parameter'].sudo().get_param('whatsapp.token')
            if not token:
                _logger.error("Token de WhatsApp no configurado (ir.config_parameter: whatsapp.token)")
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_procesar_comprobante')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            content = cls._download_whatsapp_file(file_id, token)
            if not content:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_procesar_comprobante')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            attachment, sale_order = cls._attach_to_sale_order(res_id, file_name, content, file_mime)

            user_session.update_session(numero, state="confirmar_pago")

            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''

            if tipo_pago == "Ahorita!/Deuna!":
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

            elif tipo_pago == "Deuna!":
                transaction_id = sale_order.pay_deuna_id
                status, result, err = cls._verify_deuna(base_url, transaction_id)

                if err:
                    _logger.error("[%s] Error del endpoint Deuna: %s", numero, err)
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "❌ No pudimos verificar tu pago. Intenta nuevamente en unos minutos."
                    )
                    return

                if status == 'APPROVED':
                    so = request.env['sale.order'].sudo().browse(res_id)
                    if so.exists() and so.state in ('draft', 'sent'):
                        so.action_confirm()

                    mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                    MetaAPi.enviar_mensaje_texto(numero, mensaje)
                    return
                elif status in {'PENDING', 'IN_PROCESS', 'PROCESSING'}:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "⏳ Tu pago está pendiente, cuando se haya realizado el pago envia nuevamente el comprobante."
                    )
                    return
                else:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "❌ El pago no fue aprobado. Por favor verifica tu pago e intenta nuevamente."
                    )
                    return
                return

            elif tipo_pago == "Ahorita!":
                deeplink_id = (sale_order.pay_ahorita_id or "").strip()

                status, result, err = cls._verify_ahorita(base_url, deeplink_id)

                if err or status == 'error':
                    _logger.error("[%s] Error del endpoint Ahorita: %s / result=%s", numero, err, result)
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "❌ No pudimos verificar tu pago. Intenta nuevamente en unos minutos."
                    )
                    return

                approved_vals = {'payment_confirmed', 'approved', 'aprobado', 'confirmado'}
                pending_vals = {'pending', 'pendiente', 'in_process', 'processing'}
                error_vals = {'error', 'failed', 'rechazado', 'declined'}

                if status in approved_vals:
                    so = request.env['sale.order'].sudo().browse(res_id)
                    if so.exists() and so.state in ('draft', 'sent'):
                        so.action_confirm()
                    mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                    MetaAPi.enviar_mensaje_texto(numero, mensaje)
                    return
                elif status in pending_vals:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "⏳ Tu pago está pendiente, cuando se haya realizado el pago envia nuevamente el comprobante."
                    )
                    return
                elif status in error_vals or status == '':
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "❌ No pudimos verificar tu pago. Intenta nuevamente en unos minutos."
                    )
                    return
                else:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "❌ El pago no fue aprobado. Por favor verifica tu pago e intenta nuevamente."
                    )
                    return
                return

            elif tipo_pago == "Tarjeta":
                transaction_id = sale_order.transaction_id
                order_name = sale_order.name
                if not transaction_id:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "Un asesor validará su pedido 👩🏼‍💻"

                    )
                    return
                payment_tx = request.env['payment.transaction'].sudo().search([('reference', '=', order_name)], limit=1)
                if not payment_tx:
                    MetaAPi.enviar_mensaje_texto(
                        numero,
                        "Un asesor validará su pedido 👩🏼‍"
                    )
                    return
                card_info = payment_tx.card_info
                card_info_json = json.loads(card_info)

                status = card_info_json.get("transaction", {}).get("status", "")

                if status == '1':
                    sale_order = request.env['sale.order'].sudo().browse(res_id)  # res_id debe ser un entero
                    if sale_order.state not in ['sale', 'done']:
                        sale_order.action_confirm()
                        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                        return MetaAPi.enviar_mensaje_texto(numero, mensaje)
                    else:
                        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                        return MetaAPi.enviar_mensaje_texto(numero, mensaje)

                elif status == '2':
                    mensaje = "⏳ Tu pago está pendiente, cuando se haya realizado el pago envia nuevamente el comprobante."
                    return MetaAPi.enviar_mensaje_texto(numero, mensaje)

                elif status == '3':
                    mensaje = "❌ Tu pago ha sido rechazado, intenta nuevamente."
                    return MetaAPi.enviar_mensaje_texto(numero, mensaje)
                else:
                    mensaje = "❌ No pudimos verificar tu pago. Intenta nuevamente en unos minutos."
                    return MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return
            else:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_recibido')
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                return

        except Exception:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('error_procesar_comprobante')
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            return

    @classmethod
    def _get_whatsapp_file_url(cls, file_id, token):
        """Obtener la URL del archivo (imagen o documento) desde la API de WhatsApp."""
        try:
            url = f"https://graph.facebook.com/v22.0/{file_id}"
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("url")
        except Exception as e:
            return None
