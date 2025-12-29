/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { RegisterInvoicePaymentPopupWidget } from "@cucu_pos_credit/js/Popup/RegisterInvoicePaymentPopupWidget"

export class PosInvoiceDetail extends AbstractAwaitablePopup {
    static template = "cucu_pos_credit.PosInvoiceDetail";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
    }

    go_back_screen() {
		this.props.close({ confirmed: false});
		this.pos.showScreen('ProductScreen');
	}

	async register_payment() {
		this.props.close({ confirmed: false});
		this.popup.add(RegisterInvoicePaymentPopupWidget, {'invoice': this.props.order});
	}
}