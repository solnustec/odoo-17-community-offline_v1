from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime
from lxml import etree
from odoo.tools.xml_utils import cleanup_xml_node, validate_xml_from_attachment
import random
import base64
from cryptography.hazmat.primitives.serialization import pkcs12
from base64 import b64decode
from zeep import Client
from zeep.transports import Transport
from requests import Session
import logging
from collections import defaultdict
import requests
import json

_logger = logging.getLogger(__name__)

# URLs del SRI
TEST_URL = {
    'reception': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    'authorization': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}

PRODUCTION_URL = {
    'reception': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    'authorization': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}

DEFAULT_TIMEOUT_WS = 20


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # button SRI
    show_send_sri_button = fields.Boolean(compute='_compute_show_send_sri_button')
    clave_acceso_sri = fields.Char(string='Clave de Acceso', readonly=True)
    pdf_attachment_id = fields.Many2one('ir.attachment', string="PDF Adjunto",
                                        readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company)
    # result xml
    guia_remision_xml = fields.Text("Guía de Remisión XML")

    # Campos para la Guía de Remisión
    transportista_id = fields.Many2one('res.partner', string='Transportista')
    identificacion = fields.Char(string='Identificación',
                                 related='transportista_id.vat', store=True,
                                 readonly=False)
    fecha_inicio_transporte = fields.Date(string='Fecha de inicio del transporte')
    fecha_fin_transporte = fields.Date(string='Fecha fin del transporte')
    direccion_partida = fields.Char(string='Lugar de partida')
    direccion_llegada = fields.Char(string='Lugar de llegada')
    destino = fields.Char(string='Dirección de destino')
    ruta = fields.Char(string='Ruta')
    city = fields.Char(string='Ciudad')
    vehiculo_transportista_id = fields.Many2one('fleet.vehicle',
                                                string='Vehículo asociado')
    placa = fields.Char(string='Placa del Vehículo',
                        related='vehiculo_transportista_id.license_plate', store=True)
    numero_guia_remision = fields.Char(string="Número de Guía de Remisión", copy=False,
                                       readonly=True)
    destinatario_id = fields.Many2one('res.partner', string='Destinatario')
    identificacion_destinatario = fields.Char(string='Identificación del Destinatario',
                                              related='destinatario_id.vat', store=True,
                                              readonly=False)
    productos = fields.One2many('stock.move', 'picking_id',
                                string='Productos Transportados')
    descripcion_mercaderia = fields.Text(
        string='Descripción de la Mercadería Transportada')
    cantidad_mercaderia = fields.Float(string='Cantidad de Mercadería Transportada')
    motivo_traslado = fields.Char(string='Motivo del Traslado')
    ambiente_pruebas = fields.Char(string='ambiente de pruebas')
    type_transfer = fields.Selection([('0', 'Normal'),
                                      ('1', 'Express'), ],
                                     string='Tipo de transferencia',
                                     default='0')
    key_transfer = fields.Char(string='ambiente de pruebas', readonly=False)

    # CAMPO PARA SUMATORIA DE TRANFERENCIA EN DINERO NO ELIMINAR
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
        readonly=True
    )

    amount_total = fields.Monetary(
        string="Total Transferencia",
        compute="_compute_amount_total",
        store=True,
        currency_field="currency_id"
    )

    @api.depends('move_ids_without_package.total_line')
    def _compute_amount_total(self):
        for picking in self:
            picking.amount_total = sum(picking.move_ids_without_package.mapped('total_line'))

    # METODOS PARA ENVIO DE TRANSFERENCIAS Y VALIDACIONES
    def action_update_all_stocks(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                stock_quant = self.env['stock.quant'].search([
                    ('location_id', '=', picking.location_id.id),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)
                move.stock_product = stock_quant.inventory_quantity_auto_apply - stock_quant.reserved_quantity if stock_quant else 0

    # BOTON DE VALIDACION DE TRANSFERENCIAS ESTADO "HECHO"
    def button_validate(self):
        result = super(StockPicking, self).button_validate()

        if self.picking_type_id.code == 'internal' and self.location_id.warehouse_id.code == 'BODMA' and not self.key_transfer:
            self.transfer_from_parent_to_branch()

        elif self.picking_type_id.code == 'internal' and not self.key_transfer:
            self.create_transfer_from_branch_to_branch()
        return result

    @api.model
    def get_warehouse_from_config(self, config_id):
        try:
            if not config_id:
                return False

            config = self.env['pos.config'].sudo().browse(config_id)

            # Verificar que la configuración existe
            if not config.exists():
                return False

            # Verificar que tiene picking_type_id
            if not config.picking_type_id:
                return False

            # Verificar que el picking_type_id tiene warehouse_id
            if not config.picking_type_id.warehouse_id:
                return False

            warehouse = config.picking_type_id.warehouse_id

            return warehouse.id

        except Exception as e:
            # Log del error si es necesario
            # _logger.error("Error getting warehouse from config: %s", str(e))
            return False

    def transfer_from_parent_to_branch(self):
        list_product_transfer = []
        counter_product = 0
        for move in self.move_ids_without_package:
            counter_product += 1
            product_data = {
                "externo": "0",
                "idExterno": "0",
                "LINE": str(counter_product),
                "IDITEM": move.product_id.id_database_old,
                "QUANTITY": move.product_uom_qty,
                "RECIBIDA": 0,
                "FECHCADU": "2017-08-08",
                "nota": "Transferencia generada por odoo",
                "YA": 0,
                "idlote": ""
            }
            list_product_transfer.append(product_data)

        data = {
            "transfer": {
                "date": self.scheduled_date.strftime("%Y-%m-%d"),
                "GENERADO": 0,
                "MONEDA": 1,
                "tomardesde": 0,
                "hora": datetime.now().strftime("%H:%M:%S"),
                "bloqueado": 0,
                "TOTAL": 0,
                "nota": "PAGINA 1",
                "itemseries": 0,
                "TIPOCAMBIO": 1.0,
                "numero": "",
                "idBodFROM": self.location_id.warehouse_id.external_id,
                "Externo": 0,
                "tipo": 3,
                "responsable": self.user_id.employee_id.name,
                "idBodTO": self.location_dest_id.warehouse_id.external_id,
                "transito": 0,
                "sync": 0,
                "idUser": self.user_id.employee_id.id_employeed_old,
                "idIn": "",
                "IdExterno": 0,
                "express": self.type_transfer,
                "STATE": 1,
                "idOut": "",
                "YA": 1,  # dejarlo en 1 si sale de bodega central
                "autosync": 0,
                "VOID": 0,
                "idsupplier": "",
                "guiaremision": 0,
            },
            "transferdets": list_product_transfer
        }

        url_api_transfer = self.env['ir.config_parameter'].sudo().get_param(
            'url_api_create_transfer_in_visual')

        if not url_api_transfer:
            return

        api_url = url_api_transfer
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }
        try:
            response = requests.post(api_url, data=json.dumps(data), headers=headers, timeout=5)
            if response.status_code == 200 or response.status_code == 201:
                print("Transferencia enviada correctamente.")
            else:
                print(f"Error en la solicitud: {response.status_code}, {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"Error en la conexión con la API: {e}")

    def create_transfer_from_branch_to_branch(self):
        list_transfers = []

        for record in self:

            if not record.location_id.warehouse_id or not record.location_dest_id.warehouse_id:
                raise ValueError(f"Transfer {record.id}: Almacenes origen/destino inválidos")

            # Buscar si existe un borrador previo en json.pos.transfers.edits
            draft_transfer = self.env['json.pos.transfers.edits'].sudo().search([
                ('stock_picking_id', '=', record.id)
            ], limit=1)

            # Obtener la llave del borrador si existe
            draft_db_key = draft_transfer.db_key if draft_transfer else ""

            # Validar usuario responsable
            employee_name = "Unknown"
            if record.user_id and record.user_id.employee_ids:
                employee_name = record.user_id.employee_ids[0].name

            # Construir líneas de productos una sola vez
            # move_lines = record.move_line_ids
            # order_lines_data = []
            # transfer_products_list = []

            # for index, line in enumerate(move_lines):
            #     # Datos del producto
            #     product_id = line.product_id.product_tmpl_id.id_database_old or None
            #     quantity = line.quantity
            #     price = line.product_id.list_price or 0.0
            #
            #     # Para transfer_products
            #     transfer_products_list.append({
            #         "llave": index + 1,
            #         "orden": "10",
            #         "iditem": product_id,
            #         "cantidad": quantity,
            #         "precio": price,
            #         "idlote": 0,
            #         "disponible": 0,
            #         "recibido": 0,
            #     })
            #
            #     # Para order_lines
            #     order_lines_data.append([
            #         "10",
            #         product_id,
            #         quantity,
            #         price,
            #         0.0,
            #     ])

            pos_conf = self.env['pos.config'].sudo().search([
                ('picking_type_id.warehouse_id', '=', record.location_id.warehouse_id.id),
                ('point_of_sale_series', '!=', False),
            ], limit=1)

            # Estructura de datos - usar la llave del borrador si existe
            # data = {
            #     "transfer": {
            #         "llave": draft_db_key,
            #         "iduser": record.user_id.employee_ids and record.user_id.employee_ids[0].id_employeed_old or '',
            #         "idbodfrom": record.location_id.warehouse_id.external_id,
            #         "idbodto": record.location_dest_id.warehouse_id.external_id,
            #         "serie": pos_conf.point_of_sale_series or "",
            #         "secuencia": 0,
            #         "tipo": 1,
            #         "l_close": 0,
            #         "l_recibido": 0,
            #         "l_sync": 0,
            #         "l_file": 0,
            #         "l_void": 0,
            #         "t_init": datetime.now().strftime("%Y-%m-%d"),
            #         "t_close": "",
            #         "t_recibido": "",
            #         "t_sync": "",
            #         "t_void": None,
            #         "t_file": None,
            #         "l_sel": 0,
            #         "total": "",
            #         "nota": record.note or "",
            #         "responsable": record.user_id.email or "",
            #         "cdet": {
            #             "fields": ["orden", "iditem", "cantidad", "precio", "idlote"],
            #             "data": order_lines_data
            #         },
            #         "express": record.type_transfer or "",
            #     },
            #     "transfer_products": transfer_products_list
            # }

            obj = {
                # 'json_data': json.dumps([data], indent=4),
                'external_id': record.location_id.warehouse_id.external_id or "",
                'point_of_sale_series': pos_conf.point_of_sale_series or "",
                'stock_picking_id': record.id,
                'sync_date': None,
                'db_key': draft_db_key,
                'sent': False,
                'employee': employee_name,
                'origin': record.location_id.warehouse_id.name or "Unknown",
                'destin': record.location_dest_id.warehouse_id.name or "Unknown",
            }

            list_transfers.append(obj)

        if list_transfers:
            self.env['json.pos.transfers'].sudo().create(list_transfers)

    # AQUI TERMINA EL CODIGO

    def _compute_show_send_sri_button(self):
        for picking in self:
            picking.show_send_sri_button = picking.state == 'done'

    @api.onchange('transportista_id')
    def _onchange_transportista_id(self):
        if self.transportista_id:
            vehiculo = self.env['fleet.vehicle'].search(
                [('driver_id', '=', self.transportista_id.id)], limit=1)
            self.vehiculo_transportista_id = vehiculo if vehiculo else False
            self.placa = vehiculo.license_plate if vehiculo else False

    #
    # @api.model
    # def create(self, vals):
    #     if not vals.get('numero_guia_remision'):
    #         vals['numero_guia_remision'] = self._get_next_numero_guia_atomic()
    #
    #     return super(StockPicking, self).create(vals)
    #
    # def _get_next_numero_guia_atomic(self) -> str:
    #     """
    #     Obtiene el siguiente número de guía de forma atómica.
    #     Evita conflictos de concurrencia usando UPDATE ... RETURNING.
    #     """
    #     company = self.env.company
    #     is_production = company.l10n_ec_production_env
    #
    #     # Determinar qué campo actualizar
    #     field_name = 'numero_guia_remision' if is_production else 'numero_guia_pruebas'
    #
    #     # UPDATE atómico con RETURNING - sin race conditions
    #     self.env.cr.execute(f"""
    #         UPDATE res_company
    #         SET {field_name} = LPAD(
    #                 (COALESCE(NULLIF({field_name}, '')::int, 0) + 1)::text,
    #                 9,
    #                 '0'
    #             ),
    #             write_date = NOW() AT TIME ZONE 'UTC',
    #             write_uid = %s
    #         WHERE id = %s
    #         RETURNING {field_name}
    #     """, [self.env.uid, company.id])
    #
    #     result = self.env.cr.fetchone()
    #
    #     # Invalidar cache para que Odoo no intente escribir de nuevo
    #     self.env['res.company'].invalidate_model([field_name])
    #
    #     return result[0] if result else '000000001'

    def copy(self, default=None):
        default = dict(default or {})

        # Usar el número de guía correcto según el ambiente
        if self.env.company.l10n_ec_production_env:
            last_numero_guia = self.env.company.numero_guia_remision
        else:
            last_numero_guia = self.env.company.numero_guia_pruebas

        # Incrementar el número de guía
        if last_numero_guia.isdigit():
            new_secuencial = str(int(last_numero_guia) + 1).zfill(9)
        else:
            new_secuencial = '000000001'

        default['numero_guia_remision'] = new_secuencial

        # Actualizar el número de guía en la compañía
        if self.env.company.l10n_ec_production_env:
            self.env.company.numero_guia_remision = new_secuencial
        else:
            self.env.company.numero_guia_pruebas = new_secuencial

        return super(StockPicking, self).copy(default)

    def _generate_clave_acceso(self):
        """
        Genera la clave de acceso para la guía de remisión con exactamente 49 caracteres.
        """
        # Fecha de emisión debe tener 8 caracteres en formato ddMMyyyy
        fecha_emision = self.fecha_inicio_transporte.strftime('%d%m%Y')

        # Tipo de comprobante (siempre '06' para la guía de remisión)
        tipo_comprobante = '06'

        # RUC debe tener exactamente 13 caracteres
        ruc = self.company_id.vat
        if len(ruc) != 13:
            raise ValidationError('El RUC debe tener 13 dígitos.')

        # Tipo de ambiente (1 para pruebas, 2 para producción)
        tipo_ambiente = '2' if self.company_id.l10n_ec_production_env else "1"

        # Secuencial (solo números, debe tener 9 caracteres)
        secuencial = ''.join(filter(str.isdigit, self.numero_guia_remision)).zfill(9)
        if len(secuencial) != 9:
            raise ValidationError(
                f'El secuencial debe tener 9 dígitos, pero tiene {len(secuencial)}.')

        # Código del establecimiento y punto de emisión (3 caracteres cada uno)
        codigo_establecimiento = self.company_id.l10n_ec_establishment_code.zfill(3)
        punto_emision = self.company_id.punto_emision.zfill(3)

        # Código numérico generado aleatoriamente con 8 dígitos
        codigo_numerico = str(random.randint(1, 99999999)).zfill(8)

        # Código de emisión (siempre es '1')
        codigo_emision = '1'

        # Formar la clave de acceso sin el dígito verificador
        clave_acceso_sin_dv = f'{fecha_emision}{tipo_comprobante}{ruc}{tipo_ambiente}{codigo_establecimiento}{punto_emision}{secuencial}{codigo_numerico}{codigo_emision}'
        # Verificación de longitud
        if len(clave_acceso_sin_dv) != 48:
            raise ValidationError(
                f"La clave de acceso debe tener 48 caracteres, pero tiene {len(clave_acceso_sin_dv)}.")

        # Calcular el dígito verificador
        digito_verificador = self._modulo11(clave_acceso_sin_dv)

        # Clave de acceso final
        clave_acceso = f'{clave_acceso_sin_dv}{digito_verificador}'

        self.clave_acceso_sri = clave_acceso
        self.ambiente_pruebas = tipo_ambiente
        return clave_acceso

    def _modulo11(self, clave_acceso):
        """
        Calcula el dígito verificador usando el algoritmo módulo 11.
        """
        # Revertir la clave de acceso para aplicar el algoritmo desde el final
        clave_invertida = clave_acceso[::-1]

        # Inicializar variables
        coeficiente = 2
        suma = 0

        # Aplicar el algoritmo para calcular el dígito verificador
        for char in clave_invertida:
            # Multiplicar cada dígito por el coeficiente actual
            numero = int(char)
            numero = numero * coeficiente
            suma += numero

            # Aumentar el coeficiente (vuelve a 2 después de 7)
            coeficiente += 1
            coeficiente = 2 if coeficiente > 7 else coeficiente

        # Obtener el residuo de la suma y calcular el dígito verificador
        mod = suma % 11
        mod = 11 - mod

        # Ajustar el valor del dígito verificador según el módulo
        digito_verificador = 0 if mod == 11 else 1 if mod == 10 else mod

        return digito_verificador

    def _l10n_ec_get_guia_remision_data(self):
        self.ensure_one()
        move_info = {
            'company': self.company_id,
            'clave_acceso': self._generate_clave_acceso(),
            'secuencial': self.numero_guia_remision,
            'dir_establecimiento': self.company_id.street,
            'dir_partida': self.direccion_partida,
            'transportista_id': self.transportista_id,
            'fecha_ini_transporte': self.fecha_inicio_transporte.strftime('%d/%m/%Y'),
            'fecha_fin_transporte': self.fecha_fin_transporte.strftime('%d/%m/%Y'),
            'vehiculo_transportista': {
                'license_plate': self.vehiculo_transportista_id.license_plate if self.vehiculo_transportista_id else '',
            },
            'destinatario_id': self.destinatario_id,
            'direccion_llegada': self.destino,
            'motivo_traslado': self.motivo_traslado,
            "ambiente": self.ambiente_pruebas,
            'productos': [{
                'default_code': move.product_id.default_code or '',
                'name': move.product_id.name or '',
                'cantidad': move.product_uom_qty,
                'bulto': move.bulto,  # Aquí incluimos el campo bulto
            } for move in self.move_ids_without_package],
        }

        return move_info

    def _l10n_ec_generate_guia_remision_xml(self):
        """
        Genera el XML de la guía de remisión.
        """
        self.ensure_one()
        move_info = self._l10n_ec_get_guia_remision_data()
        template = 'guide_remision.guia_remision_template'
        xml_content = self.env['ir.qweb']._render(template, move_info)
        xml_content = cleanup_xml_node(xml_content)

        return etree.tostring(xml_content, encoding='unicode')

    def _get_certificate(self):
        """
        Obtiene el certificado configurado en la compañía para firmar los documentos electrónicos.
        """
        # Asegúrate de que la compañía tiene configurado un certificado
        certificate = self.company_id.l10n_ec_edi_certificate_id
        if not certificate:
            raise ValidationError(
                "No se ha configurado un certificado electrónico para esta compañía.")

        # Verificar que el certificado tenga contenido y una contraseña válida
        if not certificate.content:
            raise ValidationError("El certificado configurado no tiene contenido.")
        if not certificate.password:
            raise ValidationError("El certificado configurado no tiene una contraseña.")

        return certificate

    def _action_sign(self, xml_string):
        """
        Firma el XML con el certificado digital de la compañía.
        """
        certificate = self._get_certificate()

        try:
            # Cargar la clave privada y el certificado público desde el archivo PKCS12
            private_key, public_cert, _dummy = pkcs12.load_key_and_certificates(
                b64decode(certificate.content),
                certificate.password.encode(),
            )

            # Proceder con el proceso de firma del XML...
            signed_xml = certificate._action_sign(xml_string)
            return signed_xml

        except ValueError as e:
            _logger.error(f"Error al cargar el certificado PKCS12: {str(e)}")
            raise ValidationError(f"Error al cargar el certificado PKCS12: {str(e)}")

        except Exception as e:
            _logger.error(f"Error inesperado al intentar firmar el XML: {str(e)}")
            raise ValidationError(
                f"Error inesperado al intentar firmar el XML: {str(e)}")

    def action_generate_and_send_guia(self):
        """Generates and sends the guide to the SRI"""
        # Generar el XML de la Guía de Remisión
        xml_string = self._l10n_ec_generate_guia_remision_xml()

        # Firmar el XML
        signed_xml = self._action_sign(xml_string)

        # Enviar al SRI
        response = self._send_xml_to_sri(signed_xml)

        # Decodificar la respuesta de bytes a cadena
        response_str = response.decode('utf-8')
        print(response_str)
        # Procesar la respuesta del SRI
        if 'AUTORIZADO' in response_str:
            self.l10n_ec_authorization_number = "Número de autorización"  # Asegúrate de extraer esto de la respuesta.
            self.l10n_ec_authorization_date = fields.Datetime.now()  # Asigna la fecha actual o extrae de la respuesta.

    def _send_xml_to_sri(self, signed_xml):
        """
        Envío del XML firmado al SRI usando una solicitud SOAP.
        """
        # Determinar la URL de envío según el ambiente (producción o pruebas)
        if self.company_id.l10n_ec_production_env:
            reception_url = PRODUCTION_URL['reception']
        else:
            reception_url = TEST_URL['reception']

        print(reception_url)
        print(self.clave_acceso_sri)
        print(self.ambiente_pruebas)
        # Codificar el XML firmado en base64
        signed_xml_base64 = base64.b64encode(signed_xml.encode('utf-8')).decode('utf-8')

        # Construir la envoltura SOAP con el XML codificado en base64
        soap_envelope = f"""
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
           <soapenv:Header/>
           <soapenv:Body>
              <ns2:validarComprobante xmlns:ns2="http://ec.gob.sri.ws.recepcion">
                 <xml>{signed_xml_base64}</xml>
              </ns2:validarComprobante>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        headers = {'Content-Type': 'text/xml; charset=utf-8'}

        try:
            # Enviar la solicitud SOAP
            response = requests.post(reception_url, data=soap_envelope, headers=headers,
                                     timeout=DEFAULT_TIMEOUT_WS)

            if response.status_code != 200:
                raise ValidationError(
                    f"Error en la recepción del documento: {response.content}")

            # Manejo de la respuesta
            return response.content

        except requests.ConnectionError as e:
            raise ValidationError(f"Error de conexión al SRI: {e}")

    def consultar_guia_remision(self):
        # URL del WSDL del servicio de autorización de comprobantes offline
        if self.company_id.l10n_ec_production_env:
            reception_url = PRODUCTION_URL['authorization']
        else:
            reception_url = TEST_URL['authorization']

        session = Session()
        session.timeout = 10  # 10 segundos de tiempo de espera para las solicitudes
        client = Client(reception_url, transport=Transport(session=session))

        try:
            response = client.service.autorizacionComprobante(
                claveAccesoComprobante=self.clave_acceso_sri
            )

            if response and response.autorizaciones:
                autorizacion = response.autorizaciones.autorizacion[0]
                estado = autorizacion.estado
                fecha_autorizacion = autorizacion.fechaAutorizacion.strftime(
                    '%Y-%m-%d %H:%M:%S') if hasattr(autorizacion,
                                                    'fechaAutorizacion') else 'No disponible'
                numero_autorizacion = autorizacion.numeroAutorizacion if hasattr(
                    autorizacion, 'numeroAutorizacion') else 'No disponible'
                ambiente = autorizacion.ambiente if hasattr(autorizacion,
                                                            'ambiente') else 'No disponible'

                guia_remision_data = {
                    'estado_sri': estado,
                    'fecha_autorizacion_sri': fecha_autorizacion,
                    'numero_autorizacion_sri': numero_autorizacion,
                    'ambiente_sri': ambiente,
                }

                return self.env.ref(
                    'guide_remision.action_shift_change_report').report_action(self)

            else:
                _logger.error(
                    "No se encontraron autorizaciones en la respuesta del SRI.")
                return None

        except Exception as e:
            _logger.error(f"Error al descargar el archivo: {str(e)}")
            return None

    def render_qweb_pdf(self, docids, data=None):
        # Llamar a la función original para obtener el PDF, pero pasando los datos personalizados
        data = {
            'estado_sri': self.clave_acceso_sri,
            'fecha_autorizacion_sri': self.fecha_inicio_transporte.strftime(
                '%Y-%m-%d %H:%M:%S'),
            'numero_autorizacion_sri': self.numero_guia_remision,
            'ambiente_sri': 'Producción' if self.company_id.l10n_ec_production_env else 'Pruebas',
        }

        return self.env['ir.actions.report']._render_qweb_pdf(
            'guide_remision.report_referral_guide_document_test', docids=docids,
            data=data
        )


class ReportStockPickingGuiaRemision(models.AbstractModel):
    _name = 'report.guide_remision.report_referral_guide_document_test'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.picking'].browse(docids)

        # Crear un diccionario para agrupar productos por bulto
        productos_por_bulto = defaultdict(list)
        for move in docs.move_ids_without_package:
            productos_por_bulto[move.bulto].append({
                'cantidad': move.product_uom_qty,
                'descripcion': move.product_id.name,
                'codigo_principal': move.product_id.default_code or '',
                'codigo_auxiliar': move.product_id.barcode or ''
            })

        # Crear los datos de la guía de remisión, incluyendo productos agrupados por bulto
        guia_remision_data = {
            'clave_acceso': docs.clave_acceso_sri,
            'fecha_autorizacion_sri': docs.fecha_inicio_transporte.strftime(
                '%Y-%m-%d %H:%M:%S'),
            'numero_autorizacion_sri': docs.numero_guia_remision,
            'ambiente_sri': 'Producción' if docs.company_id.l10n_ec_production_env else 'Pruebas',
            'ruc': docs.company_id.vat,
            'razon_social_transportista': docs.transportista_id.name,
            'identificacion_transportista': docs.transportista_id.vat,
            'placa_vehiculo': docs.vehiculo_transportista_id.license_plate,
            'fecha_inicio_transporte': docs.fecha_inicio_transporte.strftime(
                '%d/%m/%Y'),
            'fecha_fin_transporte': docs.fecha_fin_transporte.strftime('%d/%m/%Y'),
            'direccion_partida': docs.direccion_partida or 'Sin Dirección de Partida',
            'destinatario': docs.destinatario_id.name,
            'identificacion_destinatario': docs.destinatario_id.vat,
            'destino': docs.destino,
            'motivo_traslado': docs.motivo_traslado,
            'ruta': docs.ruta,
            'productos_por_bulto': productos_por_bulto,  # Agrupación por bultos
        }
        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'data': data,
            'docs': docs,
            'guia_remision_data': guia_remision_data,
        }
