/** @odoo-module */

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";

export class OkeyPopup extends AbstractAwaitablePopup {
    static template = "point_of_sale.OkeyPopup";
    static defaultProps = {
        cancelText: _t("Ok"),
        title: _t("Confirm?"),
        body: "",
    };
}
