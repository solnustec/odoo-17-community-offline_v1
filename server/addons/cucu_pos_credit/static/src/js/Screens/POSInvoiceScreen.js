/** @odoo-module */
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {debounce} from "@web/core/utils/timing";
import {useService} from "@web/core/utils/hooks";
import {useAsyncLockedMethod} from "@point_of_sale/app/utils/hooks";
import {session} from "@web/session";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {Component, onWillUnmount, useRef, useState} from "@odoo/owl";
import {POSInvoice} from "./POSInvoice";
import {PosInvoiceDetail} from "@cucu_pos_credit/js/Popup/PosInvoiceDetail";
import {OfflineErrorPopup} from "@point_of_sale/app/errors/popups/offline_error_popup";

export class POSInvoiceScreen extends Component {
    static components = {POSInvoice};
    static template = "cucu_pos_credit.POSInvoiceScreen";
    static defaultProps = {
        invoices: []
    };

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
        this.ui = useState(useService("ui"));
        this.state = {
            query: null,
            selectedPosOrder: this.props.partner,
        };
    }

    back() {
        this.pos.showScreen("ProductScreen");
    }

    get invoices() {
        return this.props.invoices
    }

    async showDetails(invoices) {
        let self = this;
        let o_id = invoices.id;
        let orders = self.orders;
        let orderlines = self.orderlines;
        let orders1 = [invoices];

        let pos_lines = [];

        for (let n = 0; n < orderlines.length; n++) {
            if (orderlines[n]['move_id'][0] == o_id) {
                pos_lines.push(orderlines[n])
            }
        }
        await this.popup.add(PosInvoiceDetail, {'order': invoices, 'orderline': pos_lines,});
    }
}

registry.category("pos_screens").add("POSInvoiceScreen", POSInvoiceScreen);