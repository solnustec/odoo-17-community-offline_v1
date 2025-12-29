from odoo import models, fields, api, _
import logging
import json
import re
from odoo.exceptions import ValidationError

logger = logging.getLogger(__name__)


class WhatsappMessagesUser(models.Model):
    _name = "whatsapp_messages_user"
    _description = 'Mensajes del Bot para el Usuario'

    category = fields.Selection([
        ('bienvenida', 'Mensaje de Bienvenida'),
        ('message_hello', 'Mensaje de saludo'),
        ('salida', 'Mensaje de Salida'),
        # TODO: INACTIVIDAD
        ('inactividad', 'Mensaje de Inactividad'),
        # TODO: POLITICAS
        ('hello_politicas', 'Saludo Políticas'),
        ('confirmar_politicas', 'Confirmar políticas'),
        ('rechaza_condiciones', 'Rechaza Condiciones'),
        ('tipo_envio', 'Mensaje de Tipo Envio'),
        ('tipo_pago', 'Mensaje de Tipo Pago'),

        # TODO: TRABAJA CON NOSOTROS
        ('workplace_hello', 'Saludo Trabaja con Nosotros'),
        # TODO: SUCURSAL CERCANA
        ('branch_location', 'Ubicación Sucursal'),
        # TODO: FARMACIA TURNO
        ('pharmacy_location', 'Saludo Farmacia Turno'),
        # TODO: ASESOR
        ('hello_asesor', 'Saludo Asesor'),
        ('hello_asesor_movil', 'Saludo Asesor desde la app movil'),
        ('hello_asesor_product', 'Producto no encontrado'),
        ('product_found', 'Producto no encontrado'),


        ('search', 'Saludo Tienda'),
        ('not_found_product', 'Producto No Encontrado'),
        ('invalid_number', 'Producto de número Inválido'),
        ('invalid_product', 'Producto Inválido'),
        ('invalid_quantity', 'Cantidad Inválida'),
        ('no_product_selected', 'Ningún Producto Seleccionado'),
        ('fin_order', 'Fin de la Orden'),
        ('pago_efectivo', 'Pago efectivo'),
        ('solicitar_cedula_ruc', 'Solicitar Cedula o RUC'),
        ('solicitar_nombres', 'Solicitar Nombres'),
        ('nombre_vacio', 'Nombre Vacio'),
        ('email_invalido', 'Email Inválido'),
        ('solicitar_direccion', 'Solicitar Direccion'),
        ('solicitar_email', 'Solicitar Email'),
        ('solicitar_ubicacion_envio', 'Solicitar Ubicación de Envio'),
        ('error_metodo_pago', 'Metodo de Pago'),
        ('solicitar_apellidos_tarjeta', 'Solicitar Apellidos'),
        ('datos_tarjeta', 'Datos de la Tarjeta'),
        ('datos_transferencia', 'Datos de la Transferencia'),
        ('datos_pago_codigo', 'Pago por ahorita! / deuna!'),
        ('apellido_vacio', 'Vacio Apellidos Tarjeta'),
        ('error_enlace_pago', 'Error enlace de pago'),
        ('error_enlace_pago_nuvei', 'Error enlace de pago Nuvei'),
        ('error_procesa_pago', 'Error Procesa Pago'),
        ('error_enviar_comprobante', 'Error Enviar Comprobante'),
        ('error_procesar_comprobante', 'Error al procesar el Comprobante'),
        ('not_found_order', 'Orden no encontrada'),
        ('comprobante_recibido', 'Comprobante Recibido'),
        ('cedula_ruc_invalido', 'Cedula o RUC Inválido'),
        ('error_generar_resumen', 'Error Generar Resumen'),
        ('cancelar_compra', 'Cancelar Compra'),
        # TODO: ERROR
        ('branch_general_error', 'Error General'),
        ('error_branch', 'Error Sucursal'),
        ('image_error_branch', 'Error de Imagen Sucursal'),
        ('searched_product', 'Productos encontrados'),
        ('withdraw_purchase', 'Mensaje de la ciudad de retiro compra'),
        ('solicitar_email_nuevo', 'Mensaje de correo'),
        ('enlace_pagos', 'Enlace de pagos'),
        ('tiempo_envio', 'Mensaje de tiempo de envío'),
        

    ], string='Categoría', default='bienvenida', required=True)

    message = fields.Text(string="Mensaje", required=False,
                          help="Mensaje personalizado. Deja vacío para usar el mensaje por defecto.")

    effective_message = fields.Text(
        string="Mensaje a Mostrar",
        compute="_compute_effective_message",
        store=False
    )

    @api.model
    def get_default_messages(self):
        return {
            'bienvenida': '¿En qué te puedo ayudar hoy? 👇🏻',
            'message_hello': '¡Hola! Bienvenido, soy tu asistente virtual de *Farmacias Cuxibamba.*',
            'salida': 'Gracias por tu visita. ¡Hasta pronto! 👋',
            # TODO: INACTIVIDAD
            'inactividad': "Notamos que no has tenido actividad en los últimos 15 minutos, así que el chat se ha cerrado automáticamente. ¡Gracias por visitarnos! 👋",
            # TODO: POLITICAS
            'hello_politicas': "A continuación, comparto contigo los *Términos y Condiciones de acceso y uso de los servicios de Farmacias Cuxibamba a través de WhatsApp*.\n\n"
                               "*Enlace*: https://farmaciascuxibamba.com.ec/politicas-de-privacidad-whatsapp",
            'confirmar_politicas': "Para poder proseguir con la conversación, es necesario que, por favor, confirmes si estás de acuerdo con los *Términos y Condiciones de acceso y uso de los servicios de Farmacias Cuxibamba a través de WhatsApp.*",
            'rechaza_condiciones': "Aceptar los *Términos y Condiciones de acceso y uso de los servicios de Farmacias Cuxibamba a través de WhatsApp*, es necesario para poder seguir usando nuestros servicios. Puedes intentarlo más tarde😊",
            # TODO: ENVIOS

            # TODO: TRABAJA CON NOSOTROS
            'workplace_hello': "Para saber más información sobre postulaciones ingresa a:\n\n" +
                               "🔗 https://farmaciascuxibamba.com.ec/jobs",
            # TODO: UBICACION
            'branch_location': "📍 *Por favor, envía tu ubicación actual en WhatsApp*\n\n"
                               "Para hacerlo, usa la opción 📎 *Adjuntar > Ubicación* y selecciona *Enviar mi ubicación actual*.\n\n",
            # TODO: FARMACIA TURNO
            'pharmacy_location': "📍 *Por favor, envía tu ubicación actual en WhatsApp*\n\n"
                                 "Para hacerlo, usa la opción 📎 *Adjuntar > Ubicación* y selecciona *Enviar mi ubicación actual*",
            # TODO: ASISTENTE DE COMPRAS
            'hello_asesor': "¡Hola! 👋 Mi nombre es Paula 😊. ¿En qué te puedo ayudar hoy? 🤔\n"
                            "Envíame una foto 📸 o descríbeme el producto que buscas 🛍️.",
            'product_found': "El producto que has solicitado no se encuentra en nuestra tienda  🛍️.\n",
            'hello_asesor_product': "Nuestra asesora Paula te ayudará con más información sobre el producto que buscas",
            'hello_asesor_movil': "¡Hola! 👋 Mi nombre es Paula 😊. ¿En qué te puedo ayudar hoy? 🤔\n"
                            "Te ayudaré a cotizar lo solicitado.",
            # TODO: TIENDA
            'search': "Por favor, ingresa el nombre del producto que deseas\n\n"
                      "Ejemplo: Vitamina C",
            'not_found_product': "Lo sentimos, el producto que buscas no se encuentra en nuestra tienda.\n\n",
            'invalid_number': "Por favor, ingresa un número válido.",
            'invalid_product': "Número de producto inválido. Por favor, intenta nuevamente.",
            'invalid_quantity': "Por favor, ingresa una cantidad válida.",
            'no_product_selected': "No se ha seleccionado ningúno producto. Inicia nuevamente la búsqueda.",
            'fin_order': "Su orden ha sido generada con éxito y sera atendido por un asesor, por favor comparta el comprobante de pago.",
            'pago_efectivo': "¡Su orden ha sido generada con éxito! Un asesor validara su compra y procederá su despacho.",
            'searched_product': "Productos encontrados:\n",
            'solicitar_cedula_ruc': "Por favor, ingresa tu número de cédula o RUC:",
            'solicitar_nombres': "Datos de facturación:\nPor favor, ingresa tu nombre completo:",
            'nombre_vacio': "⚠️ El nombre no puede estar vacío. Por favor, ingrésalo nuevamente.",
            'email_invalido': "⚠️ Email inválido. Asegúrate de incluir '@' y '.'.",
            'solicitar_direccion': "Por favor, ingresa tu direción:",
            'solicitar_email_nuevo': "Por favor, ingresa tu correo electrónico:",
            'solicitar_email': "Tu factura electrónica será enviada al correo electrónico",
            'recibir_email': "Por favor, ingresa tu correo electrónico válido (ejemplo: nombre@dominio.com)",
            'error_email': "⚠️ Ocurrió un error al registrar tu email. Por favor intenta de nuevo.",
            'solicitar_ubicacion_envio': "Por favor, envía tu ubicación actual de WhatsApp.",
            'error_metodo_pago': "⚠️ Error: Método de pago no reconocido. Intenta nuevamente.",
            'datos_pago_codigo': ("*Pago por Ahorita!*"),
            'datos_transferencia': ("*Pago por Transferencia Bancaria*\n\n"
                                    "Realiza tu pago en la siguiente cuenta bancaria:\n\n"
                                    "*BANCO PICHINCHA:*\n"
                                    "Cuenta de Ahorros: #2210135251\n"
                                    "Titular: Farmacias Cuxibamba\n"
                                    "Correo: farmaciascuxibambadomicilios@gmail.com\n"
                                    "RUC: 1191751422001\n\n"),
            'solicitar_apellidos_tarjeta': "Por favor, ingresa tus apellidos:",
            'comprobante_pago': "Su orden ha sido generada con éxito, por favor comparta el comprobante de pago.",
            'datos_tarjeta': "Nombres de la Tarjeta:",
            'apellido_vacio': "⚠️ El apellido no puede estar vacío. Por favor, ingrésalo nuevamente.",
            'error_enlace_pago': "⚠️ Hubo un problema al generar el enlace de pago. Por favor, intenta nuevamente.",
            'error_enlace_pago_nuvei': "⚠️ Error inesperado con el servicio de Nuvei. Por favor, intenta nuevamente más tarde.",
            'error_procesa_pago': "⚠️ Hubo un error al procesar su pago. Por favor, contáctenos para asistencia.",
            'error_enviar_comprobante': "⚠️ Por favor, envíe una imagen o documento como comprobante de pago.",
            'error_procesar_comprobante': "⚠️ Error al procesar el archivo. Por favor, intenta de nuevo.",
            'not_found_order': "⚠️ No se encontró la orden asociada. Por favor, contáctenos.",
            'comprobante_recibido': "✅ Un asesor validara su compra y procederá con su despacho en menos de 30-45 minutos.",
            'cedula_ruc_invalido': "⚠️ Número inválido. Ingresa 10 dígitos para cédula o 13 para RUC.",
            'error_generar_resumen': "⚠️ Hubo un error al generar el resumen de la orden. Por favor, intenta de nuevo.",
            'cancelar_compra': "❌ Has cancelado tu compra. ¡Gracias por visitarnos! 👋",
            # TODO: ERROR
            'branch_general_error': "Lo sentimos, ha ocurrido un error al procesar tu solicitud. Por favor, intenta nuevamente.\n\n",
            'tipo_envio':"¿Cómo desea la entrega?",
            'tipo_pago':"Seleccionar método de pago:",
            'withdraw_purchase':"Selecciona la ciudad donde deseas retirar tu compra:",
            'enlace_pagos':" Por favor realiza tu pago aquí:  {link}",
            'tiempo_envio':"Envios a la ciudad de Loja de forma inmediata, para otras ciudades consulta su tiempo.",
            
        }

    @api.depends('message', 'category')
    def _compute_effective_message(self):
        defaults = self.get_default_messages()
        for record in self:
            record.effective_message = record.message or defaults.get(record.category, 'Mensaje no disponible')

    @api.model
    def get_message(self, category):
        record = self.search([('category', '=', category)], limit=1)
        if record and record.message:
            return record.message
        return self.get_default_messages().get(category, 'Mensaje no disponible')
