/** @odoo-module */
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {_t} from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.notificationService = useService("notification");
        this.state = useState({buttonClicked: false});

    },

    async _confirmAction({title, body}) {
        const {confirmed} = await this.popup.add(ConfirmPopup, {
            title, body,
        });
        return confirmed;
    },

    toggleButtonState() {
        this.state.buttonClicked = !this.state.buttonClicked;
    },

    toggleIsToInvoice() {
        //limpiar la lineas de pagos seleccionada en la ordende entrega
        const paymentLines = this.currentOrder.get_paymentlines();
        for (const paymentLine of paymentLines) {
            this.deletePaymentLine(paymentLine.cid)
        }
        this.currentOrder.set_to_invoice(!this.currentOrder.is_to_invoice());
        this.state.buttonClicked = !this.currentOrder.to_invoice;
        this._updatePaymentMethods()

    },
    async _veriffy_is_credit_note(orderlines) {
        let is_credit_note = false
        if (orderlines[0].refunded_orderline_id > 0) {
            is_credit_note = true
        }
        return is_credit_note
    },


    async toggleSaleOrder() {
        await this.toggleButtonState()
        //verificar si es una notadecreito
        const is_credit_note = await this._veriffy_is_credit_note(this.currentOrder.orderlines)
        if (is_credit_note) {
            await this._confirmAction({
                title: _t("Advertencia"),
                body: _t("Cuando se crea una Nota de Crédito, no se puede generar una Orden de Entrega"),
            })
            this.currentOrder.set_to_invoice(true);
            this.state.buttonClicked = false;
            return;
        }


        //limpiar la lineas de pagos
        const paymentLines = this.currentOrder.get_paymentlines();
        for (const paymentLine of paymentLines) {
            this.deletePaymentLine(paymentLine.cid)
        }
        //verificar si el metodo de pago es credito a cliente sino tiene se le lanza un alreta de advertencia
        const paymentMethods = this.payment_methods_from_config

        const existsFlexible = paymentMethods.some(item => item.name.toLowerCase().includes('CRÉDITO') || item.name.toLowerCase().includes('credito'));
        if (!existsFlexible) {
            await this._confirmAction({
                title: _t("Advertencia"),
                body: _t("No es posible crear una orden de entrega, solo esta disponible para clientes con crédito Farmacias Cuxibamba"),
            })
            this.currentOrder.set_to_invoice(true);
            this.state.buttonClicked = false;
            return
        }

        // si se cambia a factura se recargan los metodos de apgo
        this.payment_methods_from_config = this.payment_methods_from_config.filter((method) => method.name.toLowerCase().includes("CRÉDITO") || method.name.toLowerCase().includes("credito"));
        this.currentOrder.set_to_invoice(false);
        this.state.buttonClicked = true;
        const partner = this.currentOrder.get_partner();
        const confirmed = await this._confirmAction(partner ? {
            title: _t("Esta seguro de que desea crear una orden de entrega?"),
            body: _t("Esto no se puede deshacer.")
        } : {
            title: _t("Please select the Customer"),
            body: _t("You need to select the customer before you can invoice or ship an order.")
        });
        if (!confirmed) {
            this.currentOrder.set_to_invoice(true);
            this.state.buttonClicked = false;
            return;
        }

        if (partner === undefined) {
            this.selectPartner();
        }
        this.render();
    },

    async validateOrder(isForceValidate) {
        try {
            await this.createQuotation();
            super.validateOrder(isForceValidate);
        } catch (error) {
            this._handleError(error);
        }
    },

    async createQuotation() {
        const order = this.pos.get_order();
    },


    async _prepareQuoteData(order) {
        const orderData = order.export_for_printing();
        let warehouseId = await this._getWarehouse()
        const partner = order.get_partner();

        return {
            partner_id: partner.id,
            user_id: this.pos.user.id,
            generate_from_pos: true,
            pos_session_id: this.pos.pos_session.id,
            order_line: order.get_orderlines().map(line => this._prepareLineData(line)),
            amount_total: orderData.total,
            amount_tax: orderData.amount_tax,
            amount_untaxed: orderData.amount_untaxed,
            warehouse_id: warehouseId,
        }
    }, async _getWarehouse() {
        try {
            const pickingTypeId = this.pos.config.picking_type_id[0];
            const result = await this.orm.call("stock.picking.type", "read", [[pickingTypeId], ["warehouse_id"]]);
            if (result.length) {
                return result[0].warehouse_id[0]
            }
        } catch (error) {
            console.error("Error al obtener el almacén:", error);
        }
    }, _prepareLineData(line) {
        return [0, 0, {
            product_id: line.product.id,
            name: line.product.display_name,
            is_reward_line: line.price_type === "automatic",
            product_uom_qty: line.quantity,
            price_unit: line.get_price_without_tax(),
            reward_id: line.reward_id ? line.reward_id : "",
            reward_identifier_code: line.reward_identifier_code ? line.reward_identifier_code : "",
            discount: line.discount,
            points_cost: line.points_cost

        }];
    }, async _handleSuccessResponse(quoteId) {
        await this.notificationService.add(_t("Orden de Entrega %s generada con éxito", quoteId), {type: 'success'});
        //await this.pos.showScreen(this.nextScreen);

    }, _handleError(error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        this.notificationService.add(_t("Error al crear la orden de venta: %s", errorMessage), {type: "warning"});
    }

});