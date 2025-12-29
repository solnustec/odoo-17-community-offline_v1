/** @odoo-module **/

import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useState} from "@odoo/owl";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.state = useState({
            ...this.state,
        });
        this.pos.isNumpadDisabled = false;
        this.pos.btnDisabled = false;
    },

    addNewPaymentLine(paymentMethod) {
        try {
            const order = this.pos.get_order();
            const existingLine = order.get_paymentlines().find(
                line => line.payment_method.id === paymentMethod.id
            );

            if (existingLine) {
                this.popup.add(ErrorPopup, {
                    title: _t("Método de pago duplicado"),
                    body: _t(`Ya has agregado el método de pago "${paymentMethod.name}". No puedes agregarlo más de una vez.`),
                });
                return;
            }

            const result = super.addNewPaymentLine(paymentMethod);

            if (paymentMethod.type === "cash") {
                this.pos.isNumpadDisabled = false;
            }

            return result;
        } catch (e) {
            console.error("Error en addNewPaymentLine:", e);
        }
    },


    updateSelectedPaymentline(amount = false) {
        if (this.pos.isNumpadDisabled) {
            return;
        }
        super.updateSelectedPaymentline(amount);
    },

    getNumpadButtons() {
        const buttons = super.getNumpadButtons();
        if (this.pos.isNumpadDisabled) {
            return buttons.map(button => ({
                ...button,
                disabled: true,
            }));
        }
        return buttons;
    },

    async validateOrder(isForceValidate) {
        const order = this.pos.get_order();
        const paymentlines = order.get_paymentlines();

        const invalidLine = paymentlines.find(line => line.amount == 0);

        if (invalidLine) {
            const paymentName = invalidLine.payment_method.originalName || invalidLine.payment_method.name;
            await this.popup.add(ErrorPopup, {
                title: _t("Pago inválido"),
                body: _t(`El método de pago "${paymentName}" está con un monto de cero.`),
            });
            return;
        }

        // Continuar con validación original
        await super.validateOrder(isForceValidate);
        localStorage.removeItem("result_institution_client");
    },
    //vaciar el localstorrage al validar la aordern
});
