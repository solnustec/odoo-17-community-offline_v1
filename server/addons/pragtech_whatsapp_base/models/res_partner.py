from odoo import models, fields, api
import unicodedata, re


def _fold(s):
    if not s: return ''
    s = unicodedata.normalize('NFD', s)
    s = re.sub(r'[\u0300-\u036f]', '', s)
    return s.lower()

class ResPartner(models.Model):
    _name = "res.partner.chatbot"

    name = fields.Char(string="Partner Name", required=True)
    name_fold = fields.Char(index=True, store=True, compute='_compute_name_fold')
    chatId = fields.Char('Whatsapp Chat ID')
    country_id = fields.Char('Country ID')
    same_vat_partner_id = fields.Char('Same VAT Partner ID')
    mobile = fields.Char('Mobile')
    whatsapp_message_ids = fields.One2many('whatsapp.messages', 'partner_id', string='Whatsapp Messages')

    @api.depends('name')
    def _compute_name_fold(self):
        for r in self:
            r.name_fold = _fold(r.name)
