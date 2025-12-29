from odoo import models, fields, api
import unicodedata
import logging
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class SideEffect(models.Model):
    _name = 'product.sideeffect'
    _description = 'Efectos Secundarios'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción', required=False)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("El efecto secundario, con ese nombre ya existe!")


class ActivePrinciple(models.Model):
    _name = 'product.active_principle'
    _description = 'Principios Activos'
    name = fields.Char(string='Nombre', required=True)

    @api.constrains('name')
    def _check_name(self):
        def normalize_active_name(text):
            return unicodedata.normalize('NFKD', text).encode('ascii',
                                                              'ignore').decode(
                'utf-8').lower()

        for record in self:
            actives_principle_names = {normalize_active_name(record.name) for record in self}
            existing_actives_names = {
                normalize_active_name(active_principle.name)
                for active_principle in self.env['product.active_principle'].search([('id', 'not in', self.ids)])
            }

            if actives_principle_names & existing_actives_names:
                raise ValidationError("El principio activo con ese nombre ya existe.")


    @api.model
    def create(self, vals):
        if 'name' in vals:
            vals['name'] = vals['name'].upper()
        return super(ActivePrinciple, self).create(vals)


class Laboratory(models.Model):
    _name = 'product.laboratory'
    _description = 'Laboratorio'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción', required=False)
    id_database_old = fields.Char(string='Id base antigua')
    partner_id = fields.Many2one('res.partner', string='Proveedor')

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("El Laboratorio, con ese nombre ya existe!")


class Presentation(models.Model):
    _name = 'product.presentation'
    _description = 'Presentación'
    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción', required=False)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("La presentación, con ese nombre ya existe!")


class Manufacturer(models.Model):
    _name = 'product.manufacturer'
    _description = 'Fabricante'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción', required=False)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("El fabricante, con ese nombre ya existe!")

class PackagingType(models.Model):
    _name = 'product.packagingtype'
    _description = 'Tipo de Embalaje'

    name = fields.Char(string='Nombre', required=True)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("El tipo de embalaje, con ese nombre ya existe!")


class TherapeuticClassification(models.Model):
    _name = 'product.therapeuticclassification'
    _description = 'Clasificación Terapeutica'

    name = fields.Char(string='Tipo', required=True)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("La clasificación terapéutica, con ese nombre ya existe!")


