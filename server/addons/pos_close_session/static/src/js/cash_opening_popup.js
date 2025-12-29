/** @odoo-module */

import { CashOpeningPopup } from "@point_of_sale/app/store/cash_opening_popup/cash_opening_popup";
import { patch } from "@web/core/utils/patch";
import { parseFloat as odooParseFloat } from "@web/views/fields/parsers";


patch(CashOpeningPopup.prototype, {

    /**
     * Normaliza el valor decimal para el locale de Ecuador.
     * Convierte punto a coma ya que parseFloat de Odoo usa coma como separador decimal.
     * @param {string} value - El valor a normalizar
     * @returns {string} - El valor con coma como separador decimal
     */
    normalizeForOdooLocale(value) {
        if (typeof value !== 'string') {
            value = String(value || '0');
        }
        // Si tiene punto, convertir a coma para el locale Ecuador
        if (value.includes('.')) {
            return value.replace('.', ',');
        }
        return value;
    },

    /**
     * Valida si un valor es un número flotante válido (acepta coma o punto).
     */
    isValidDecimalInput(value) {
        if (typeof value !== 'string') {
            value = String(value || '0');
        }
        // Normalizar a punto para validación con parseFloat nativo
        const normalized = value.replace(',', '.');
        const num = parseFloat(normalized);
        return !isNaN(num) && isFinite(num);
    },

    /**
     * Override confirm para normalizar el valor antes de enviarlo al servidor.
     */
    async confirm() {
        // Normalizar el valor de apertura: punto → coma para parseFloat de Odoo
        const normalizedValue = this.normalizeForOdooLocale(this.state.openingCash);

        this.pos.pos_session.state = "opened";
        this.orm.call("pos.session", "set_cashbox_pos", [
            this.pos.pos_session.id,
            odooParseFloat(normalizedValue),
            this.state.notes,
        ]);

        // Llamar al confirm del AbstractAwaitablePopup (el padre del padre)
        this.props.close({ confirmed: true, payload: await this.getPayload() });
    },

    /**
     * Override handleInputChange para validar con soporte de coma y punto.
     */
    handleInputChange() {
        if (!this.isValidDecimalInput(this.state.openingCash)) {
            return;
        }
        this.state.notes = "";
    }

});
