/** @odoo-module */

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";

export class ConfirmPop extends AbstractAwaitablePopup {
    static template = "pos_close_session.ConfirmPop";
    static defaultProps = {
        confirmText: _t("Cerrar Sistema"),
        cancelText: _t("Panel Administrativo"),
        title: _t("Confirm?"),
        body: "",
    };
}
