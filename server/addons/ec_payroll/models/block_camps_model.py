
from odoo import models, fields

class EmployeeFieldBlockConfig(models.Model):
    _name = 'employee.field.block'
    _description = 'Configuración de bloqueo de campos para Empleado Perfil'

    category_id = fields.Many2many(
        'employee.field.block.category',
        string='Categoria de Busqueda',
        help='Agrupa campos relacionados para facilitar y optimizar la búsqueda de información.'
    )
    model_id = fields.Many2one(
        'ir.model',
        string="Modelo",
        required=True,
        ondelete='cascade',
        help="Modelo al que pertenece el campo, por ejemplo, hr.employee",
        default=lambda self: self.env['ir.model'].search([('model', '=', 'hr.employee')], limit=1) or False,)
    field_id = fields.Many2one('ir.model.fields', string="Campo", required=True,
                               ondelete='cascade',
                               domain="[('model_id', '=', model_id)]",
                               help="Campo que se va a configurar")

    unblock = fields.Boolean("Desbloquear para Empleado Perfil", default=False)



class EmployeeFieldBlockConfigCategory(models.Model):
    _name = 'employee.field.block.category'
    _description = 'Categoria de bloqueo de campos para Empleado Perfil'

    name = fields.Char(string='Nombre')