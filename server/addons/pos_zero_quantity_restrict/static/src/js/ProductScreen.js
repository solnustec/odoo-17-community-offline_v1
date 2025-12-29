/** @odoo-module */

import {Order} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";

patch(Order.prototype, {
    /**
     * Patched version of the pay method for the Order class.
     * Validates that a client is selected and that all order lines have quantity > 0.
     * Shows error popups if any validation fails.
     */
    async pay() {
        const orderLines = this.get_orderlines();
        const quantity = orderLines.map(line => line.quantity);

        if (quantity.includes(0)) {
            this.env.services.popup.add(ErrorPopup, {
                title: 'Error',
                body: 'Hay un producto con una cantidad de 0. Por favor, cambie la cantidad del producto para poder procesar el pago.',
            });
            return;
        }

        const total = this.get_total_with_tax();

        if (total <= 0.05 && total >= 0) {
            this.env.services.popup.add(ErrorPopup, {
                title: 'Monto inválido',
                body: 'Para realizar la venta el monto total debe ser mayor a $0.05.',
            });
            return;
        }

        return super.pay(...arguments);
    },
});

