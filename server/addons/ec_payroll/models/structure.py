# -*- coding: utf-8 -*-
from odoo import models, fields, registry, api
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools.misc import formatLang
from odoo.tools import float_is_zero, float_compare, float_round
from odoo.osv import expression
from collections import OrderedDict
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
from odoo import SUPERUSER_ID
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
from lxml import etree
import logging
_logger = logging.getLogger(__name__)

class hr_payroll_structure_account_map(models.Model):
    
    _name = 'hr.payroll.structure.account.map'
    
    structure_id = fields.Many2one('hr.payroll.structure', string=u'Estructura Salarial', 
                                   required=True, readonly=False, states={}, help=u"", ondelete="cascade") 
    origin_account_id = fields.Many2one('account.account', string=u'Cuenta Origen', 
                                        required=True, readonly=False, states={}, help=u"", ondelete="restrict") 
    dest_account_id = fields.Many2one('account.account', string=u'Cuenta Destino', 
                                        required=True, readonly=False, states={}, help=u"", ondelete="restrict") 
    
    _sql_constraints = [('name_uniq', 'unique (structure_id, origin_account_id)', _(u'Solo puede generar una linea por cuenta contable en la estructura salarial!')), ]
    
    
    @api.constrains('origin_account_id','dest_account_id')
    def _check_diff_accounts(self):
        if self.origin_account_id.id == self.dest_account_id.id:
            raise UserError(_(u'El mapeo no puede tener la misma cuenta de origen y destino %s') % self.origin_account_id.display_name)



class hr_payroll_structure(models.Model):

    _inherit = 'hr.payroll.structure'

    map_account_ids = fields.One2many('hr.payroll.structure.account.map', 'structure_id', string=u'Mapeo de Cuentas', 
                                      required=False, readonly=False, states={}, help=u"Use este mapeo para simplificar la configuración de sus reglas de sueldos")
    
    
    def get_account(self, account_id):
        self.ensure_one()
        map_model = self.env['hr.payroll.structure.account.map']
        maps = map_model.search([
            ('origin_account_id', '=', account_id),
            ('structure_id', '=', self[0].id),
                                 ])
        if maps:
            return maps.dest_account_id.id
        else:
            return account_id