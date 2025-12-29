/** @odoo-module **/

import {Component} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {SaleOrderPopup} from "@adevx_pos_sales_order/js/SaleOrderPopup";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {OkeyPopup} from "../../../../pos_custom_check/static/src/popups/okey_popup";

export class CreateSaleOrderButton extends Component {
    static template = "adevx_pos_sales_order.CreateSaleOrderButton";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
        this.notification = useService("pos_notification");
        this.report = useService("report");
        this.ui = useService("ui");

    }

    get currentOrder() {
        return this.pos.get_order();
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
        const {confirmed, payload: values} = await this.popup.add(SaleOrderPopup, {
            title: _t('Create Sale Order'),
            order: order,
            sale_order_auto_confirm: this.pos.config.sale_order_auto_confirm,
            sale_order_auto_delivery: this.pos.config.sale_order_auto_delivery,
            sale_order_auto_invoice: this.pos.config.sale_order_auto_invoice,
        });
        if (confirmed) {
            this.ui.block();

            try {
                if (values.error) {
                    this.ui.unblock();
                    return this.popup.add(ErrorPopup, {
                        title: _t('Warning'), body: values.error,
                    });
                }

                const so_val = order.export_as_JSON();
                const id_employee = this.pos.cashier.id;

                const warehouse = await this.orm.call(
                    "sale.order",
                    "get_pos_by_employee",
                    [id_employee]
                );

                let value = {
                    name: order.name,
                    note: values.note,
                    origin: this.pos.config.name,
                    partner_id: order.get_partner().id,
                    pricelist_id: values.pricelist_id,
                    website_id: 1,
                    warehouse_id: warehouse.id,
                    user_id: this.pos.cashier.user_id,
                    order_line: [],
                    signature: values.signature,
                    signed_by: this.pos.user.name,
                    payment_partial_amount: values.payment_partial_amount,
                    payment_partial_method_id: values.payment_partial_method_id,
                };

                for (let i = 0; i < so_val.lines.length; i++) {
                    const line = so_val.lines[i][2];
                    const line_val = order._covert_pos_line_to_sale_line(line);
                    value.order_line.push(line_val);
                }

                const result = await this.orm.call(
                    "sale.order",
                    "create_from_pos_ui",
                    [value, values.sale_order_auto_confirm, values.sale_order_auto_delivery, values.sale_order_auto_invoice]
                );

                this.pos.removeOrder(this.currentOrder);
                this.pos.selectNextOrder();

                await this.popup.add(OkeyPopup, {
                    title: _t("Pedido creado"),
                    body: _t(`El pedido ${result.name} ha sido creado correctamente.`),
                    cancelText: _t("Ok"),
                    confirmText: null,
                });

                // Enviar notificación WhatsApp (opcional - no falla si el módulo no está instalado)
                const fullEcuPhone = values.cellphone_formatted || "";
                if (fullEcuPhone) {
                    try {
                        await this.orm.call("sale.order", "send_message_whatsapp", [result.id, result.id, fullEcuPhone]);
                    } catch (whatsappErr) {
                        console.warn("WhatsApp integration not available or failed:", whatsappErr);
                        // No mostrar error al usuario - la orden se creó correctamente
                    }
                }

            } catch (err) {
                console.error("Error al crear pedido:", err);
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t("Ocurrió un error al crear el pedido. Revisa la consola o el log."),
                });
            } finally {
                this.ui.unblock();
            }
        }

    }
}

function processRewardLines(orderLines) {
    if (!orderLines || !Array.isArray(orderLines)) {
        return orderLines;
    }

    orderLines.forEach((line, index) => {
        // Verificar si la línea tiene reward_product_id y price_unit en 0
        if (line[2] && line[2].reward_product_id && line[2].price_unit === 0) {
            const rewardProductId = line[2].reward_product_id;

            // Reemplazar product_id con reward_product_id
            line[2].product_id = rewardProductId;
        }
    });

    return orderLines;
}

ProductScreen.addControlButton({
    component: CreateSaleOrderButton,
    condition: function () {
        return this.pos.config.create_sale_order;
    },
});
