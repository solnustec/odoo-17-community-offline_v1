/** @odoo-module **/

import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

patch(PaymentScreen.prototype, {

    // validar que en la ordenes si son de rembolso, pida obligatoriamente la nota de factura

    async validateOrder(isForceValidate) {

        const order = this.pos?.get_order()

        if (order && order.get_orderlines()[0]?.refunded_orderline_id){
            const invoice_note = order.get_invoice_note()
            if (!invoice_note){

                const {confirmed} = await this.env.services.popup.add(ConfirmPopup, {
                    title: "Nota requerida",
                    body: "Por favor, añade una nota antes de continuar con el reembolso."
                });

                if (confirmed) {
                    this.pos?.openInvoiceNotePopup?.openInvoiceNotePopup();
                }
                return;
            }
        }

        return await super.validateOrder(...arguments);

    },


});
