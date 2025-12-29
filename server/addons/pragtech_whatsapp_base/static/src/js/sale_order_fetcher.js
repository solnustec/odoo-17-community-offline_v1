/** @odoo-module **/

import { registry } from "@web/core/registry";

const originalService = registry.category("services").get("sale_order_fetcher");
const oldStart = originalService.start;

originalService.start = function(env, deps) {
    const fetcher = oldStart.call(this, env, deps);

    fetcher._getOrderIdsForCurrentPage = async function(limit, offset) {
        const domain = [["currency_id", "=", this.pos.currency.id]].concat(
            this.searchDomain || []
        );

        this.pos.set_synch("connecting");
        const saleOrders = await this.orm.searchRead(
            "sale.order",
            domain,
            [
                "name",
                "partner_id",
                "amount_total",
                "date_order",
                "state",
                "user_id",
                "amount_unpaid",
                "x_channel",
                "digital_media"
            ],
            { offset, limit }
        );

        this.pos.set_synch("connected");
        return saleOrders;
    };

    return fetcher;
};
