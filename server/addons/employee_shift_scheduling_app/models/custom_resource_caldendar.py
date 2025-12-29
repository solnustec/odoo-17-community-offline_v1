
from odoo import models, fields, api, _

class ResourceCalendarDaysCustom(models.Model):
    _inherit = 'resource.calendar.attendance'

    is_extraordinary = fields.Boolean('Es dia extraordinario', default=False)

