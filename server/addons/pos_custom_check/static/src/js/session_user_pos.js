/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {Order} from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.real_user_id = this.env.services.user.userId;
        return json;
    }
});
