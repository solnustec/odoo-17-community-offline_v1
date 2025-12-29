/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    _hasRewardLinkedToProduct(productId) {
        const rewardLines = this._get_reward_lines_custom?.() || this.get_orderlines();
        return rewardLines.some((l) =>
            (l.is_reward_line || l.reward_product_id) &&
            (l.reward_prod_id === productId || l.reward_product_id === productId)
        );
    },
});
