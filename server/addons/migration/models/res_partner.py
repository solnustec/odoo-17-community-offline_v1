import json
import threading

from odoo import models, fields, api
import logging
import requests
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    institution_ids = fields.One2many(
        'institution.client',  # Modelo intermedio
        'partner_id',  # Relación hacia res.partner
        string='Instituciones Asociadas',
        help='Instituciones a las que está vinculado este cliente.'
    )

    birth_date = fields.Date(string="Fecha de Nacimiento",
                             help="Fecha de nacimiento del cliente",
                             required=False)
    id_database_old = fields.Char(string="Id base anterior", required=False,default='-1')

    @api.model
    def create_from_ui(self, partner):
        """ create or modify a partner from the point of sale ui.
            partner contains the partner's fields. """
        # image is a dataurl, get the data after the comma
        if partner.get('image_1920'):
            partner['image_1920'] = partner['image_1920'].split(',')[1]

        partner_id = partner.pop('id', False)
        if partner_id:
            partner['id_database_old'] = '-1'
            self.browse(partner_id).write(partner)
        else:
            partner_id = self.create(partner).id
        return partner_id


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_res_partner(self):
        """Incluimos birth_date en los campos enviados al frontend del POS"""
        result = super(PosSession, self)._loader_params_res_partner()
        if 'fields' in result['search_params']:
            result['search_params']['fields'].append('birth_date')
        return result
