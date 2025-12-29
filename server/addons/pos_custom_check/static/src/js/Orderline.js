/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/store/models";

patch(Orderline.prototype, {
    setup() {
        super.setup(...arguments);
        this.selected = false;
        this.is_selectionable = false;
        this.price_original = this.product.get_price(this.order.pricelist, this.get_quantity())
        this.amount_applied = 0;
        this.quantity_applied = 0;
    },

    init_from_JSON(json) {
        this.reward_product_id = json.reward_product_id;
        super.init_from_JSON(...arguments);
    },

    set_reward_product_id(reward_product_id) {
        this.reward_product_id = reward_product_id;
    },

    set_original_id_reward(original_id_reward) {
        this.original_id_reward = original_id_reward;
    },

    set_amount_applied(amount_applied) {
        this.amount_applied = amount_applied;
    },

    set_percent_discount(percent_discount) {
        this.percent_discount = percent_discount;
    },

    get_percent_discount(){
        return this.percent_discount;
    },

    get_total_with_discount(){
        return this.total_with_discount;
    },

    set_total_with_discount(total_with_discount){
        this.total_with_discount = this.env.utils.formatCurrency(total_with_discount);
    },

    isGiftCardOrEWalletReward() {
        const coupon = this.pos.couponCache[this.coupon_id];
        if (!coupon || !this.is_reward_line) {
            return false;
        }
        const program = this.pos.program_by_id[coupon.program_id];
        if(!program){
            return false;
        }
        return ["ewallet", "gift_card"].includes(program.program_type);
    },

//    set_unit_price(price) {
//        this.order.assert_editable();
//        var parsed_price = !isNaN(price)
//            ? price
//            : isNaN(parseFloat(price))
//            ? 0
//            : oParseFloat("" + price);
//        this.price = parsed_price || 0;
//    }

    set_unit_price(price) {
        // Evitar excepción si la orden ya fue finalizada
        if (this.order && typeof this.order.assert_editable === 'function') {
            try {
                this.order.assert_editable();
            } catch (err) {
                console.warn('Order not editable, skipping price change:', err);
                return;
            }
        }

        this.order.assert_editable && this.order.assert_editable(); // seguridad si existe

        var parsed_price = !isNaN(price)
            ? price
            : isNaN(parseFloat(price))
            ? 0
            : oParseFloat("" + price);
        this.price = parsed_price || 0; // Sin redondeo aquí
    }
})
