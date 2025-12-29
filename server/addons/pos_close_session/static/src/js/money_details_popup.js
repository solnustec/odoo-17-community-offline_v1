/** @odoo-module */


import {MoneyDetailsPopup} from "@point_of_sale/app/utils/money_details_popup/money_details_popup";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";

patch(MoneyDetailsPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.pos = usePos();
    },

    async getPayload() {
        const res = await super.getPayload()
        const moneyDetails = res.moneyDetails
        if (moneyDetails) {
            const categorizedTotals = {
                "b100": 0, "b50": 0, "b20": 0, "b10": 0, "b5": 0, "b1": 0, "btotal": 0,
                "m100": 0, "m50": 0, "m25": 0, "m10": 0, "m5": 0, "m1": 0, "mtotal": 0
            };
            Object.entries(moneyDetails).forEach(([key, quantity]) => {
                let value = parseFloat(key)
                if (parseFloat(key) >= 1) {
                    let billKey = `b${value}`;
                    if (categorizedTotals.hasOwnProperty(billKey)) {
                        categorizedTotals[billKey] += quantity;
                    }
                    categorizedTotals["btotal"] += quantity;
                } else {
                    let coinKey;
                    if (parseFloat(key) === 0.99) {
                        coinKey = "m100";
                    } else {
                        coinKey = `m${value * 100}`;
                    }
                    if (categorizedTotals.hasOwnProperty(coinKey)) {
                        categorizedTotals[coinKey] += quantity;
                    }
                    categorizedTotals["mtotal"] += quantity;
                }
            });
            const data = {
                pos_session_id: this.pos.pos_session.id,
                bills_data: categorizedTotals
            };

            const pos_bills_data = await this.orm.search(
                'pos.close.session.bills',
                [['pos_session_id', '=', this.pos.pos_session.id]],
                {limit: 1}
            );

            if (pos_bills_data.length === 0) {
                await this.orm.create('pos.close.session.bills', [data]);
            } else {
                const recordId = pos_bills_data[0];
                if (recordId) {

                    await this.orm.write('pos.close.session.bills', [recordId], {bills_data: categorizedTotals});
                } else {
                    console.error("Error: No se encontró un ID válido para actualizar");
                }
            }

        }
        let moneyDetailsNotesFixed = ""
        this.pos.bills.forEach((bill) => {
            if (this.state.moneyDetails[bill.value]) {
                if (bill.value === 0.99) {
                    moneyDetailsNotesFixed += `  - ${
                        this.state.moneyDetails[bill.value]
                    } Moneda(s) (1 dolar) \n`;
                } else if (bill.value >= 1) {
                    moneyDetailsNotesFixed += `  - ${
                        this.state.moneyDetails[bill.value]
                    }  Billete(s) ${this.env.utils.formatCurrency(bill.value)} \n`;
                } else {
                    moneyDetailsNotesFixed += `  - ${
                        this.state.moneyDetails[bill.value]
                    }  Moneda(s) ${this.env.utils.formatCurrency(bill.value)} \n`;
                }
            }
        });
        res.moneyDetailsNotes = moneyDetailsNotesFixed
        return res
    },

})