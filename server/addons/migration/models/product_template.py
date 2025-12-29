from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = "product.template"
    _description = "Product Template"

    standar_price_old = fields.Float(
        string="Standar Price Old",
        digits=(16, 4)  # 16 dígitos enteros, 4 decimales
    )
    avg_standar_price_old = fields.Float(
        string="Standar Price Old",
        digits=(16, 4)  # 16 dígitos enteros, 4 decimales
    )

    @api.model
    def cron_assign_company_to_products(self):
        company = self.env.company
        sale_tax = company.account_sale_tax_id

        batch_size = 500
        offset = 0
        total_updated = 0

        _logger.info("🚀 Inicio asignación compañía + impuestos (%s)", company.name)

        while True:
            products = self.search(
                [
                    ('company_id', '=', False),
                    '|',
                    ('detailed_type', '=', 'product'),
                    '&',
                    ('detailed_type', '=', 'service'),
                    ('service_tracking', '=', 'no'),
                ],
                limit=batch_size,
                offset=offset,
                order='id'
            )

            if not products:
                break

            for product in products:
                vals = {'company_id': company.id}

                # 👉 Servicios requieren impuesto si se venden
                if (
                        product.detailed_type == 'service'
                        and product.sale_ok
                        and sale_tax
                ):
                    vals['taxes_id'] = [(6, 0, [sale_tax.id])]

                try:
                    product.write(vals)
                    total_updated += 1

                    if total_updated % 100 == 0:
                        _logger.info("✅ Actualizados: %s", total_updated)

                except Exception as e:
                    _logger.error(
                        "❌ Error %s (%s): %s",
                        product.display_name,
                        product.id,
                        str(e)
                    )

            self.env.cr.commit()
            offset += batch_size

        _logger.info("🏁 Fin proceso. Total: %s", total_updated)

        cron = self.env.ref(
            'sanitary_registry_for_product.cron_assign_company_products',
            raise_if_not_found=False
        )
        if cron:
            cron.active = False

    # @api.model
    # def assign_company_to_services_with_taxes(self):
    #     company = self.env.company
    #     Product = self.env['product.template'].sudo()
    #
    #     batch_size = 300
    #     offset = 0
    #     updated = 0
    #     skipped = 0
    #
    #     _logger.info(
    #         "🚀 INICIO → Servicios SIN timesheets | Empresa: %s",
    #         company.name
    #     )
    #
    #     valid_iva_taxes = self.env['account.tax'].sudo().search([
    #         ('company_id', 'in', [company.id, False]),
    #         ('type_tax_use', '=', 'sale'),
    #         ('amount', 'in', [0.0, 15.0]),
    #     ])
    #
    #     if not valid_iva_taxes:
    #         _logger.warning("⚠️ No hay impuestos IVA válidos")
    #         return
    #
    #     while True:
    #         services = Product.search(
    #             [
    #                 ('detailed_type', '=', 'product'),
    #                 ('company_id', '=', False),
    #                 ('sale_ok', '=', True),
    #                 # ('taxes_id', '=', False),
    #
    #                 # 🔒 EXCLUSIÓN REAL DE TIMESHEETS
    #                 ('service_tracking', '=', 'no'),
    #             ],
    #             limit=batch_size,
    #             offset=offset,
    #             order='id'
    #         )
    #
    #         if not services:
    #             break
    #
    #         for product in services:
    #             try:
    #                 product_iva = product.taxes_id.filtered(
    #                     lambda t: t.amount in (0.0, 15.0)
    #                 )
    #
    #                 if not product_iva:
    #                     skipped += 1
    #                     continue
    #
    #                 taxes_to_set = valid_iva_taxes.filtered(
    #                     lambda t: t.amount in product_iva.mapped('amount')
    #                 )
    #
    #                 if not taxes_to_set:
    #                     skipped += 1
    #                     continue
    #
    #                 product.with_context(force_company=company.id).write({
    #                     'company_id': company.id,
    #                     'taxes_id': [(6, 0, taxes_to_set.ids)],
    #                 })
    #
    #                 updated += 1
    #
    #             except Exception as e:
    #                 skipped += 1
    #                 _logger.warning(
    #                     "⛔ OMITIDO [%s] %s → %s",
    #                     product.id,
    #                     product.display_name,
    #                     str(e)
    #                 )
    #
    #         offset += batch_size
    #
    #     _logger.info(
    #         "🏁 FIN → Actualizados: %s | Omitidos: %s",
    #         updated,
    #         skipped
    #     )



