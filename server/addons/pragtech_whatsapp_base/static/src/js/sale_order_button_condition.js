/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { onMounted } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";

patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        const pos = usePos();

        // Ejecuta cuando el componente ya está montado
        onMounted(() => {
            const btn = document.querySelector('.o_sale_order_button');
            if (btn && !pos.config.show_sale_order_button) {
                btn.style.display = 'none';
            }
        });
    },
});
