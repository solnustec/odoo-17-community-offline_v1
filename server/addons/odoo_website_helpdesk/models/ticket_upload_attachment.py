import logging
import mimetypes
import base64
import boto3
import uuid
import os
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import io
from PIL import Image

_logger = logging.getLogger(__name__)

class TicketUploadAttachment(models.Model):
    _name = 'ticket.upload.attachment'
    _description = 'Cargar archivo del ticket'

    ticket_id = fields.Many2one('ticket.helpdesk', string='Ticket relacionado', required=True)
    name = fields.Char('Nombre del archivo', required=True)
    datas = fields.Binary('Archivo', required=True)
    file_url = fields.Char('URL en S3', readonly=True)
    mimetype = fields.Char('Tipo MIME', readonly=True)
    is_technical = fields.Boolean(string="Es archivo técnico", default=False)

    @api.model
    def create(self, vals):
        if vals.get('datas'):
            filedata = base64.b64decode(vals['datas'])

            filename = vals.get('name', '')
            _logger.info("Nombre del archivo recibido: %s", filename)

            # Intentar detectar el mimetype desde el nombre del archivo
            mimetype = mimetypes.guess_type(filename)[0]

            # Si no se detecta el mimetype, intentar desde el contenido
            if not mimetype:
                try:
                    from magic import Magic
                    mime = Magic(mime=True)
                    mimetype = mime.from_buffer(filedata[:1024])
                    _logger.info("Mimetype detectado desde contenido: %s", mimetype)
                except ImportError:
                    _logger.warning("python-magic no está instalado, usando mimetype por defecto")
                    # Fallback para extensiones comunes
                    if filename.lower().endswith('.png'):
                        mimetype = 'image/png'
                    elif filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                        mimetype = 'image/jpeg'
                    elif filename.lower().endswith('.pdf'):
                        mimetype = 'application/pdf'
                    elif filename.lower().endswith('.docx'):
                        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    elif filename.lower().endswith('.doc'):
                        mimetype = 'application/msword'

        # Compress image if it's an image
        if mimetype and mimetype.startswith('image/'):
            try:
                # Open the image
                img = Image.open(io.BytesIO(filedata))

                # If it's a PNG, convert to JPG for better compression
                if mimetype == 'image/png':
                    img = img.convert('RGB')
                    mimetype = 'image/jpeg'
                    if filename.lower().endswith('.png'):
                        filename = filename[:-4] + '.jpg'

                # Create output buffer
                output = io.BytesIO()

                # Save with optimized settings
                img.save(output,
                         format='JPEG' if mimetype == 'image/jpeg' else 'PNG',
                         optimize=True,
                         quality=70)  # Adjust quality (70 is a good balance)

                # Get compressed data
                filedata = output.getvalue()
                output.close()

                # Update vals with compressed data
                vals['datas'] = base64.b64encode(filedata)
                _logger.info("Imagen comprimida: %s", filename)

            except Exception as e:
                _logger.error("Error al comprimir imagen %s: %s", filename, str(e))
                # Fallback to original if compression fails
                pass

            vals['name'] = filename
            vals['mimetype'] = mimetype or 'application/octet-stream'
            _logger.info("Archivo: %s, MIME final: %s", filename, vals['mimetype'])
        return super().create(vals)

    def _upload_to_s3(self, filename, filedata):
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION')
        aws_bucket = os.getenv('AWS_BUCKETNAME')

        s3 = boto3.client('s3',
                          aws_access_key_id=aws_access_key,
                          aws_secret_access_key=aws_secret_key,
                          region_name=aws_region)

        key = f'tickets/{uuid.uuid4()}_{filename}'
        s3.put_object(Bucket=aws_bucket, Key=key, Body=filedata)

        return f'https://{aws_bucket}.s3.amazonaws.com/{key}'

    def action_upload(self):
        _logger.info("Ejecutando action_upload para ticket_id=%s, archivo=%s", self.ticket_id.id, self.name)
        if not self.datas:
            raise ValidationError(_('Debes seleccionar un archivo.'))

        filedata = base64.b64decode(self.datas)

        # Verificar si ya existe un archivo con el mismo nombre para este ticket
        existing_attachment = self.env['ticket.upload.attachment'].search([
            ('ticket_id', '=', self.ticket_id.id),
            ('name', '=', self.name),
        ], limit=1)
        if existing_attachment:
            _logger.warning("Archivo duplicado detectado: %s para ticket_id=%s", self.name, self.ticket_id.id)
            return {'type': 'ir.actions.act_window_close'}

        url = self._upload_to_s3(self.name, filedata)

        # Calcular mimetype para asegurar que sea correcto
        mimetype = mimetypes.guess_type(self.name)[0]
        if not mimetype:
            try:
                from magic import Magic
                mime = Magic(mime=True)
                mimetype = mime.from_buffer(filedata[:1024])
                _logger.info("Mimetype detectado desde contenido en action_upload: %s", mimetype)
            except ImportError:
                if self.name.lower().endswith('.png'):
                    mimetype = 'image/png'
                elif self.name.lower().endswith('.jpg') or self.name.lower().endswith('.jpeg'):
                    mimetype = 'image/jpeg'
                elif self.name.lower().endswith('.pdf'):
                    mimetype = 'application/pdf'
                elif self.name.lower().endswith('.docx'):
                    mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                elif self.name.lower().endswith('.doc'):
                    mimetype = 'application/msword'

        mimetype = mimetype or 'application/octet-stream'

        attachment = self.env['ticket.upload.attachment'].create({
            'ticket_id': self.ticket_id.id,
            'name': self.name,
            'datas': self.datas,
            'file_url': url,
            'mimetype': mimetype,
        })

        self.ticket_id.message_post(
            body=_("Archivo subido: <a href='%s' target='_blank'>%s</a>") % (url, self.name)
        )

        self.file_url = url
        _logger.info("Archivo subido: id=%s, nombre=%s, url=%s, mimetype=%s", attachment.id, attachment.name, attachment.file_url, attachment.mimetype)
        return {'type': 'ir.actions.act_window_close'}