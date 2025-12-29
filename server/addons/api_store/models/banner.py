from odoo import models, fields, api


class Banner(models.Model):
    _name = 'api_store.banner'
    _description = 'API Store Banner'

    name = fields.Char(string='Nombre', required=True)
    image = fields.Image(string='Imagen 300x100', attachment=True,
                         required=True,
                         help="Esta imagen sera redimensionada a 300x100 pixels.")
    url = fields.Char(string='URL',
                      required=False,
                      help="URL a la que se redirigirá al hacer click en el banner.")
    enabled = fields.Boolean(string='Activo', default=True)

    s3_image_url = fields.Char(string="URL de imagen en S3",
                               compute="_compute_s3_image_url", readonly=True)

    def _compute_s3_image_url(self):
        for record in self:
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', record.id),
                ('res_field', '=', 'image')
            ], limit=1)
            attachment.write({'public': True})
            if attachment:
                record.s3_image_url = attachment.image_src  # o el campo que contenga la URL de S3
            else:
                record.s3_image_url = False
