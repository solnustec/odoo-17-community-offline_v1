/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

const originalProductScreenSetup = ProductScreen.prototype.setup;

let failSafeTimer = null;
function blockUI(ui, ms = 10000) {
    if (!ui._infoBlockCount) ui._infoBlockCount = 0;
    ui._infoBlockCount++;
    ui.block();
    clearTimeout(failSafeTimer);
    failSafeTimer = setTimeout(() => {
        if (ui._infoBlockCount > 0) {
            ui._infoBlockCount = 0;
            ui.unblock();
        }
    }, ms);
}
function unblockUI(ui) {
    if (!ui._infoBlockCount) ui._infoBlockCount = 0;
    ui._infoBlockCount = Math.max(0, ui._infoBlockCount - 1);
    if (ui._infoBlockCount === 0) {
        clearTimeout(failSafeTimer);
        ui.unblock();
    }
}

patch(ProductScreen.prototype, {
    setup() {
        if (originalProductScreenSetup) {
            originalProductScreenSetup.call(this, ...arguments);
        }

        this.ui = useService("ui");

        this._infoClick = (ev) => {
            const tag = ev.target.closest?.(".product-information-tag");
            if (tag) {
                blockUI(this.ui, 10000);
            }
        };

        onMounted(() => {
            document.addEventListener("click", this._infoClick, true);
        });
        onWillUnmount(() => {
            document.removeEventListener("click", this._infoClick, true);
        });
    },
});

export { blockUI, unblockUI };
