# -*- coding: utf-8 -*-

from odoo import fields, models


class DynamicFieldWidgets(models.Model):
  
    _name = 'dynamic.field.widgets'
    _rec_name = 'description'
    _description = 'Field Widgets'

    name = fields.Char(string="Name", help="Technical name of the widget")
    data_type = fields.Char(string="Data Type", help="Datatype suitable for"
                                                     " the widget")
    description = fields.Char(string="Description", help="Description of"
                                                         " the widget")
