/** @odoo-module **/

import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {_t} from "@web/core/l10n/translation";

export class RegisterInvoicePaymentPopupWidget extends AbstractAwaitablePopup {
    static template = "cucu_pos_credit.RegisterInvoicePaymentPopupWidget";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
        this.invoice = this.props.invoice;
    }

    cancel() {
        this.props.close({confirmed: false});
    }

    async register_payment() {
        debugger
        const self = this;
        const invoice = this.invoice;
        const partner = invoice.partner_id[0];
        const payment_type = $('#payment_type1').val();
        const entered_amount = $("#entered_amount1").val();
        const entered_note = $("#entered_note1").val();
        let rpc_result = false;
        console.log(this)
        if (entered_amount == '') {
            alert('Please Enter Amount !!!!');
        } else if (entered_amount == 0) {
            alert('Amount should not be zero !!!!');
        } else {
            if (invoice['amount_residual'] >= entered_amount) {
                try {
                    this.env.services.ui.block();
                    await self.orm.call(
                        'pos.create.customer.payment',
                        'create_customer_payment_inv',
                        [partner ? partner : 0, partner ? partner : 0, payment_type, entered_amount, invoice, entered_note, this.pos.pos_session.id],
                    )
                    // alert('Payment has been Registered for this Invoice !!!!');
                    self.props.close({confirmed: false});
                    await this.pos.showScreen('PaymentReprintHist', {
                        'order': {name: invoice.name, partner_id: invoice.partner_id, ...invoice, minus: entered_amount}
                    });
                } catch (err) {
                    console.log(err)
                } finally {
                     this.env.services.ui.unblock();
                }
            } else {
                self.popup.add(ErrorPopup, {
                    'title': _t('Amount Error'),
                    'body': _t('Entered amount is larger then due amount. please enter valid amount'),
                });
            }
        }


    }
}