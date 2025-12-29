/** @odoo-module **/

import { MoneyDetailsPopup } from "@point_of_sale/app/utils/money_details_popup/money_details_popup";
import { patch } from "@web/core/utils/patch";

// Denominaciones a ocultar
const BLOCKED = [200, 0.20, 0.02];

function normalize(value, dp) {
    const n = parseFloat(value);
    const m = Math.pow(10, dp);
    return Math.round(n * m) / m;
}

const superSetup = MoneyDetailsPopup.prototype.setup;

patch(MoneyDetailsPopup.prototype, {
    setup() {
        // Llama al original
        superSetup.call(this);

        const dp = this.pos?.currency?.decimal_places ?? 2;
        const blocked = new Set(BLOCKED.map((v) => normalize(v, dp)));
        const shouldSkip = (v) => blocked.has(normalize(v, dp));

        if (this.props.moneyDetails) {
            // Si viene preconstruido (p.ej. re-apertura), filtramos las llaves
            const filtered = Object.entries(this.props.moneyDetails).filter(
                ([val]) => !shouldSkip(val)
            );
            this.state.moneyDetails = Object.fromEntries(filtered);
        } else {
            // Caso típico: se arma desde pos.bills; filtramos aquí
            const filteredBills = (this.pos?.bills || []).filter((b) => !shouldSkip(b.value));
            this.state.moneyDetails = Object.fromEntries(filteredBills.map((b) => [b.value, 0]));
        }

    },
});
