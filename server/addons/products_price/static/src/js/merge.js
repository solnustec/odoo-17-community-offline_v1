/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/store/models";
import {
    roundDecimals as round_di,
    roundPrecision as round_pr,
    floatIsZero,
} from "@web/core/utils/numbers";

function normNote(v){
    return (v ?? "").toString().trim();
}

patch(Orderline.prototype, {
    can_be_merged_with(orderline) {
        const r1 = !!this.is_reward_line;
        const r2 = !!orderline.is_reward_line;
        if (r1 !== r2) return false;

        if (this.skipChange) return false;

        if (!this.get_unit() || !this.is_pos_groupable()) return false;

        if (this.get_product().id !== orderline.get_product().id) return false;

        if (normNote(this.getNote?.()) !== normNote(orderline.getNote?.())) return false;

        if (normNote(this.get_customer_note?.()) !== normNote(orderline.get_customer_note?.())) return false;

        if (this.refunded_orderline_id) return false;

        if (this.isPartOfCombo?.() || orderline.isPartOfCombo?.()) return false;

        if (
            this.product.tracking === "lot" &&
            (this.pos.picking_type.use_create_lots || this.pos.picking_type.use_existing_lots)
        ) {
            return false;
        }

        if ((this.full_product_name || "") !== (orderline.full_product_name || "")) return false;


        let hasSameAttributes =
            Object.keys(Object(orderline.attribute_value_ids)).length ===
            Object.keys(Object(this.attribute_value_ids)).length;

        if (
            hasSameAttributes &&
            Object(orderline.attribute_value_ids)?.length &&
            Object(this.attribute_value_ids)?.length
        ) {
            hasSameAttributes = orderline.attribute_value_ids.every(
                (v, i) => v === this.attribute_value_ids[i]
            );
        }

        if (!hasSameAttributes) return false;

        const currencyDP = this.pos.currency.decimal_places;
        const tolDP = Math.min(currencyDP + 1, 6);

//        const unit1 = round_di(this.get_unit_price() || 0, tolDP);
//        const unit2 = round_di(orderline.get_unit_price() || 0, tolDP);

//        const disc1 = round_pr(this.get_discount() || 0, 3);
//        const disc2 = round_pr(orderline.get_discount() || 0, 3);

        const extra1 = round_di(this.get_price_extra?.() || 0, tolDP);
        const extra2 = round_di(orderline.get_price_extra?.() || 0, tolDP);

        const eff1 = round_di(extra1, tolDP);
        const eff2 = round_di(extra2, tolDP);

        return floatIsZero(eff1 - eff2, tolDP);
    },
});
