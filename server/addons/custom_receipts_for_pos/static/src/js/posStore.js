/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        // Load coupon BIN TC patterns for coupon duplication
        this.coupon_bin_tc = loadedData['coupon_bin_tc'] || [];
    },
});
