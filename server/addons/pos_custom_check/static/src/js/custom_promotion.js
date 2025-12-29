/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";
import {OkeyPopup} from "../popups/okey_popup";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

patch(ProductScreen.prototype, {
    selectLine(orderline) {
        this.numberBuffer.reset();
        this.currentOrder.select_orderline(orderline);
        localStorage.setItem("idProductCoupon",orderline.product.id)
    },

    async updateSelectedOrderline({ buffer, key }) {
        const order = this.pos.get_order();
        const selectedLine = this.currentOrder.get_selected_orderline();
        // This validation must not be affected by `disallowLineQuantityChange`
        if (selectedLine && selectedLine.isTipLine() && this.pos.numpadMode !== "price") {
            /**
             * You can actually type numbers from your keyboard, while a popup is shown, causing
             * the number buffer storage to be filled up with the data typed. So we force the
             * clean-up of that buffer whenever we detect this illegal action.
             */
            this.numberBuffer.reset();
            if (key === "Backspace") {
                this._setValue("remove");
            } else {
                this.popup.add(ErrorPopup, {
                    title: _t("Cannot modify a tip"),
                    body: _t("Customer tips, cannot be modified directly"),
                });
            }
            return;
        }



        if (key === "-") {
            if (selectedLine && selectedLine.eWalletGiftCardProgram) {
                // Do not allow negative quantity or price in a gift card or ewallet orderline.
                // Refunding gift card or ewallet is not supported.
                this.notification.add(
                    _t("You cannot set negative quantity or price to gift card or ewallet."),
                    4000
                );
                return;
            }
        }
        if (
            selectedLine &&
            selectedLine.refunded_orderline_id
        ){
            const { confirmed } = await this.popup.add(ConfirmPopup, {
                title: _t("Cancelar reembolso"),
                body: _t(
                    "¿Está seguro de que desea cancelar este reembolso?"
                ),
                cancelText: _t("Cancelar"),
                confirmText: _t("Ok"),
            });
            if (confirmed) {
                buffer = null;
                this.pos.get_order()
                const orderlines = order.get_orderlines()
                orderlines.forEach((orderline) => {
                    order.removeOrderline(orderline)
                });
                return;
            } else {
                return;
            }
        }
        if (
            selectedLine &&
            selectedLine.is_reward_line &&
            !selectedLine.manual_reward &&
            (key === "Backspace" || key === "Delete")
        ) {
            if (selectedLine._popupInProgress) {
                return;
            }
            selectedLine._popupInProgress = true;

            const { confirmed } = await this.popup.add(OkeyPopup, {
                title: _t("Deactivating reward"),
                body: _t(
                    `La recompensa está vinculada o aplicada a uno de los productos. No se puede desactivar.`
                ),
                cancelText: _t("Ok"),
                confirmText: null,
            });

            selectedLine._popupInProgress = false;

            if (confirmed) {
                buffer = null;
            } else {
                return;
            }
        }else{
            if (
                selectedLine &&
                this.pos.numpadMode === "quantity" &&
                this.pos.disallowLineQuantityChange()
            ) {
                const orderlines = order.orderlines;
                const lastId = orderlines.length !== 0 && orderlines.at(orderlines.length - 1).cid;
                const currentQuantity = this.pos.get_order().get_selected_orderline().get_quantity();

                if (selectedLine.noDecrease) {
                    this.popup.add(ErrorPopup, {
                        title: _t("Invalid action"),
                        body: _t("You are not allowed to change this quantity"),
                    });
                    return;
                }
                const parsedInput = (buffer && parseFloat(buffer)) || 0;
                if (lastId != selectedLine.cid) {
                    this._showDecreaseQuantityPopup();
                } else if (currentQuantity < parsedInput) {
                    this._setValue(buffer);
                } else if (parsedInput < currentQuantity) {
                    this._showDecreaseQuantityPopup();
                }
                return;
            } else if (
                selectedLine &&
                this.pos.numpadMode === "discount" &&
                this.pos.disallowLineDiscountChange()
            ) {
                this.numberBuffer.reset();
                const { confirmed, payload: inputNumber } = await this.popup.add(NumberPopup, {
                    startingValue: 10,
                    title: _t("Set the new discount"),
                    isInputSelected: true,
                });
                if (confirmed) {
                    await this.pos.setDiscountFromUI(selectedLine, inputNumber);
                }
                return;
            }
            const val = buffer === null ? "remove" : buffer;
            this._setValue(val);
            if (val == "remove") {
                this.numberBuffer.reset();
                this.pos.numpadMode = "quantity";
            }
        }

    },
});
