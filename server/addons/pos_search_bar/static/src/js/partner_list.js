/** @odoo-module **/

import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";

patch(PartnerListScreen.prototype, {
    async updatePartnerList(event) {
        this.state.query = event.target.value;
        if (event.key === 'Enter') {
            this.searchPartner();
        }
    }
})