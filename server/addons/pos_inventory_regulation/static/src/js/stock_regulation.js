/** @odoo-module **/
/**
 * This file is used to register the a new button for stock transfer
 */

import {Component} from "@odoo/owl";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {CreateRegulationPopup} from "./regulation_create_popup";
import {useService} from "@web/core/utils/hooks";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";


class StockRegulationButton extends Component {
    static template = 'StockRegulationButton';

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.pos = usePos();
        this.popup = useService("popup");
        this.notificationService = useService("notification");
    }

    async onClick() {
        let self = this
        try {
            await this.orm.call(
                "pos.config", "get_stock_transfer_list_api", [], {
                    "stock_picking_type_id": this.pos.picking_type.id,
                    "sync_data": this.pos.config.sync_data
                }
            ).then(function (result) {
                if (!result.success) {
                    self.pos.popup.add(ErrorPopup, {
                        body: (result.error),
                    });
                    return;
                }
                self.pos.popup.add(CreateRegulationPopup, {
                    laboratories: result.laboratories,
                    location_id: result.location_id,
                    warehouse_name: result.warehouse_name,
                    warehouse_id: result.warehouse_id,
                    warehouse_external_id: result.warehouse_external_id,
                    employee_id_old: result.employee_id_old,
                    start_date: result.start_date,
                    end_date: result.end_date
                });
            })
        } catch (error) {
            console.log(error, "Error al obtener la información");
            // self.notificationService.add(
            //     ("Error al obtener la información" + error),
            //     {type: "error"}
            // );
        }
    }
}

ProductScreen.addControlButton({
    component: StockRegulationButton,
    condition: () => true
})