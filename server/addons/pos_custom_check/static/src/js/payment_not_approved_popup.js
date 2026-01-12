/** @odoo-module */

import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {_t} from "@web/core/l10n/translation";

/**
 * Popup para pagos digitales no aprobados.
 * Ofrece opciones: Validar estado, Autorizar con PIN, Cancelar
 */
export class PaymentNotApprovedPopup extends AbstractAwaitablePopup {
    static template = "pos_custom_check.PaymentNotApprovedPopup";
    static defaultProps = {
        title: _t("Pago no aprobado"),
        body: _t("La transacción aún no ha sido aprobada."),
        retryText: _t("Validar estado"),
        authorizeText: _t("Autorizar con PIN"),
        cancelText: _t("Cancelar"),
    };

    setup() {
        super.setup();
    }

    async onRetry() {
        this.props.close({confirmed: true, action: 'retry'});
    }

    async onAuthorize() {
        this.props.close({confirmed: true, action: 'authorize'});
    }

    async onCancel() {
        this.props.close({confirmed: false, action: 'cancel'});
    }
}
