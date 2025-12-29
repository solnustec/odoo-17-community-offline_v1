/** @odoo-module **/

console.log("✅ MÓDULO POS JS CARGADO: load_orders_today.js");

import {PosStore} from "@point_of_sale/app/store/pos_store";
import {patch} from "@web/core/utils/patch";
import moment from "moment";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(loadedData);

        const recentOrders = await this.env.services.rpc({
            model: 'pos.order',
            method: 'search_read',
            args: [
                [['date_order', '>=', moment().subtract(3, 'days').format()]],
                ['name', 'amount_total', 'state', 'date_order', 'pos_reference']
            ],
            limit: 200,
        });

        console.log("✅ Órdenes cargadas desde backend:", recentOrders.length);
        this.db.add_orders(recentOrders);
        this.pos_orders = recentOrders;
    }
});
