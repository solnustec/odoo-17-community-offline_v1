/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class HistoricalPopup extends AbstractAwaitablePopup {
    static template = "HistoricalPopupTemplate";
    static defaultProps = {
        title: _t("Historial de Movimientos"),
        warehouseId: null,
        laboratoryId: null,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            history: [],
        });
        this.loadHistory();
    }

    async loadHistory() {
        try {
            const domain = [];

            if (this.props.warehouseId) {
                const warehouseId = parseInt(this.props.warehouseId, 10);

                const stockLocationId = await this.orm.call("stock.location", "search", [
                    [["warehouse_id", "=", warehouseId], ["replenish_location", "=", true]]
                ]);


                domain.push(["location_dest_id", "=", stockLocationId]);
            }

            const labId = parseInt(this.props.laboratoryId, 10);
            
            if (this.props.laboratoryId) {

                const templateIds = await this.orm.call("product.template", "search", [
                    [["laboratory_id", "=", labId]]
                ]);


                const productIds = await this.orm.call(
                    "product.product",
                    "search",
                    [[["product_tmpl_id", "in", templateIds]]]
                );
    

                domain.push(["product_id", "in", productIds]);
            }


            const stock = await this.orm.call("stock.move.line", "search_read", [
                domain,
                ["id", "date", "product_id", "reference", "location_id", "location_dest_id", "quantity", "product_uom_id", "state"],
              ]);


            this.state.history = stock.map(rec => ({
                date: rec.date,
                product_name: rec.product_id ? rec.product_id[1] : "",
                reference: rec.reference,
                location: rec.location_id ? rec.location_id[1] : "",
                location_dest: rec.location_dest_id ? rec.location_dest_id[1] : "",
                quantity: rec.quantity,
                product_uom: rec.product_uom_id ? rec.product_uom_id[1] : "",
                state: rec.state,
                id: rec.id,
            }));

        } catch (error) {
            console.error("Erro ao carregar o histórico:", error);
        }
    }

    closePopup() {
        this.cancel();
    }
}
