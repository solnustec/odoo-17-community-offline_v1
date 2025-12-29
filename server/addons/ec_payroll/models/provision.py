# -*- coding: utf-8 -*-
#############################################################################
#                                                                           #
# Copyright (C) HackSystem, Inc - All Rights Reserved                       #
# Unauthorized copying of this file, via any medium is strictly prohibited  #
# Proprietary and confidential                                              #
# Written by Ing. Darwin Velez Anangono <dvelez@cenecuador.edu.ec>, 2022    #
# Written by Ing. Harry Alvarez <halvarez@cenecuador.edu.ec>, 2022          #
#                                                                           #
#############################################################################
from odoo import api, fields, models, tools, _
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from datetime import date, datetime, timedelta
from odoo.exceptions import UserError, RedirectWarning, ValidationError



class PayrollProvision(models.Model):
    _name = "payroll.provision"
    _description = "Provisiones"

    name = fields.Many2one("hr.employee", string="Empleado")
    year = fields.Integer("Año")
    month = fields.Integer("Mes")
    salary = fields.Float("Salario")
    hours_payroll = fields.Integer("Horas Trabajadas")
    amount = fields.Float("Ingresos Nómina")
    impuesto_renta = fields.Float("Impuesto a la renta")
    thirteenth = fields.Float("Decimo Tercero")
    fourteenth = fields.Float("Decimo Cuarto")
    holidays = fields.Float("Vacaciones")
    h_50 = fields.Float("Horas Extras 50%")
    h_100 = fields.Float("Horas Extras 100%")
    h_noct = fields.Float("Horas Extras Nocturnas")
    o_ingr = fields.Float("Otros ingresos")




