/** @odoo-module **/

import {Component} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {SaleOrderPopup} from "@adevx_pos_sales_order/js/SaleOrderPopup";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";

export class UpdateSaleOrderButton extends Component {
    static template = "adevx_pos_sales_order.UpdateSaleOrderButton";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
        this.notification = useService("pos_notification");
        this.report = useService("report");
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    async _getSaleOrder(id) {
        const [sale_order] = await this.orm.read("sale.order", [id], ["state", "partner_id"]);
        return sale_order;
    }

    async _getSOLines(ids) {
        const so_lines = await this.orm.call("sale.order.line", "read_converted", [ids]);
        return so_lines;
    }

    async click() {
        var self = this;
        let order = this.currentOrder
        if (order.get_total_with_tax() <= 0 || order.orderlines.length == 0) {
            return this.popup.add(ErrorPopup, {
                title: _t('Error'), body: _t('Your shopping cart is empty !'),
            })
        }
        if (!order.get_partner()) {
            this.notification.add(_t("Required set customer for create sale order"), 3000);
            const {
                confirmed: confirmedTempScreen, payload: newPartner
            } = await this.pos.showTempScreen("PartnerListScreen");
            if (!confirmedTempScreen) {
                return;
            } else {
                order.set_partner(newPartner);
            }
        }
        const sale_selected = await this._getSaleOrder(order.sale_id)
        // Si la orden NO está en borrador, convertirla desde el POS
        if (!['draft', 'sent'].includes(sale_selected.state)) {

            // Aviso visual opcional (puede quitarse)
            await this.popup.add(ConfirmPopup, {
                title: _t("Pedido en estado confirmado"),
                body: _t("El pedido está confirmado. Se configurará como borrador para permitir actualizaciones."),
            });

            // Llamar al servidor para pasar a borrador
            await this.orm.call(
                "sale.order",
                "action_cancel",
                [[sale_selected.id]]
            );

            await this.orm.write(
                "sale.order",
                [sale_selected.id],
                {state: "draft"}
            );

        } else {

            // Construir datos de actualización correctamente
            const order_json = order.export_as_JSON();

            let value = {
                note: order.get_note?.() || "",
                partner_id: order.get_partner()?.id,
                pricelist_id: order.pricelist?.id,
                order_line: [],
                signature: null,
                payment_partial_amount: 0,
                payment_partial_method_id: null,
            };

            // Convertir líneas del POS → sale.order.line
            for (var i = 0; i < order_json.lines.length; i++) {
                var line = order_json.lines[i][2];
                var line_val = order._covert_pos_line_to_sale_line(line);
                value.order_line.push(line_val);
            }

            try {
                let result = await this.orm.call(
                    "sale.order",
                    "write_from_pos_ui",
                    [[sale_selected.id], value,
                        this.pos.config.sale_order_auto_confirm,
                        this.pos.config.sale_order_auto_delivery,
                        this.pos.config.sale_order_auto_invoice]
                );

                this.notification.add(
                    _t(`La orden ${result.name} fue actualizada correctamente.`),
                    4000,
                    "success"
                );

                this.pos.removeOrder(this.currentOrder);
                this.pos.selectNextOrder();

            } catch (err) {
                console.error("Error actualizando la orden:", err);

                this.notification.add(
                    _t("Error: No se pudo actualizar la orden. Revisa la consola o intenta nuevamente."),
                    5000,
                    "danger"
                );

                return;
            }
        }

    }

}

ProductScreen.addControlButton({
    component: UpdateSaleOrderButton,
    condition: function () {
        return this.pos.config.update_sale_order && this.pos.get_order().sale_id;
    },
});
