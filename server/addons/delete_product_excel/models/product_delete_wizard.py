from odoo import models, fields, _
import base64
import pandas as pd


class StockArchiveProducts(models.TransientModel):
    _name = 'stock.archive.products'
    _description = 'Archivar productos por Excel'

    file = fields.Binary(string="Archivo Excel", required=True)
    file_name = fields.Char(string="Nombre del archivo")

    def action_process_file(self):
        if not self.file:
            raise models.UserError(_("No se ha cargado ningún archivo."))

        # Leer el archivo cargado
        file_content = base64.b64decode(self.file)
        try:
            # Leer el archivo Excel
            df = pd.read_excel(file_content)
            if 'product_id' not in df.columns:
                raise models.UserError(_("El archivo debe contener una columna 'product_id'."))

            product_ids = df['product_id'].dropna().astype(int).tolist()

            # Buscar productos existentes en product.template
            products = self.env['product.template'].search([('id', 'in', product_ids)])

            if not products:
                raise models.UserError(_("No se encontraron productos para los IDs especificados."))

            # Archivar los productos encontrados
            products.write({'active': False})

            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

        except Exception as e:
            raise models.UserError(_("Error procesando el archivo: %s") % str(e))
