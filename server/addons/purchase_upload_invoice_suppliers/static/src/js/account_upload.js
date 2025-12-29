/** @odoo-module */

import {AccountMoveListController} from "@account/components/bills_upload/bills_upload";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

patch(AccountMoveListController.prototype, {

    setup() {
        super.setup();
        this.action = useService("action");
    },

    async openMovementHistory() {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Importar Facturas SRI",
                res_model: "import.sri.txt.wizard",
                views: [
                    [false, "form"]
                ],
                domain: [],
                context: {
                    multi_select: true,
                },
                target: "new",
            });
        } catch (error) {
            console.log("Error al abrir el Importar Facturas SRI.", error);
        }
    },

})