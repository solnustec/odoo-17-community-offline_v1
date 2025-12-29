/** @odoo-module **/

import {Component} from "@odoo/owl";
import {omit} from "@web/core/utils/objects";

export class OrderReceiptReprint extends Component {
    static template = "cucu_pos_credit.OrderReceiptReprint";
    static props = {
        data: Object,
        formatCurrency: Function,
    };

    setup(){
        super.setup()
        console.log(this)
    }
    formatCurrency(amount){
        return this.env.utils.formatCurrency(amount)
    }
    omit(...args) {
        return omit(...args);
    }
}