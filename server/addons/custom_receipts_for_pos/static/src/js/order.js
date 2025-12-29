/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order, Orderline, Product } from "@point_of_sale/app/store/models";

patch(Order.prototype, {

    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        result.total_brute_order = this.get_value_brute();

        return result;
    },

    get_value_brute() {
        return this.orderlines.reduce(function (sum, orderLine) {
            return sum + orderLine.get_all_prices().priceWithTaxBeforeDiscount;
        }, 0);
    }
})