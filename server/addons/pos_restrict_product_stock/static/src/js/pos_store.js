/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { Product } from "@point_of_sale/app/store/models";

patch(PosStore.prototype, {
  async addProductToCurrentOrder(...args) {
    try {
      const result = await this.env.services.orm.call(
        "product.product",
        "get_discount_for_product",
        [args[0].product_tmpl_id]
      );
      if (result && result.success) {
        args[0].discount = result.discount || 0;
        args[0].free_stock = result.free_stock || "";
      }
      return await super.addProductToCurrentOrder(...args);
    } catch (error) {
      return await super.addProductToCurrentOrder(...args);
    }
  },

  async _loadProductFields() {
    const fields = await super._loadProductFields();
    if (!fields.includes("pos_barcode")) {
      fields.push("pos_barcode");
    }
    return fields;
  },
});

patch(Product.prototype, {

    async setup() {
        super.setup(...arguments);
        await this.getStock(this.pos.pos_session.id, this.id);
        await this.getIncomingStock(this.pos.pos_session.id, this.id);
    },

    async getStock(session, product_id){
      const stockId = await this.env.services.orm.call('product.product', 'pos_stock_new', [session, product_id]);
      this.pos_stock_available = stockId;
    },

    async getIncomingStock(session, product_id){
      const incomingStock = await this.env.services.orm.call('product.product', 'pos_stock_incoming_new', [session, product_id]);
      this.pos_stock_incoming = incomingStock;
    }
})