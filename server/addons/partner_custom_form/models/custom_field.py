from odoo import models, fields, api
import random
import string


class ResPartner(models.Model):
    _inherit = "res.partner"

    update_token = fields.Char(string="Update Token", readonly=True, copy=False)

    def generate_random_string(self, length=24):
        characters = string.ascii_letters + string.digits
        return "".join(random.choices(characters, k=length))

    @api.model
    def generate_update_token(self):
        sequence = self.generate_random_string()
        self.update_token = sequence + str(self.id)
        self.env.cr.commit()

    @api.model
    def get_update_url(self):
        self.generate_update_token()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/customer/update?token={self.update_token}"
