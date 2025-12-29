/** @odoo-module **/
import { Component } from "@odoo/owl";

export class PopupVademecum extends Component {
    static template = "vademecum.OrderLineDisplay";
    static props = {
        medicines: { type: Array },
        close: { type: Function, optional: true },
        selectMedicine: { type: Function } 
    };
}


