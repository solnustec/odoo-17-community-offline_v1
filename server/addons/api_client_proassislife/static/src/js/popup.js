/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";

export class PopupGetApi extends AbstractAwaitablePopup {
    static template = "api_client_proassislife.OrderLinePopup";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.contractData = this.props.contractData || [];
        this.isLoading = false;
    }

    confirm() {
        console.log("Confirmación realizada");
    }

    cancel() {
        this.props.close({ confirmed: false, payload: null });
    }
}
