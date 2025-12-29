/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { Order } from "@point_of_sale/app/store/models";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(loadedData);
        this.promotions =
            (this.modelByName?.["promotions_by_day.promotions_by_day"]) ||
            (loadedData?.["promotions_by_day.promotions_by_day"]) ||
            [];
        console.log("✅ Promociones cargadas en POS:", this.promotions);
    },
    getWeekdayPromoPercent() {
        const promos = this.promotions || [];
        let today = new Date().getDay(); // 0=Dom,6=Sáb
        today = today === 0 ? 6 : today - 1; // 0=Lun,6=Dom
        for (const p of promos) {
            const w = (p.weekday === false) ? null : Number.parseInt(p.weekday);
            if (p.active && (w === null || w === today)) {
                return Number(p.discount_percent) || 0;
            }
        }
        return 0;
    },
});
