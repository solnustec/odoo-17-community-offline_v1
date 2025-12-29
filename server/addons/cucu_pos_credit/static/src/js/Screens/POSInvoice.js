/** @odoo-module */

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {useAsyncLockedMethod} from "@point_of_sale/app/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {Component} from "@odoo/owl";
import {PosInvoiceDetail} from '../Popup/PosInvoiceDetail'
import {PaymentReprintHist} from '../PaymentReprintHist'
export class POSInvoice extends Component {
    static template = "cucu_pos_credit.POSInvoice";
    static defaultProps = {
        order: {}
    };

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    async onClickPosOrder(order) {
        await this.showDetails(order)
    }

    async showDetails(order) {
        await this.popup.add(PosInvoiceDetail, {'order': order});
    }

    get highlight() {
        return this.props.order !== this.props.selectedPosOrder ? '' : 'highlight';
    }

    async onClickReprint(order) {
        await this.pos.showScreen('PaymentReprintHist', {'order': order});
    }
}

registry.category("pos_screens").add("POSInvoice", POSInvoice);
