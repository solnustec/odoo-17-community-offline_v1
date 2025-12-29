/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {

    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        result.sri_authorization = this.sri_authorization;
        return result;
    },

    set_sri_authorization(sri_authorization) {
        this.sri_authorization = sri_authorization;
    },


    init_from_JSON(json) {
        this.sri_authorization = json.sri_authorization;
        super.init_from_JSON(...arguments);
      },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.sri_authorization = this.sri_authorization || null;
        return json;
    },

})