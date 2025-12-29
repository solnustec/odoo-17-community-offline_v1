/** @odoo-module */
/* global Sha1 */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { ConfirmPop } from "@pos_close_session/popups/confirmed";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";


patch(ClosePosPopup.prototype, {

    /**
     * Parsea un valor decimal, aceptando tanto punto (.) como coma (,) como separador.
     * @param {string} value - El valor a parsear
     * @returns {number} - El valor numérico parseado
     */
    parseDecimalInput(value) {
        if (typeof value !== 'string') {
            value = String(value || '0');
        }
        // Reemplazar coma por punto solo para el parseo
        return parseFloat(value.replace(',', '.'));
    },

    /**
     * Valida si un valor es un número flotante válido (acepta coma o punto).
     */
    isValidDecimalInput(value) {
        const num = this.parseDecimalInput(value);
        return !isNaN(num) && isFinite(num);
    },

    /**
     * Override getDifference para aceptar coma como separador decimal.
     */
    getDifference(paymentId) {
        const counted = this.state.payments[paymentId]?.counted || "0";

        if (!this.isValidDecimalInput(counted)) {
            return NaN;
        }

        const expectedAmount =
            paymentId === this.props.default_cash_details?.id
                ? this.props.default_cash_details.amount
                : this.props.other_payment_methods.find((pm) => pm.id === paymentId)?.amount || 0;

        return this.parseDecimalInput(counted) - expectedAmount;
    },

    /**
     * Override canConfirm para validar con soporte de coma.
     */
    canConfirm() {
        return Object.values(this.state.payments)
            .map((v) => v.counted)
            .every((value) => this.isValidDecimalInput(value));
    },

    async closeSession() {
        const cashier = this.pos?.get_cashier();
        if (!cashier) return;

        // Normalizar el valor del efectivo: punto → coma para que parseFloat de Odoo lo interprete correctamente
        // En Ecuador: coma es decimal, punto es miles. Si usuario ingresa "14.10", convertir a "14,10"
        if (this.props.default_cash_details?.id && this.state.payments[this.props.default_cash_details.id]) {
            const currentValue = this.state.payments[this.props.default_cash_details.id].counted;
            if (typeof currentValue === 'string' && currentValue.includes('.')) {
                this.state.payments[this.props.default_cash_details.id].counted = currentValue.replace('.', ',');
            }
        }

        const cashierHash = cashier.barcode;
        const employee = this.pos.employees.find(emp => emp.barcode === cashierHash);
        if (employee && (!employee.pin || await this.checkPin(employee))) {
            const { confirmed } = await this.popup.add(ConfirmPop, {
                title: "¿Qué desea hacer con la sesión actual del sistema?",
                body: _t(
                    'Al elegir CERRAR SISTEMA, se finalizará la sesión actual, se registrarán las diferencias de pago y se cerrará completamente la plataforma.\n\n' +
                    'Esto cerrará tu sesión de usuario y deberás volver a iniciar sesión para continuar.\n\n' +
                    'Si deseas seguir trabajando en el sistema, selecciona PANEL ADMINISTRATIVO.'
                )
            });

            if (!confirmed) {
                return super.closeSession();
            }
            this.pos.is_close_total = true
            return super.closeSession();
        } else {
            return
        }
    },

    async checkPin(employee) {
        const { confirmed, payload: inputPin } = await this.popup.add(NumberPopup, {
            isPassword: true,
            title: _t("Password?"),
        });

        if (!confirmed) {
            return false;
        }

        if (employee.pin !== Sha1.hash(inputPin)) {
            await this.popup.add(ErrorPopup, {
                title: _t("Incorrect Password"),
                body: _t("Please try again."),
            });
            return false;
        }
        return true;
    }

});
