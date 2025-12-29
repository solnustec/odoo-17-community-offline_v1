/* @odoo-module */
import {patch} from "@web/core/utils/patch";
import {TicketScreen} from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import {useService} from "@web/core/utils/hooks";
import {PopupSriSearch} from "./modalSri";

patch(TicketScreen.prototype, {
    setup() {
        this.pos = this.env.pos;
        this.popup = useService("popup");
        this.orm = useService("orm");
        super.setup();
    },

    btnSriSearch() {
        this.popup.add(PopupSriSearch);
    },

});

