/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        let printTriggered = false;

        // Definimos la función aquí para poder eliminarla luego correctamente
        const handleFocus = () => {
            if (printTriggered) {
                const newOrderBtn = document.querySelector('button[name="done"]');
                if (newOrderBtn) {
                    newOrderBtn.click();
                }
                printTriggered = false;
            }
        };

        onMounted(() => {
            const printBtn = document.querySelector('.button.print');
            if (printBtn) {
                printTriggered = true;
                printBtn.click();
            }
            window.addEventListener('focus', handleFocus);
        });

        onWillUnmount(() => {
            window.removeEventListener('focus', handleFocus);
        });
    },
});
