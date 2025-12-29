/** @odoo-module */

import {PartnerListScreen} from "@point_of_sale/app/screens/partner_list/partner_list";
import {PartnerLine} from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import {patch} from "@web/core/utils/patch";
import {Component, onWillStart, useExternalListener, useState} from '@odoo/owl';
import {useService} from "@web/core/utils/hooks";
import {RegisterPaymentPopupWidget} from "@cucu_pos_credit/js/Popup/RegisterPaymentPopupWidget";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {
    ClosePosPopup
} from "@point_of_sale/app/navbar/closing_popup/closing_popup";

patch(PartnerListScreen.prototype, {
    setup() {
        super.setup();
        this.popup = useService("popup");
    },
    async getMoves(method, id) {
        try {
            const moves = await this.orm.call("pos.order", method, [false, id]);
            if (moves.length > 0) {
                return moves
            }
            return []
        } catch (error) {
            console.error("ERROR IN SERVICE:", error);
            return [];
        }
    },
    async registerPayment(partner) {
        const moves = await this.getMoves('get_moves_partner', partner.id)
        this.pos.showScreen('POSInvoiceScreen',
            {invoices: moves}
        );
        // this.popup.add(RegisterPaymentPopupWidget, {'partner': partner});
    },

});

patch(PartnerLine.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
});

patch(ClosePosPopup.prototype, {
    async setup() {
        super.setup()

        onWillStart(async () => {
            this.props.customer_payments = await this.getPayments();
        })
    },
    async getPayments() {
        try {
            const payments = await this.orm.call("pos.order", 'get_payments_session_id', [false, this.pos.pos_session.id]);
            const reMap = []
            if (payments.length > 0) {
                payments.forEach(payment => {
                    reMap[payment.payment_type] = (reMap[payment.payment_type] || 0) + payment.amount
                })
                console.log(reMap)
                return reMap
            }
            return []
        } catch (error) {
            console.error("ERROR IN SERVICE:", error);
            return 0;
        }
    },
})