/** @odoo-module */

import {onMounted, useRef} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";

export class SaleOrderPopup extends AbstractAwaitablePopup {
    static template = "adevx_pos_sales_order.SaleOrderPopup"
    static defaultProps = {
        confirmText: _t("Enviar orden"),
        cancelText: _t("Close"),
        title: _t("Create Sale Order"),
        body: "",
        cancelKey: false,
    };

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.currentOrder = this.pos.get_order();
        this.changes = {
            note: null,
            signature: null,
            payment_partial_amount: 0,
            payment_partial_method_id: null,
            pricelist_id: this.currentOrder.pricelist ? this.currentOrder.pricelist.id : null,
            sale_order_auto_confirm: this.pos.config.sale_order_auto_confirm,
            sale_order_auto_delivery: this.pos.config.sale_order_auto_delivery,
            sale_order_auto_invoice: this.pos.config.sale_order_auto_invoice,
        }
        this.orderUiState = this.currentOrder.uiState.ReceiptScreen;
        this.signature_div = useRef("signature-div");
        onMounted(this.mounted);
        this.numberBuffer = useService("number_buffer");
        this.numberBuffer.use({
            triggerAtEnter: () => this.confirm(),
            triggerAtEscape: () => this.cancel(),
            state: this.changes,
        });
    }

    mounted() {
        var self = this;
        $(this.signature_div.el).jSignature();
        this.signed = false;
        $(this.signature_div.el).bind('change', function (e) {
            self.signed = true;
            self.verifyChanges(e);
        });
    }

    OnChange(event) {
        let target_name = event.target.name;
        if (event.target.type == 'checkbox') {
            this.changes[event.target.name] = event.target.checked;
        } else {
            this.changes[event.target.name] = event.target.value;
        }
        if (target_name == 'payment_partial_amount') {
            this.changes[event.target.name] = parseFloat(event.target.value);
        }
        if (target_name == 'pricelist_id' || target_name == 'payment_partial_method_id') {
            this.changes[event.target.name] = parseInt(event.target.value);
        }
        this.verifyChanges(event)
    }

    verifyChanges(event) {
        let changes = this.changes;
        if (!this.env.utils.isValidFloat(changes.payment_partial_amount)) {
            this.orderUiState.isSuccessful = false;
            this.orderUiState.hasNotice = _t('Partial amount required number');
            return
        }
        if (changes.payment_partial_amount < 0) {
            this.orderUiState.isSuccessful = false;
            this.orderUiState.hasNotice = _t('Partial amount required bigger than or equal 0');
            return;
        } else {
            this.orderUiState.isSuccessful = true;
        }
        const sign_datas = $(this.signature_div.el).jSignature("getData", "image");
        if (this.pos.config.sale_order_required_signature) {
            if (sign_datas && sign_datas[1] && this.signed) {
                changes['signature'] = sign_datas[1];
                this.orderUiState.isSuccessful = true;
                this.orderUiState.hasNotice = _t('Signature succeed')
            } else {
                this.orderUiState.isSuccessful = false;
                this.orderUiState.hasNotice = _t('Please signature');
            }
        } else {
            this.orderUiState.isSuccessful = true;
            // this.orderUiState.hasNotice = _t('Not required signature')
        }
        if (!changes.sale_order_auto_confirm || !changes.sale_order_auto_invoice) {
            changes.payment_partial_amount = 0;
            changes.payment_partial_method_id = null;
        }
        if (changes.sale_order_auto_delivery && !changes.sale_order_auto_confirm) {
            this.orderUiState.isSuccessful = false;
            this.orderUiState.hasNotice = _t('Please select auto confirm to be able to auto delivery');
        }
        if (changes.sale_order_auto_invoice && (!changes.sale_order_auto_confirm || !changes.sale_order_auto_delivery)) {
            this.orderUiState.isSuccessful = false;
            this.orderUiState.hasNotice = _t('Please select auto confirm and auto delivery to be able to auto invoice');
        }
    }

    async action_confirm() {
        const rawInput = (this.changes?.cellphone || "").trim().replace(/\s+/g, "");
        const numberWithoutZero = rawInput.startsWith("0") ? rawInput.slice(1) : rawInput;
        const fullNumber = "593" + numberWithoutZero;

        if (!(fullNumber.length === 12 && /^\d+$/.test(fullNumber))) {
            this.orderUiState.hasNotice = _t("Número de celular inválido");
            this.orderUiState.isSuccessful = false;
            return true;
        }

        // Guardar número formateado
        this.changes.cellphone_formatted = fullNumber;
        // Validación previa de nota o estado de orden (descomentar si aplica)
        // if (!this.orderUiState.isSuccessful) {
        //     if (this.orderUiState.hasNotice) {
        //         this.orderUiState.hasNotice = _t("Please check: ") + this.orderUiState.hasNotice
        //     } else {
        //         this.orderUiState.hasNotice = _t("Please full fill information of order")
        //     }
        //     return true
        // } else {

        return await this.confirm()
        // }
    }

    getPayload() {
        this.verifyChanges();
        if (this.orderUiState.isSuccessful) {
            return this.changes
        } else {
            return {
                values: {}, error: this.orderUiState.hasNotice
            };
        }
    }
}
