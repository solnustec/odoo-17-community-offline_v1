/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { TextAreaPopup } from "@point_of_sale/app/utils/input_popups/textarea_popup";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import { useState } from "@odoo/owl";


patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.currentOrder.set_to_invoice(true);
        this.pos.openInvoiceNotePopup = this;

    },
    async openInvoiceNotePopup() {
        const { confirmed, payload } = await this.popup.add(TextAreaPopup, {
            title: _t("Nota de Factura"),
            startingValue: this.currentOrder.get_invoice_note() || "",
            confirmText: _t("Guardar"),
            cancelText: _t("Cancelar"),
        });

        if (confirmed) {
            this.currentOrder.set_invoice_note(payload);
        }
    },
});
