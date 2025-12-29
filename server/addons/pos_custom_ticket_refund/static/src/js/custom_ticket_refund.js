/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { RefundButton } from "@point_of_sale/app/screens/product_screen/control_buttons/refund_button/refund_button";
import { _t } from "@web/core/l10n/translation";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

patch(TicketScreen.prototype, {

    async onDoRefund() {
        const order_review = this.getSelectedOrder();
        if (
            order_review.orderlines.length > 0 &&
            order_review.orderlines.some(line => line.refunded_orderline_id && line.refunded_qty > 0)
        ){
            await this.env.services.popup.add(ErrorPopup, {
                title: _t("No es posible reembolsar esta orden"),
                body: _t(
                    "Esta orden ya ha sido reembolsada anteriormente."
                ),
                confirmText: _t("Ok"),
            });

        } else {
            const order = this.getSelectedOrder();

            if (order && this._doesOrderHaveSoleItem(order)) {
                if (!this._prepareAutoRefundOnOrder(order)) {
                    // Don't proceed on refund if preparation returned false.
                    return;
                }
            }

            if (!order) {
                this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
                return;
            }

            const partner = order.get_partner();

            const allToRefundDetails = this._getRefundableDetails(partner, order);
            if (allToRefundDetails.length == 0) {
                this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
                return;
            }

            // const invoicedOrderIds = new Set(
            //     allToRefundDetails
            //         .filter(
            //             (detail) =>
            //                 this._state.syncedOrders.cache[detail.orderline.orderBackendId]?.state ===
            //                 "invoiced"
            //         )
            //         .map((detail) => detail.orderline.orderBackendId)
            // );
            //
            // if (invoicedOrderIds.size > 1) {
            //     this.popup.add(ErrorPopup, {
            //         title: _t("Multiple Invoiced Orders Selected"),
            //         body: _t(
            //             "You have selected orderlines from multiple invoiced orders. To proceed refund, please select orderlines from the same invoiced order."
            //         ),
            //     });
            //     return;
            // }

            // The order that will contain the refund orderlines.
            // Use the destinationOrder from props if the order to refund has the same
            // partner as the destinationOrder.
            const destinationOrder =
                this.props.destinationOrder &&
                partner === this.props.destinationOrder.get_partner() &&
                !this.pos.doNotAllowRefundAndSales()
                    ? this.props.destinationOrder
                    : this._getEmptyOrder(partner);

            // Add orderline for each toRefundDetail to the destinationOrder.
            const originalToDestinationLineMap = new Map();

            // First pass: add all products to the destination order
            for (const refundDetail of allToRefundDetails) {
                await this.pos._addProducts([refundDetail.orderline.productId], false);
                const product = this.pos.db.get_product_by_id(refundDetail.orderline.productId);
                const options = this._prepareRefundOrderlineOptions(refundDetail);
                const newOrderline = await destinationOrder.add_product(product, options);
                originalToDestinationLineMap.set(refundDetail.orderline.id, newOrderline);
                refundDetail.destinationOrderUid = destinationOrder.uid;
            }
            // Second pass: update combo relationships in the destination order
            for (const refundDetail of allToRefundDetails) {
                const originalOrderline = refundDetail.orderline;
                const destinationOrderline = originalToDestinationLineMap.get(originalOrderline.id);
                if (originalOrderline.comboParent) {
                    const comboParentLine = originalToDestinationLineMap.get(
                        originalOrderline.comboParent.id
                    );
                    if (comboParentLine) {
                        destinationOrderline.comboParent = comboParentLine;
                    }
                }
                if (originalOrderline.comboLines && originalOrderline.comboLines.length > 0) {
                    destinationOrderline.comboLines = originalOrderline.comboLines.map((comboLine) => {
                        return originalToDestinationLineMap.get(comboLine.id);
                    });
                }
            }
            //Add a check too see if the fiscal position exist in the pos
            if (order.fiscal_position_not_found) {
                this.showPopup("ErrorPopup", {
                    title: _t("Fiscal Position not found"),
                    body: _t(
                        "The fiscal position used in the original order is not loaded. Make sure it is loaded by adding it in the pos configuration."
                    ),
                });
                return;
            }
            destinationOrder.fiscal_position = order.fiscal_position;
            // Set the partner to the destinationOrder.
            this.setPartnerToRefundOrder(partner, destinationOrder);

            if (this.pos.get_order().cid !== destinationOrder.cid) {
                this.pos.set_order(destinationOrder);
            }
            await this.addAdditionalRefundInfo(order, destinationOrder);

            this.closeTicketScreen();
        }

    },

    _getRefundableDetails(partner, order) {
        return Object.values(this.pos.toRefundLines).filter(
            ({ qty, orderline, destinationOrderUid }) =>
                !this.pos.isProductQtyZero(qty) &&
                (partner ? orderline.orderPartnerId == partner.id : true) &&
                orderline.orderUid == order.uid &&
                !destinationOrderUid
        );
    },

    //para Rembolso de promociones

    _prepareRefundOrderlineOptions(toRefundDetail) {
        const { qty, orderline } = toRefundDetail;
        const originalData = super._prepareRefundOrderlineOptions(...arguments);
        return {
            ...originalData,
            tracking: orderline.tracking || "none",
            reward_product_id: orderline.reward_product_id,
            original_id_reward: orderline.original_id_reward,
        };
    },


    _getToRefundDetail(orderline) {
        const { toRefundLines } = this.pos;
        if (orderline.id in toRefundLines) {
            if(toRefundLines[orderline.id]?.orderline.uuid===orderline.uuid){
                return toRefundLines[orderline.id]
            }

        }
        const partner = orderline.order.get_partner();
        const orderPartnerId = partner ? partner.id : false;
        const newToRefundDetail = {
            qty: 0,
            orderline: {
                id: orderline.id,
                uuid: orderline.uuid,
                productId: orderline.product.id,
                price: orderline.price,
                qty: orderline.quantity,
                refundedQty: orderline.refunded_qty,
                orderUid: orderline.order.uid,
                orderBackendId: orderline.order.backendId,
                orderPartnerId,
                tax_ids: orderline.get_taxes().map((tax) => tax.id),
                discount: orderline.discount,
                reward_product_id: orderline.reward_product_id,
                original_id_reward: orderline.original_id_reward,
                program_id: orderline.program_id,
                pack_lot_lines: orderline.pack_lot_lines
                    ? orderline.pack_lot_lines.map((lot) => {
                          return { lot_name: lot.lot_name };
                      })
                    : false,
                comboParent: orderline.comboParent,
                comboLines: orderline.comboLines,
            },
            destinationOrderUid: false,
        };
        toRefundLines[orderline.id] = newToRefundDetail;
        return newToRefundDetail;
    },

    getNumpadButtons() {
        return [
            { value: "1", disabled: true },
            { value: "2", disabled: true },
            { value: "3", disabled: true },
            { value: "quantity", text: _t("Qty"), class: "active border-primary", disabled: true },
            { value: "4", disabled: true },
            { value: "5", disabled: true },
            { value: "6", disabled: true },
            { value: "discount", text: _t("% Disc"), disabled: true },
            { value: "7", disabled: true },
            { value: "8", disabled: true },
            { value: "9", disabled: true },
            { value: "price", text: _t("Price"), disabled: true},
            { value: "-", text: "+/-",  disabled: true},
            { value: "0", disabled: true },
            { value: this.env.services.localization.decimalPoint, disabled: true },
            { value: "Backspace", text: "⌫", disabled: true },
        ];
    },

    getRefundQty(line) {
        const refundLine = line.pos.toRefundLines[line.id];
        if (refundLine && refundLine.qty) {
            return this.env.utils.formatProductQty(refundLine.qty);
        }
        return false;
    },


    _onUpdateSelectedOrderline({ key, buffer }) {

        const order = this.getSelectedOrder();
        if (!order) {
            return this.numberBuffer.reset();
        }

        const selectedOrderlineId = this.getSelectedOrderlineId();
        const orderline = order.orderlines.find((line) => line.id == selectedOrderlineId);
        if (!orderline) {
            return this.numberBuffer.reset();
        }
        const toRefundDetails = orderline
            .getAllLinesInCombo()
            .map((line) => this._getToRefundDetail(line));
        for (const toRefundDetail of toRefundDetails) {
            // When already linked to an order, do not modify the to refund quantity.
            if (toRefundDetail.destinationOrderUid) {
                return this.numberBuffer.reset();
            }

            const refundableQty =
                toRefundDetail.orderline.qty - toRefundDetail.orderline.refundedQty;
            if (refundableQty <= 0) {
                return this.numberBuffer.reset();
            }

            if (buffer == null || buffer == "") {
                toRefundDetail.qty = 0;
            } else {
                const quantity = Math.abs(parseFloat(buffer));
                if (quantity > refundableQty) {
                    this.numberBuffer.reset();
                    if (!toRefundDetail.orderline.comboParent) {
                        this.popup.add(ErrorPopup, {
                            title: _t("Maximum Exceeded"),
                            body: _t(
                                "The requested quantity to be refunded is higher than the ordered quantity. %s is requested while only %s can be refunded.",
                                quantity,
                                refundableQty
                            ),
                        });
                    }
                } else {
                    toRefundDetail.qty = quantity;
                }
            }
        }
    },


    click_refund_line_add(line){
        const selectedOrder = this._state.ui.selectedOrder;
        // if (this.is_payment_card_in_order(selectedOrder)){
        selectedOrder.get_orderlines().forEach((orderline) => {
            this.action_default_for_refund(orderline, "add")
        });
        // } else {
        // selectedOrder.get_orderlines().forEach((orderline) => {
        //     if (orderline.reward_product_id === line.product.id) {
        //         this.action_default_for_refund(orderline, "add")
        //     }
        // });
        // this.action_default_for_refund(line, "add")
        // }
    },

    click_refund_line_remove(line){
        const selectedOrder = this._state.ui.selectedOrder;
        // if (this.is_payment_card_in_order(selectedOrder)){
        selectedOrder.get_orderlines().forEach((orderline) => {
            this.action_default_for_refund(orderline, "remove")
        });
        // } else {
        // selectedOrder.get_orderlines().forEach((orderline) => {
        //     if (orderline.reward_product_id === line.product.id) {
        //         this.action_default_for_refund(orderline, "remove")
        //     }
        // });
        // this.action_default_for_refund(line, "remove")
        // }

    },

    is_payment_card_in_order(order) {
        const paymentDate = new Date(order.date_order.ts);
        const now = new Date();
        return paymentDate.toDateString() === now.toDateString();
    },



    // onClickOrder(clickedOrder) {
    //     // const selectedOrder = this._state.ui.selectedOrder;
    //     super.onClickOrder(...arguments)
    //     // const currentOrder = this.pos.get_order();
    //
    //
    //     // if (selectedOrder && selectedOrder.uid !== currentOrder.uid) {
    //     //     this.action_default_for_refund(selectedOrder, 'remove');
    //     // }
    //
    //     // if (clickedOrder && clickedOrder.locked) {
    //     //     if (
    //     //         clickedOrder.orderlines.length > 0 &&
    //     //         clickedOrder.orderlines[0].refunded_orderline_id === false &&
    //     //         clickedOrder.orderlines[0].refunded_qty === 0
    //     //     ){
    //     //         this.action_default_for_refund(clickedOrder, 'add');
    //     //     }
    //     // }
    // },




    action_default_for_refund(orderline, action) {
        if (!orderline) {
            return;
        }
        if (action==='remove') {
            this.change_value_refund(orderline, 0);
        } else if (action==='add'){
            this.change_value_refund(orderline, orderline.quantity);
        }
    },


    change_value_refund(orderline, buffer){
        // if (buffer == null || buffer == "") {
        //     return ;
        // }
        const toRefundDetails = orderline
            .getAllLinesInCombo()
            .map((line) => this._getToRefundDetail(line));

        for (const toRefundDetail of toRefundDetails) {
            // When already linked to an order, do not modify the to refund quantity.
            if (toRefundDetail.destinationOrderUid) {
                continue
            }

            if (buffer == null || buffer == "") {
                toRefundDetail.qty = 0;
            } else {
                const quantity = Math.abs(parseFloat(buffer));
                toRefundDetail.qty = quantity;
            }
        }
    },

})

patch(RefundButton.prototype, {
    async click() {
        if (this.pos.get_order().get_orderlines().length >= 1){
            const { confirmed } = await this.env.services.popup.add(ConfirmPopup, {
                title: _t("Confirmación requerida antes del reembolso"),
                body: _t(
                    "Las líneas de tu pedido actual serán eliminadas antes de procesar reembolsos. ¿Estás seguro de continuar?"
                ),
                cancelText: _t("Cancelar"),
                confirmText: _t("Ok"),
            });

            if (confirmed) {
                const order = this.pos.get_order()
                const orderlines = order.get_orderlines()
                orderlines.forEach((orderline) => {
                    order.removeOrderline(orderline)
                });
                super.click();
            } else {
                return;
            }

        } else{
            super.click()
        }
    }
})