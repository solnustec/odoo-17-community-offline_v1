from .meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request
from datetime import datetime, timedelta
from odoo import tools

class LinkPayAddFlow:
    @staticmethod
    def link_pay_add(numero, deeplink, amount):
        user_session = UserSession(request.env)
        user_session.get_session(numero)

        # === 1. Buscar nombre del cliente ===
        partner = request.env['res.partner'].sudo().search([
            '|',
            ('phone', '=ilike', numero),
            ('mobile', '=ilike', numero)
        ], limit=1)

        nombre_cliente = partner.name or "estimado cliente"

        # === 2. Extraer la parte después del dominio (incluye el ?) ===

        if '?' in deeplink:
            button_url_suffix = deeplink.split('?', 1)[1]
            button_url_suffix = f"?{button_url_suffix}"
        else:
            button_url_suffix = deeplink

        # === 3. Fecha y hora de vencimiento: ahora + 15 minutos ===
        try:
            # Intenta usar la zona horaria del usuario logueado
            user_tz = request.env.user.tz
            if not user_tz:
                user_tz = 'America/Guayaquil'  # fallback seguro
            now_local = datetime.now(tools.get_timezone(user_tz))
        except:
            # Si por alguna razón falla (ej. llamada externa), fuerza Ecuador
            from pytz import timezone
            now_local = datetime.now(timezone('America/Guayaquil'))

        vencimiento = now_local + timedelta(minutes=15)
        fecha_formateada = vencimiento.strftime("%d/%m/%Y a las %H:%M")

        # === 4. Monto con formato ecuatoriano (punto para miles, coma para decimales) ===
        try:
            monto_float = float(amount)
            monto_formateado = "${:,.2f}".format(monto_float).replace(",", "X").replace(".", ",").replace("X", ".")
        except:
            monto_formateado = "$0,00"

        # === 5. Variables del cuerpo de la plantilla ===
        variables = [
            nombre_cliente,       # {{1}}
            monto_formateado,     # {{2}}
            fecha_formateada      # {{3}}
        ]

        # === 6. Enviar mensaje con la plantilla correcta ===
        MetaAPi.enviar_mensaje_template(
            numero=numero,
            template_name="pagos_ahorita",
            language_code="es",
            variables=variables,
            button_url=button_url_suffix
        )