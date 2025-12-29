from odoo import models, fields, api

class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    department_id = fields.Many2one(
        'hr.department',
        string='Departamento'
    )

    street = fields.Char(
        string="Calle 1",
        help="Calle principal donde se encuentra ubicada la sucursal."
    )
    street2 = fields.Char(
        string="Calle 2",
        help="Información adicional de la dirección, como intersecciones o referencias."
    )
    city = fields.Char(
        string="Ciudad",
        help="Ciudad donde se ubica la sucursal."
    )
    state_id = fields.Many2one(
        'res.country.state',
        string="Provincia / Estado",
        help="Provincia o estado donde se encuentra la sucursal."
    )
    zip = fields.Char(
        string="Código Postal",
        help="Código postal correspondiente a la ubicación."
    )
    country_id = fields.Many2one(
        'res.country',
        string="País",
        help="País donde está localizada la sucursal."
    )
    x_lat = fields.Char(
        string="Latitud",
        help="Latitud geográfica de la sucursal, útil para mapas o ubicaciones GPS."
    )
    x_long = fields.Char(
        string="Longitud",
        help="Longitud geográfica de la sucursal."
    )
    mobile = fields.Char(
        string="Teléfono móvil",
        help="Número de celular de contacto de la sucursal."
    )
    phone = fields.Char(
        string="Teléfono fijo",
        help="Número de teléfono fijo de la sucursal."
    )
    is_public = fields.Boolean(
        string="¿Sucursal pública?",
        default=False,
        help="Marca esta opción si la sucursal está abierta al público en general."
    )
    x_turno = fields.Boolean(
        string="¿Farmacia de turno?",
        default=False,
        help="Indica si esta sucursal funciona como farmacia de turno."
    )
    x_24hours = fields.Boolean(
        string="¿Farmacia 24 horas?",
        default=False,
        help="Indica si la farmacia atiende las 24 horas del día."
    )


