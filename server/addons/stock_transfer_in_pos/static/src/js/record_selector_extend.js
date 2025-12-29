/** @odoo-module **/

import { RecordSelector } from "@web/core/record_selectors/record_selector";

export class RecordSelectorReadonly extends RecordSelector {
    static props = {
        ...RecordSelector.props,
        readonly: { type: Boolean, optional: true },
    };

    static template = "stock_transfer_in_pos.RecordSelectorReadonly";
}