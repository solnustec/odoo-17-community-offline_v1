/** @odoo-module */

import {TicketScreen} from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import {patch} from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    setPartnerToRefundOrder(partner, destinationOrder) {
        if (this.pos.isEcuadorianCompany()) {
            if (
                partner &&
                (!destinationOrder.get_partner() ||
                    destinationOrder.get_partner().id === this.pos.finalConsumerId)
            ) {
                destinationOrder.set_partner(partner);
            }
        } else {
            super.setPartnerToRefundOrder(...arguments);
        }
    },

    onClickOrder(clickedOrder) {
        this._state.ui.selectedOrder = clickedOrder;
        this.numberBuffer.reset();
        if ((!clickedOrder || clickedOrder.locked) && !this.getSelectedOrderlineId()) {
            // Automatically select the first orderline of the selected order.
            const firstLine = this._state.ui.selectedOrder.get_orderlines()[0];
            if (firstLine) {
                this._state.ui.selectedOrderlineIds[clickedOrder.backendId] = firstLine.id;
            }
        }
    },
});
