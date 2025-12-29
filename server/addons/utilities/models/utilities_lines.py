
from odoo import models, fields, api

class EmployeeScheduleHistory(models.Model):
    _name = 'hr.payroll.utilities.lines'
    _description = 'HR Payroll Utilities Lines'

    employee_id = fields.Many2one('hr.employee', string='Empleado', tracking=True, required=True)
    family_burdens = fields.Float("Cargas Familiares")
    days_compute = fields.Float("Días Computo")
    days_calendar = fields.Float("Días Calendario")
    calculate_10_porcent = fields.Float("Calculo del 10%")
    calculate_5_porcent = fields.Float("Calculo del 5%")
    total_days_family_burdens = fields.Float("Total De Cargas Familiares Por Total Días Trabajados")
    total_utilities = fields.Float("Total de Utilidad")
    judicial_retention = fields.Float("Retención Judicial")
    advance_received = fields.Float("Anticipo Recibido")
    to_receive = fields.Float("A Recibir")
    accounting_entry = fields.Float(string="Asiento Contable")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approve', 'Validado'),
        ('cancel', 'Cancelado')],
        related='utilities_id.state',
        readonly=True,
        string="Estado",
        store=True)
    utilities_id = fields.Many2one('hr.payroll.utilities', 'Proceso de Utilidad')