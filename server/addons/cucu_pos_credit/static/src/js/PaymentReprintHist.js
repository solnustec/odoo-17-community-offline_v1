/** @odoo-module */

import {usePos} from "@point_of_sale/app/store/pos_hook";
import {registry} from "@web/core/registry";
import {Component} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {OrderReceiptReprint} from "./OrderReceiptReprint"

const {onWillStart} = owl;

export class PaymentReprintHist extends Component {
    static template = "cucu_pos_credit.PaymentReprintHist";
    static components = {OrderReceiptReprint};
    static props = ["order"];

    setup() {
        super.setup();
        this.pos = usePos();
        this.printer = useService("printer");
        this.orm = useService("orm");
        onWillStart(async () => {
            this.props.hist_payments = await this.getHist();
        })
    }

    async getHist() {
        debugger
        try {
            const partner = this.props.order.partner_id[0]
            const invoice = {
                name: this.props.order.name,
            }
            return await this.orm.call(
                'pos.create.customer.payment',
                'get_hist_payments',
                [partner ? partner : 0, partner ? partner : 0, invoice],
            )
        } catch (err) {
            console.log(err)
        }
        finally {
            this.env.services.ui.unblock();
        }
    }

    confirm() {
        this.pos.showScreen("ProductScreen");
    }

    tryReprint() {
        this.printer.print(
            OrderReceiptReprint,
            {
                data: this.props,
                formatCurrency: this.env.utils.formatCurrency,
            },
            {webPrintFallback: true}
        );
    }
}

registry.category("pos_screens").add("PaymentReprintHist", PaymentReprintHist);