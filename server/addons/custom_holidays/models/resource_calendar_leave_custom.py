# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class CustomCalendarLeavesCustom(models.Model):
    _inherit = 'resource.calendar.leaves'

    type_of_leave_holiday = fields.Selection(
        selection=[
            ('national', 'Nacional'),
            ('local', 'Local'),
        ],
        string='Tipo de Feriado',
        required=True,
        default='national'
    )
    city_id = fields.Many2one(
        'hr.department.city',
        string="Ciudad"
    )



    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False,
                   lazy=True):
        # Verificamos si estamos agrupando por type_of_leave_holiday
        if 'type_of_leave_holiday' in groupby:
            # Agregar lógica condicional para agrupaciones anidadas
            new_groupby = []
            for record in self.search(domain):
                if record.type_of_leave_holiday == 'local':
                    new_groupby = ['type_of_leave_holiday', 'city_id']
                    break
                else:

                    new_groupby = ['type_of_leave_holiday']

            # Llamamos al método original con el nuevo groupby
            return super(CustomCalendarLeavesCustom, self).read_group(domain, fields,
                                                                new_groupby,
                                                                offset=offset,
                                                                limit=limit,
                                                                orderby=orderby,
                                                                lazy=lazy)

        # Si no hay groupby por 'type_of_leave_holiday', llamamos al método original
        return super(CustomCalendarLeavesCustom, self).read_group(domain, fields, groupby,
                                                            offset=offset, limit=limit,
                                                            orderby=orderby, lazy=lazy)

