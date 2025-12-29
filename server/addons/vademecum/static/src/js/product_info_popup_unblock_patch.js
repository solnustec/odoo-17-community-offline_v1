/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { unblockUI } from "./product_info_loading_block";
import { ProductInfoPopup } from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";

const originalPopupSetup = ProductInfoPopup.prototype.setup;

patch(ProductInfoPopup.prototype, {
    setup() {
        if (originalPopupSetup) {
            originalPopupSetup.call(this, ...arguments);
        }

        this.ui = useService("ui");

        onMounted(() => {
            unblockUI(this.ui);
        });

        onWillUnmount(() => {
            unblockUI(this.ui);
        });
    },
});
