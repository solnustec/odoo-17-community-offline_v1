import requests

from odoo import models, fields, api


class ProductToSync(models.Model):
    _name = 'product.sync'
    _description = 'Sincronización de Productos'
    _order = 'create_date desc'

    product_id = fields.Many2one('product.template', string='Producto')
    sync_date = fields.Datetime(string='Fecha de Sincronización')
    id_database_old = fields.Char(
        string='ID en Base de Datos Antigua',
        help='ID del producto en la base de datos antigua.',
    )
    status = fields.Boolean(string='Sincronizado', default=False)

    new = fields.Boolean(
        string='Nuevo',
        help='Indica si el producto es nuevo y necesita ser sincronizado.',
        default=False,
    )
    downgrade = fields.Boolean(
        string='Dar de Baja',
        help='Indica si el producto se va a dar de baja.',
        default=False,
    )
    upgrade = fields.Boolean(
        string='Reactivar',
        help='Indica si el producto se va a reactivar.',
        default=False,
    )
    error_message = fields.Text(string='Mensaje de Error', readonly=True)

    @api.model
    def active_inactive_products_to_visual_fact(self):
        """
        Sincroniza productos a Visual Fact.
        """
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'vf_promotions_url')
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }

        products = self.env['product.sync'].sudo().search([
            ('status', '=', False),
        ])
        for product in products:
            # Aquí se implementaría la lógica de sincronización con Visual Fact
            data = {}
            # if product.new:
            #     taxes_id = product.product_id.taxes_id
            #     data = {
            #         "NAME": product.product_id.name,
            #         # "PRICE": product.product_id.list_price,
            #         # "IVA": 1 if taxes_id[0].amount > 0 else 0,
            #         "pdesde": "2025-08-21",
            #         "phasta": "2025-08-21",
            #         "NOTEUNIDAD": product.product_id.uom_po_id.name,
            #         "UNIDADESCAJA": product.product_id.uom_po_id.factor_inv,
            #     }
            # if product.downgrade :
            taxes_id = product.product_id.taxes_id
            data = {
                "ID": product.product_id.id_database_old,
                "NAME": product.product_id.name,
                # "PRICE": product.product_id.list_price,
                "pdesde": "2025-08-21",
                "phasta": "2025-08-21",
                "idlaboratorio": product.product_id.laboratory_id.id_database_old if product.product_id.laboratory_id else None,
                "IDBRAND": product.product_id.brand_id.id_database_old if product.product_id.brand_id else None,
                "BAJA": 1 if product.downgrade else 0,
                # "IVA": 1 if taxes_id[0].amount > 0 else 0,
            }
            # if product.upgrade :
            #     taxes_id = product.product_id.taxes_id
            #     data = {
            #         "ID": product.product_id.id_database_old,
            #         "NAME": product.product_id.name,
            #         "PRICE": product.product_id.list_price,
            #         "pdesde": "2025-08-21",
            #         "phasta": "2025-08-21",
            #         "BAJA": 0 if product.upgrade else 1,
            #         "IVA": 1 if taxes_id[0].amount > 0 else 0,
            #     }
            try:
                res = requests.put(base_url, json=[data],
                                   headers=headers,
                                   timeout=5)
                res.raise_for_status()
                if res.status_code == 201:
                    # TODO revisar aca
                    data = res.json()
                    # print(data)
                    update_items = data.get('items_actualizados', [])
                    # create_items = data.get('items_creados', [])

                    if len(update_items) > 0:
                        product.status = True
                        product.sync_date = fields.Datetime.now()
                        # product.id_database_old = update_items[0].get('ID', 0)
                        # product.product_id.id_database_old = update_items[0].get('ID', 0)

                    # if len(create_items) > 0:
                    #     print(create_items[0])
                    #     product.status = True
                    #     product.sync_date = fields.Datetime.now()
                    #     product.id_database_old = create_items[0].get('ID', 0)
                    #     product.product_id.id_database_old = create_items[0].get('ID', 0)

                    # {'message': 'Procesamiento completado. 0 items actualizados, 1 items creados.', 'items_actualizados': [], 'items_creados': [{'ID': '29623', 'NAME': 'Nuevo Producto ', 'PRICE': 1.0, 'IVA': 1, 'promCant': 0, 'baseCant': 0, 'descEsp': 0.0, 'action': 'created'}]}
                    # product.status = True


            except requests.exceptions.HTTPError as e:
                self.env['sales.summary.error'].sudo().create({
                    'error_details': f"active_inactive_products_to_visual_fact {e} {product.product_id}",
                })
