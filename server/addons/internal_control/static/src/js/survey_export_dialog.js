/** @odoo-module */

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useChildRef } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

// Extended dialog component with observations field
export class SurveyExportDialog extends Component {
    setup() {
        this.env.dialogData.dismiss = () => this._cancel();
        this.modalRef = useChildRef();
        this.isProcess = false;
        this.observations = "";
    }

    async _cancel() {
        return this.execButton(this.props.cancel);
    }

    async _confirm() {
        // Pass observations to the confirm callback
        if (this.props.confirm) {
            this.props.confirm(this.observations);
        }
        return this.execButton(this.props.confirm);
    }

    setButtonsDisabled(disabled) {
        this.isProcess = disabled;
        if (!this.modalRef.el) {
            return;
        }
        for (const button of [...this.modalRef.el.querySelectorAll(".modal-footer button")]) {
            button.disabled = disabled;
        }
    }

    async execButton(callback) {
        if (this.isProcess) {
            return;
        }
        this.setButtonsDisabled(true);
        if (callback) {
            let shouldClose;
            try {
                shouldClose = await callback();
            } catch (e) {
                this.props.close();
                throw e;
            }
            if (shouldClose === false) {
                this.setButtonsDisabled(false);
                return;
            }
        }
        this.props.close();
    }

    onObservationsChange(ev) {
        this.observations = ev.target.value;
    }
}

// Setting properties of SurveyExportDialog
SurveyExportDialog.template = "SurveyExportDialog.List";
SurveyExportDialog.components = { Dialog };
SurveyExportDialog.props = {
    close: Function,
    title: {
        validate: (m) => {
            return (
                typeof m === "string" || (typeof m === "object" && typeof m.toString === "function")
            );
        },
        optional: true,
    },
    body: String,
    exportedFields: { type: Array, optional: true },
    confirm: { type: Function, optional: true },
    confirmLabel: { type: String, optional: true },
    confirmClass: { type: String, optional: true },
    cancel: { type: Function, optional: true },
    cancelLabel: { type: String, optional: true },
};
SurveyExportDialog.defaultProps = {
    confirmLabel: _t("Exportar"),
    cancelLabel: _t("Cancelar"),
    confirmClass: "btn-primary",
                title: _t("Exportar Métricas de Encuesta PDF"),
}; 