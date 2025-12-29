/** @odoo-module */

import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { TransferModal } from "./transfers_modal";

patch(Navbar.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },

    openTransferModal() {
        this.pos.popup.add(TransferModal, {
            title: "Gestión de Transferencias",
            zIndex: 1000,
        });
    },
});