from odoo import models, fields

class PromotionsByDay(models.Model):
    _name = "promotions_by_day.promotions_by_day"
    _description = "Promociones por Día de la Semana (POS)"
    _order = "weekday asc"

    name = fields.Char("Nombre", required=True)
    weekday = fields.Selection([
        ('0', 'Lunes'),
        ('1', 'Martes'),
        ('2', 'Miércoles'),
        ('3', 'Jueves'),
        ('4', 'Viernes'),
        ('5', 'Sábado'),
        ('6', 'Domingo'),
    ], string="Día de la Semana", required=True)
    discount_percent = fields.Float("Descuento (%)", required=True, default=10.0)
    active = fields.Boolean("Activo", default=True)
