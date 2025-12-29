from odoo import models, fields, api
from odoo.tools import logging

# _logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        fields_to_add = [
            "pos_stock_available",
            "pos_stock_incoming",
            "virtual_available",
            "laboratory_id",
            "discount",
            "free_stock",
            "pos_barcode",
            "uom_po_id",
            "multi_barcode_ids",
        ]
        if "search_params" in result and "fields" in result["search_params"]:
            for field in fields_to_add:
                if field not in result["search_params"]["fields"]:
                    result["search_params"]["fields"].append(field)
        if "load" not in result:
            result["load"] = {}
        result["load"]["multi_barcode_ids"] = {"fields": ["product_multi_barcode"]}
        # _logger.info("Loader params for product.product: %s", result)
        return result

    def _get_pos_ui_product_product(self, params):
        products = super(PosSession, self)._get_pos_ui_product_product(params)
        # Log a sample of the product data to inspect multi_barcode_ids structure
        if products:
            # _logger.info(
            #     "Sample product data sent to POS (first product): %s", products[0]
            # )
            # Optionally log multi_barcode_ids details for the first few products
            for prod in products[:3]:  # Limit to first 3 to avoid log spam
                if "multi_barcode_ids" in prod and prod["multi_barcode_ids"]:
                    barcode_ids = prod["multi_barcode_ids"]
                    # _logger.info(
                    #     "Product %s multi_barcode_ids: %s",
                    #     prod.get("display_name", "Unknown"),
                    #     barcode_ids,
                    # )
                    # Fetch full data for logging if it's just IDs
                    if isinstance(barcode_ids, list) and all(
                        isinstance(id_val, int) for id_val in barcode_ids
                    ):
                        barcode_records = self.env["product.multiple.barcodes"].browse(
                            barcode_ids
                        )
                        # _logger.info(
                        #     "Full barcode data for %s: %s",
                        #     prod.get("display_name", "Unknown"),
                        #     [
                        #         (rec.id, rec.product_multi_barcode)
                        #         for rec in barcode_records
                        #     ],
                        # )
        return products
