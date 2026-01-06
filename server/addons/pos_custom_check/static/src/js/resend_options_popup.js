/** @odoo-module */

import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {_t} from "@web/core/l10n/translation";

/**
 * Popup con opciones para manejar reenvío de links de pago:
 * - Reenviar link actual por WhatsApp
 * - Cancelar
 */
export class ResendOptionsPopup extends AbstractAwaitablePopup {
    static template = "pos_custom_check.ResendOptionsPopup";
    static defaultProps = {
        title: _t("Link de pago existente"),
        body: _t("Ya existe un link de pago generado para esta transacción."),
        resendCurrentText: _t("Reenviar link actual"),
        cancelText: _t("Cancelar"),
    };

    setup() {
        super.setup();
    }

    /**
     * Usuario quiere reenviar el link actual por WhatsApp
     */
    async onResendCurrent() {
        this.props.close({confirmed: true, action: 'resend_current'});
    }

    /**
     * Usuario cancela la operación
     */
    async onCancel() {
        this.props.close({confirmed: false, action: 'cancel'});
    }
}
