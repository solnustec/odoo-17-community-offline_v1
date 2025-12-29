/** @odoo-module **/

import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {useService} from "@web/core/utils/hooks";
import {Component} from "@odoo/owl";
import {usePos} from "@point_of_sale/app/store/pos_hook";


export class SeeAllInvoicesButtonWidget extends Component {
    static template = "cucu_pos_credit.SeeAllInvoicesButtonWidget";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
    }

    async getMoves() {
        try {
            const moves = await this.orm.call("pos.order", 'get_moves_partner_all', [false]);
            if (moves.length > 0) {
                return moves
            }
            return []
        } catch (error) {
            console.error("ERROR IN SERVICE:", error);
            return [];
        }
    }

    async getMovesSession() {
        try {
            const moves = await this.orm.call("pos.order", 'get_moves_partner_pos_session', [false, this.pos.config.id]);
            if (moves.length > 0) {
                return moves
            }
            return []
        } catch (error) {
            console.error("ERROR IN SERVICE:", error);
            return [];
        }
    }

    async onClickInvoiceCustom() {
        let moves = []
        if (this.pos.config.allow_all_invoices) {
            moves = await this.getMoves()
        } else {
            moves = await this.getMovesSession()
        }
        this.pos.showScreen('POSInvoiceScreen',
            {invoices: moves}
        );
    }
}

ProductScreen.addControlButton({
    component: SeeAllInvoicesButtonWidget,
    condition: function () {
        return this.pos.config.allow_pos_invoice;
    },
});