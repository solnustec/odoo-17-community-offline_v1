/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {Order} from "@point_of_sale/app/store/models";

// Referencia al método original (importante)
const _super_add_orderline = Order.prototype.add_orderline;
const _super_export_as_JSON = Order.prototype.export_as_JSON;
const _super_init_from_JSON = Order.prototype.init_from_JSON;

patch(Order.prototype, {

    export_as_JSON() {
        const json = _super_export_as_JSON.apply(this, arguments);

        // ⭐ Guardar sale_id en el JSON para que persista
        json.sale_id = this.sale_id || null;
        return json;
    },

    init_from_JSON(json) {
        _super_init_from_JSON.apply(this, arguments);

        // ⭐ Restaurar sale_id cuando se abre desde historial del POS
        this.sale_id = json.sale_id || null;

        return this;
    },

    _covert_pos_line_to_sale_line: function (line) {
        let product = this.pos.db.get_product_by_id(line.product_id);
        let line_val = {
            product_id: line.product_id,
            price_unit: line.price_unit,
            product_uom_qty: line.qty,
            discount: line.discount,
            product_uom: product?.uom_id[0],
            reward_product_id: line?.reward_product_id,
        };
        if (line.uom_id) {
            line_val['product_uom'] = line.uom_id
        }
        if (line.variants) {
            line_val['variant_ids'] = [[6, false, []]];
            for (let j = 0; j < line.variants.length; j++) {
                let variant = line.variants[j];
                line_val['variant_ids'][0][2].push(variant.id)
            }
        }
        if (line.tax_ids) {
            line_val['tax_id'] = line.tax_ids;
        }
        if (line.customer_note) {
            line_val['note'] = line.customer_note;
        }
        return [0, 0, line_val];
    },

    async add_orderline(line) {
        const res = _super_add_orderline.call(this, line);

        if (line.sale_order_origin_id) {
            const sale_id = line.sale_order_origin_id.id;
            this.sale_id = sale_id;

            if (res) {
                res.is_from_sale_order = true;
            }

            if (line.from_digital_sale === true && res) {
                res.from_digital_sale = true;
            }

            // Evitar duplicar llamadas
            if (!this.x_channel) {
                try {
                    const result = await this.pos.orm.call(
                        "sale.order",
                        "get_order_detail_chatbot",
                        [sale_id]
                    );

                    const orderData = result?.[0] || {};
                    this.x_channel = orderData.x_channel || null;
                    this.pay_deuna_id = orderData.pay_deuna_id || null;
                    this.pay_ahorita_id = orderData.pay_ahorita_id || null;

                } catch (error) {
                    console.error("Error cargando x_channel:", error);
                }
            }

        }

        return res;
    },

});
