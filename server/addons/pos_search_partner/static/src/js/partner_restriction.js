// /** @odoo-module **/
//
// import { patch } from "@web/core/utils/patch";
// import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
//
// patch(ActionpadWidget.prototype, {
//     getMainButtonClasses() {
//         const base = "button btn d-flex flex-column flex-fill align-items-center justify-content-center fw-bolder btn-lg rounded-0";
//         const order = this.pos.get_order?.();
//         const hasPartner = !!order?.get_partner?.();
//
//         const extra = hasPartner ? "" : " disabled opacity-50 pe-none";
//         return base + extra;
//     },
// });
