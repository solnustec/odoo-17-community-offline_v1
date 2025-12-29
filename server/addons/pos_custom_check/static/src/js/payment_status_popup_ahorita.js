/** @odoo-module */

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";

export class PaymentStatusAhoritaPopup extends AbstractAwaitablePopup {
    static template = "pos_custom_check.PaymentStatusAhoritaPopup";

    setup() {
        super.setup();
    }
}