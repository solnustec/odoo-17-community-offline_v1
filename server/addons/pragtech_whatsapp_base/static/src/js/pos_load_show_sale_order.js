/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        const configList = loadedData?.["pos.config"] || [];
        this._showSaleButtonTemp =
            Array.isArray(configList) &&
            configList.length &&
            typeof configList[0].show_sale_order_button !== "undefined"
                ? !!configList[0].show_sale_order_button
                : false;
    },

    async _afterLoadServerData() {
        await super._afterLoadServerData(...arguments);

        if (this.config) {
            this.config.show_sale_order_button = this._showSaleButtonTemp || false;
        }
    },
});
