/** @odoo-module **/


import {PosStore} from "@point_of_sale/app/store/pos_store";
import {patch} from "@web/core/utils/patch";

patch(PosStore.prototype, {
    removeOrder(order, removeFromServer = true) {
        if (order?.payment_key === 'fact_credit') {
            order.pos.db.partner_by_id[order.partner.id].to_credit = true
        }
        super.removeOrder(order, removeFromServer)
    }
})
