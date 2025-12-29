/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    set_invoice_note(note) {
        this.invoice_note = note;
    },
    get_invoice_note() {
        return this.invoice_note || "";
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.invoice_note = this.get_invoice_note();
        return json;
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.invoice_note = json.invoice_note || "";
    },
    export_for_printing() {
        const res = super.export_for_printing(...arguments);
        res.invoice_note = this.get_invoice_note();
        return res;
    },
});