class Brand(models.Model):
    _name = 'product.brand'
    _description = 'Marca'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción', required=False)
    partner_id = fields.Many2one('res.partner', string='Proveedor')
    id_database_old = fields.Char(string='Id base antigua',
                                  help='Id del producto en la base de datos antigua.')

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("La marca, con ese nombre ya existe!")


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'
    sale_uom_ecommerce = fields.Boolean(default=False,
                                        string='Activar ventas por cajas (Ecommerce)')
    id_database_old = fields.Char(string='Id base antigua')
    generic_name = fields.Char(string='Nombre genérico')
    brand_id = fields.Many2one('product.brand', string='Marca',
                               help='Marca del producto')
    laboratory_id = fields.Many2one('product.laboratory', string='Laboratorio',
                                    help='Laboratorio del producto',
                                    store=True)
    manufacturer_id = fields.Many2one('product.manufacturer',
                                      string='Fabricante',
                                      help='Fabricante del producto')
    therapeutic_classification_ids = fields.Many2many(
        'product.therapeuticclassification',
        string='Clasificación Terapéutica', )
    tags = fields.Char(string='Palabras clave para búsqueda rápida')
    indications = fields.Text(string='Indicaciones')
    contraindications = fields.Text(string='Contraindicaciones')
    side_effects_ids = fields.Many2many('product.sideeffect',
                                        string='Efectos secudarios',
                                        help='Efectos Secundarios')
    requires_recipe = fields.Boolean(string='Requiere Receta')
    active_principle_concentrations_ids = fields.One2many(
        'product.active_principle.concentration',
        'product_tmpl_id',
        string='Principios Activos con Concentración',
        help='Lista de principios activos con su concentración asociada al producto'
    )
    image_alt = fields.Char(string="Texto alternativo de imagen",
                            translate=True)
    image_refer_text = fields.Char(string="Etiqueta de referencia de imagen")
    alternate_product_ids = fields.Many2many(
        'product.template',
        'product_alternate_rel',
        'product_id',
        'alternate_id',
        string='Productos Alternativos',
        compute='_compute_alternate_products',
        store=True,
        widget = 'many2many_tags'
    )



    pharmaceutical_form = fields.Char(string='Forma Farmacéutica')
    presentation_ids = fields.Many2many('product.presentation',
                                        string="Presentación",
                                        help="Presentación del medicamento")
    packaging_type_id = fields.Many2one('product.packagingtype',
                                        string='Tipo de Embalaje')
    units_per_packaging = fields.Integer(string='Unidades por Embalaje')
    unit_dimensions = fields.Char(string='Dimensiones de Unidades')
    box_dimensions = fields.Char(string='Dimensiones de Cajas')
    life_span = fields.Integer(string='Vida Útil (Días)',
                               help='Vida útil del producto en días')
    manufacture_date = fields.Date(string='Fecha de Fabricación',
                                   help='Fecha de fabricación del producto')
    expiration_date = fields.Date(string='Fecha de Vencimiento',
                                  help='Fecha de vencimiento del producto')
    lot_number = fields.Char(string='Número de Lote',
                             help='Número de lote del producto')
    min_stock = fields.Integer(string='Stock Mínimo',
                               help='Cantidad mínima de stock para reabastecer')
    max_stock = fields.Integer(string='Stock Máximo',
                               help='Cantidad máxima de stock permitida')
    safety_stock = fields.Integer(string='Stock de Seguridad',
                                  help='Reserva de productos')
    lead_time = fields.Integer(string='Días de entrega del proveedor',
                               help='Días de entrega del proveedor')
    reorder_point = fields.Integer(string='Punto de Reorden',
                                   help='Cantidad mínima de stock para reordenar')
    boxes_per_pallet = fields.Integer(string='Cajas por Plancha',
                                      help='Número de cajas por plancha')
    pallets_per_container = fields.Integer(string='Planchas por Pallet',
                                           help='Número de planchas por pallet')
    warehouse_location = fields.Char(string='Ubicación de Almacén',
                                     help='Ubicación del almacén')
    packaging_unit = fields.Char(string='Unidad de Embalaje',
                                 help='Unidad de medida del empaque')
    total_units = fields.Integer(string='Cantidad Total de Unidades',
                                 help='Total de unidades en el empaque')
    suppliers = fields.Text(string='Proveedor(es)',
                            help='Información del proveedor')
    storage_requirements = fields.Text(
        string='Requisitos de Almacenaje Especial',
        help='Condiciones especiales de almacenaje')
    recommended_storage = fields.Text(string='Almacenamiento Recomendado',
                                      help='Instrucciones de almacenamiento')
    shipping_method = fields.Text(string='Método de Envío',
                                  help='Descripción del método de envío')
    attached_documentation = fields.Text(string='Documentación Adjunta',
                                         help='Notas sobre documentación adjunta')
    return_policy = fields.Text(string='Política de Devoluciones',
                                help='Condiciones para devoluciones')
    technical_sheet = fields.Text(string='Ficha Técnica del Producto',
                                  help='Características técnicas del producto')
    concentration = fields.Text(string='Concentración', help='Concentración')
    add_image = fields.Binary(string='Agregar Imagen',
                              help='Imagen del producto')
    health_record = fields.Text(string='Registro sanitario',
                                help='Registro del producto')
    substances = fields.Text(string='Sustancias', help='Sustancias')
    price_with_uom_ecommerce = fields.Float(
        string='Precio por UOM Ecommerce',
        help='Precio por unidad de medida del sitio web',
        store=True,
        compute='_compute_price_with_uom_ecommerce',
    )

    @api.depends(
        'list_price',
        'uom_id',
        'uom_po_id',
        'taxes_id',
        'sale_uom_ecommerce',
        'currency_id',
        'company_id',
    )
    def _compute_price_with_uom_ecommerce(self):
        for product in self:
            if not product.sale_uom_ecommerce:
                product.price_with_uom_ecommerce = product.list_price
                continue

            # 1) Precio base en la UoM original
            base_price = product.list_price or 0.0

            # 2) Convertir precio a la unidad de compra si existe
            if product.uom_po_id:
                base_price = product.uom_id._compute_price(base_price, product.uom_po_id)

            # 3) Filtrar impuestos por compañía
            taxes = product.taxes_id.filtered(
                lambda t: not t.company_id or t.company_id == product.company_id
            )

            # 4) Calcular total con impuestos incluidos
            res = taxes.compute_all(
                base_price,
                currency=product.currency_id,
                quantity=1.0,
                product=product
            )

            product.price_with_uom_ecommerce = product.currency_id.round(res.get('total_included', base_price))



    @api.depends('active_principle_concentrations_ids.active_principle_id')
    def _compute_alternate_products(self):
        principles_map = {
            rec.id: rec.active_principle_concentrations_ids.mapped(
                'active_principle_id.id')
            for rec in self
        }
        all_principles = set(sum(principles_map.values(), []))
        if not all_principles:
            for rec in self:
                rec.alternate_product_ids = [(5, 0, 0)]
            return
        candidates = self.env['product.template'].search([
            ('active_principle_concentrations_ids.active_principle_id', 'in',
             list(all_principles)),
            ('available_in_pos', '=', True),
            ('detailed_type', '=', 'product'),
        ])
        by_principle = {}
        for c in candidates:
            for pid in c.active_principle_concentrations_ids.mapped(
                    'active_principle_id.id'):
                by_principle.setdefault(pid, []).append(c.id)

        for rec in self:
            related_ids = set()
            for pid in principles_map.get(rec.id, []):
                related_ids.update(by_principle.get(pid, []))
            related_ids.discard(rec.id)
            rec.alternate_product_ids = [(6, 0, list(related_ids))]
    @api.model
    def create(self, vals):
        products = super(ProductTemplateInherit, self).create(vals)
        products._compute_alternate_products()

        Product = self.env['product.template']
        for p in products:
            ap_ids = p.active_principle_concentrations_ids.mapped('active_principle_id.id')
            if not ap_ids:
                continue
            related = Product.search([
                ('active_principle_concentrations_ids.active_principle_id', 'in', ap_ids),
            ])
            had_as_alt = Product.search([('alternate_product_ids', 'in', p.id)])
            impacted = (related | had_as_alt) - products
            if impacted:
                impacted._compute_alternate_products()
        return products

    def write(self, vals):
        old_map = {
            p.id: p.active_principle_concentrations_ids.mapped('active_principle_id.id')
            for p in self
        }
        res = super(ProductTemplateInherit, self).write(vals)
        if 'active_principle_concentrations_ids' in vals:
            self._compute_alternate_products()
            Product = self.env['product.template']
            for p in self:
                new_ap = p.active_principle_concentrations_ids.mapped('active_principle_id.id')
                watch = set(old_map.get(p.id, [])) | set(new_ap)
                if not watch:
                    continue
                related = Product.search([
                    ('active_principle_concentrations_ids.active_principle_id', 'in', list(watch)),
                ])
                had_as_alt = Product.search([('alternate_product_ids', 'in', p.id)])
                impacted = (related | had_as_alt) - self
                if impacted:
                    impacted._compute_alternate_products()
        return res



    def _get_product_fields(self):
        product_fields = super(ProductTemplateInherit,
                               self)._get_product_fields()
        product_fields.append('brand_id')
        return product_fields


    @api.model
    def vademecum_products(self, id_product):
        product = self.env['product.template'].browse(id_product)

        if not product:
            raise UserError(f"Producto no encontrado: {id_product}")

        try:
            alts = product.alternate_product_ids.filtered('available_in_pos')
            return [{
                'id': alt.id,
                'name': alt.name,
                'active_principles': alt.active_principle_concentrations_ids.mapped('active_principle_id.name'),
                'concentration': ', '.join(
                    str(c.concentration)
                    for c in alt.active_principle_concentrations_ids
                    if c.concentration not in ('nan', '-')
                ),
            } for alt in alts]

        except Exception as e:
            _logger.error(f"Error al obtener productos alternativos para {product.name}: {str(e)}")
            return []

class ProductActivePrincipleConcentration(models.Model):
    _name = 'product.active_principle.concentration'
    _description = 'Principio Activo con Concentración'

    product_tmpl_id = fields.Many2one('product.template', string='Producto',
                                      ondelete='cascade', required=True)
    active_principle_id = fields.Many2one('product.active_principle',
                                          string='Principio Activo',
                                          required=True)
    concentration = fields.Char(string='Concentración', required=True)

    _sql_constraints = [
        ('product_active_principle_uniq',
         'unique(product_tmpl_id, active_principle_id)',
         'Este principio activo ya ha sido asignado al producto.'),
    ]
