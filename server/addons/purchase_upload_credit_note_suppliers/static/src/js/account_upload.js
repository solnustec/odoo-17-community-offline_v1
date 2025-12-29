/** @odoo-module */

import { AccountMoveListController } from "@account/components/bills_upload/bills_upload";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(AccountMoveListController.prototype, {
    __patch: "credit_note_upload",

    setup() {
        super.setup();
        this.action = useService("action");
    },

    async openCreditNoteUploadWizard() {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Importar Notas de Crédito SRI",
                res_model: "import.sri.credit.note.txt.wizard",
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
            console.error("Error al abrir el wizard de Notas de Crédito SRI:", error);
        }
    },

});