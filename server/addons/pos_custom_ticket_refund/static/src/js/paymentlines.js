/** @odoo-module */

import {PaymentScreenPaymentLines} from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";
import {CheckInfoPopup} from "@pos_custom_check/js/check_info_popup";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {_t} from "@web/core/l10n/translation";
import {useState, onMounted, useEffect} from "@odoo/owl";
import {SelectionPopup} from "@point_of_sale/app/utils/input_popups/selection_popup";

patch(PaymentScreenPaymentLines.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.state = useState({
            ...this.state,
        });
        this.pos.isNumpadDisabled = false;
        this.pos.btnDisabled = false;
        this.orm = useService("orm");
    },

    async loadCashPaymentMethods() {
        try {
            const allPaymentMethodCash = await this.orm.call("account.journal", "get_cash_journals", []);
            const cashMethods = Array.isArray(allPaymentMethodCash) ? allPaymentMethodCash.map(paymentMethod => paymentMethod.name) : [];
            const processedPaymentMethods = [...cashMethods, "TARJETA", "CREDITO"];
            return processedPaymentMethods;
        } catch (error) {
            console.error('Error al llamar al método get_cash_journals:', error);
            return [];
        }
    },


    async selectLine(paymentline) {
        this.props.selectLine(paymentline.cid);
        const paymentAllCash = await this.loadCashPaymentMethods();
        const enableAdvanced = paymentline?.enable_advanced_payments === true;

        if (enableAdvanced) {
            if (
                paymentAllCash.includes(paymentline.payment_method.originalName) ||
                (
                    paymentline.name === "CHEQUE / TRANSF" &&
                    (paymentline.bank_id !== "464" ||
                        paymentline.bank_id !== "463")
                )
            ) {
                this.pos.isNumpadDisabled = true;
            } else {
                this.pos.isNumpadDisabled = false;
            }
        } else {
            this.pos.isNumpadDisabled = false;
        }


        if (this.ui.isSmall) {
            const {confirmed, payload} = await this.popup.add(NumberPopup, {
                title: _t("New amount"),
                startingValue: paymentline.amount,
                isInputSelected: true,
                nbrDecimal: this.pos.currency.decimal_places,
            });

            if (confirmed) {
                this.props.updateSelectedPaymentline(parseFloat(payload));
            }
        }
        return;
    },


    async _CheckInfoClicked(cid) {
        const order = this.pos.get_order();
        const selected_paymentline = order.selected_paymentline;
        if (selected_paymentline) {
            const check_info = selected_paymentline.getCheckInfo();
            const {confirmed} = await this.popup.add(CheckInfoPopup, {
                title: 'Check',
                array: check_info,
            });
            if (confirmed) {
                if (selected_paymentline.payment_method.name === "TARJETA") {
                    this._updateCardInfo(selected_paymentline);
                } else if (selected_paymentline.payment_method.name === "CHEQ O TRANS") {
                    this._updateCheckInfo(selected_paymentline);
                }
            }
        }
    },

    _updateCheckInfo(selected_paymentline) {
        const bank_name = parseInt($("#bank_id").val());
        const check_number = document.getElementById("check_number").value;
        const owner_name = document.getElementById("owner_name").value;
        const bank_account = document.getElementById("bank_account").value;

        if (!bank_name && !check_number && !owner_name && !bank_account) {
            this._clearCheckInfo(selected_paymentline);
        } else {
            selected_paymentline.set_bank_name(bank_name);
            selected_paymentline.set_check_number(check_number);
            selected_paymentline.set_owner_name(owner_name);
            selected_paymentline.set_bank_account(bank_account);
        }
    },

    _updateCardInfo(selected_paymentline) {
        const number_voucher = document.getElementById("number_voucher").value;
        const type_card = document.getElementById("type_card").value;

        if (!number_voucher && !type_card) {
            this._clearCardInfo(selected_paymentline);
        } else {
            selected_paymentline.set_number_voucher(number_voucher);
            selected_paymentline.set_type_card(type_card);
        }
    },

    _clearCheckInfo(selected_paymentline) {
        selected_paymentline.set_check_number("");
        selected_paymentline.set_owner_name("");
        selected_paymentline.set_bank_account("");
        selected_paymentline.set_bank_name("");
    },

    _clearCardInfo(selected_paymentline) {
        selected_paymentline.set_number_voucher("");
        selected_paymentline.set_type_card("");
    },
});

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.pos = usePos();
        this.rpc = useService("rpc");

        this.state = useState({
            credit_partner: parseFloat(localStorage.getItem("credito")) || 0,
            clientHasCreditNotes: false,
            creditNoteTotal: 0,
            paymentMethods: [],
            isRefund: false,
            originalPaymentMethods: [],
            paymentsAdded: false,
            originalAmountsByMethodId: {}
        });
        this.pos.paymentScreen = this;
        this._updatePaymentMethodsDisplayName();

        useEffect(
            () => {
                this._onClientChanged();
            },
            () => [this.currentOrder, this.currentOrder?.client]
        );

        onMounted(async () => {
            const order = this.currentOrder;
            const totalWithTax = order.get_total_with_tax();
            const isRefund = totalWithTax < 0;
            this.state.isRefund = isRefund;

            if (isRefund && !this.state.paymentsAdded) {
                const selectedOrderline = order.selected_orderline || order.get_orderlines()[0];
                if (selectedOrderline && selectedOrderline.refunded_orderline_id) {
                    const orderIdLine = selectedOrderline.refunded_orderline_id;
                    const orderId = await this.orm.call('pos.order.line', 'get_order_id', [orderIdLine]);

                    console.log("🔍 Order ID de la línea original:", orderId);

                    const paymentMethods = await this.orm.call('pos.order', 'get_order_payment_methods', [orderId]);
                    this.state.originalPaymentMethods = paymentMethods;

                    console.log("🔍 Original Payment Methods:", paymentMethods);

                    // Verificar si hay método CREDITO con institución
                    const creditPayment = paymentMethods.find(pm =>
                        pm.payment_method_name === "CREDITO" ||
                        pm.payment_method_name.includes("CREDITO")
                    );

                    if (creditPayment) {
                        console.log("✅ Reembolso incluye método CREDITO");
                        console.log("📌 Institution ID del pago original:", creditPayment.credit_institution_id);

                        // Si no tiene credit_institution_id, intentar obtenerla del cliente
                        if (!creditPayment.credit_institution_id) {
                            console.log("⚠️ No se encontró institution_id en el pago, buscando por cliente...");
                            const client = order.get_partner();
                            if (client) {
                                try {
                                    const institutions = await this.orm.call(
                                        'institution.client',
                                        'get_institutions_by_partner',
                                        [client.id]
                                    );
                                    if (institutions && institutions.length > 0) {
                                        // Usar la primera institución del cliente como fallback
                                        creditPayment.credit_institution_id = institutions[0].institution_id;
                                        console.log("✅ Institution ID obtenida del cliente:", creditPayment.credit_institution_id);
                                    }
                                } catch (e) {
                                    console.error("Error obteniendo instituciones del cliente:", e);
                                }
                            }
                        }
                    }

                    for (const pm of paymentMethods) {
                        const paymentMethodId = pm.payment_method_id;
                        const amount = -Math.abs(pm.amount);
                        this.state.originalAmountsByMethodId[paymentMethodId] = amount;
                    }

                    for (const paymentData of paymentMethods) {
                        const paymentMethodId = paymentData.payment_method_id;
                        const paymentMethod = this.pos.payment_methods.find(pm => pm.id === paymentMethodId);
                        if (paymentMethod) {
                            const existingPaymentLine = order.get_paymentlines().find(
                                (line) => line.payment_method.id === paymentMethodId
                            );
                            if (!existingPaymentLine) {
                                const amount = this.state.originalAmountsByMethodId[paymentMethodId];
                                if (amount !== 0) {
                                    order.add_paymentline(paymentMethod);
                                    const paymentline = order.selected_paymentline;
                                    paymentline.set_amount(amount);

                                    // Si es CREDITO, guardar la institución
                                    if (paymentMethod.code_payment_method === "CREDITO" && paymentData.credit_institution_id) {
                                        paymentline.set_selecteInstitutionCredit(paymentData.credit_institution_id);
                                        console.log("💾 Guardando institution_id en paymentline:", paymentData.credit_institution_id);
                                    }
                                }
                            }
                        } else {
                            console.warn(`Método de pago con ID ${paymentMethodId} no encontrado en el POS.`);
                        }
                    }

                    this.state.paymentsAdded = true;
                } else {
                    console.warn("No fue posible obtener el ID de la orden original.");
                    this.state.originalPaymentMethods = [];
                }
            }

            this._updatePaymentMethods();

        });

        useEffect(() => {
            const paymentLines = this.currentOrder.get_paymentlines();
            const paymentMethodsUsed = paymentLines.map(line => line.payment_method.name);
        }, () => [this.currentOrder.paymentlines]);

        useEffect(() => {
            const order = this.currentOrder;

            if (this.state.originalPaymentMethods && this.state.originalPaymentMethods.length > 0) {
                const originalIds = this.state.originalPaymentMethods.map(p => p.payment_method_id);
                const existingOriginalLines = order.get_paymentlines().filter(line => originalIds.includes(line.payment_method.id));
                if (existingOriginalLines.length === 0) {
                    this.state.paymentsAdded = false;
                }
            }
        }, () => [this.currentOrder.paymentlines]);

        useEffect(() => {
            this.state.paymentsAdded = false;
        }, () => [this.currentOrder]);

    },

    get currentOrder() {
        return this.pos.get_order();
    },

    async _onClientChanged() {
        const client = this.currentOrder.get_partner();
        if (client) {
            this.state.clientHasCreditNotes = await this._checkClientCreditNotes(client.id);
        } else {
            this.state.clientHasCreditNotes = false;
        }
        this._updatePaymentMethods();
    },

    async _checkClientCreditNotes(partner_id) {
        const creditNotes = await this.orm.call(
            "account.move",
            "get_value_for_note_credit",
            [partner_id, this.pos.config.id]
        );

        const totalCredit = creditNotes.reduce((sum, note) => sum + note.note_credit, 0);

        this.state.clientHasCreditNotes = creditNotes.length > 0;
        this.state.creditNoteTotal = totalCredit;

        return creditNotes.length > 0;
    },

    get _getNumberBufferConfig() {
        const config = {
            triggerAtInput: (data) => this._safeUpdateSelectedPaymentline(data),
            useWithBarcode: true,
        };
        return config;
    },

    _safeUpdateSelectedPaymentline(data) {
        const order = this.currentOrder;

        if (order && order.finalized) {
            return;
        }

        // Si no está finalizada, proceder normalmente
        this.updateSelectedPaymentline();
    },

    updateSelectedPaymentline(amount = false) {


        const order = this.currentOrder

        if (order && order.finalized) {
            console.log("[POS] Intento de modificar orden finalizada bloqueado");
            return;
        }

        const selectedPaymentLine = order.selected_paymentline;

        if (!selectedPaymentLine) return;

        if (this.state.isRefund && this._isOriginalPaymentMethod(selectedPaymentLine.payment_method.id)) {
            return;
        }

        super.updateSelectedPaymentline(amount);

        // Validar montos para métodos de pago no efectivo
        const selectedMethod = selectedPaymentLine.payment_method;
        const isCash = selectedMethod.is_cash_count || selectedMethod.type === "cash";

        if (!isCash) {
            const totalOrder = parseFloat(Math.abs(this.get_total_amount_order(order)).toFixed(2));
            const currentAmount = selectedPaymentLine.amount;
            const paymentName = selectedMethod.originalName || selectedMethod.name;

            // Validar que el monto no sea menor a 0 (excepto en reembolsos)
            if (currentAmount < 0 && !this.state.isRefund) {
                this.popup.add(ErrorPopup, {
                    title: _t("Monto inválido"),
                    body: _t(`El método de pago "${paymentName}" no puede tener un monto menor a 0.`),
                });
                selectedPaymentLine.set_amount(0);
                return;
            }

            // Validar que el monto no sea mayor al total de la factura
            if (currentAmount > totalOrder) {
                this.popup.add(ErrorPopup, {
                    title: _t("Monto excede el total"),
                    body: _t(`El método de pago "${paymentName}" no puede exceder el total de la factura ($${totalOrder.toFixed(2)}). Solo el efectivo puede exceder el total.`),
                });
                selectedPaymentLine.set_amount(totalOrder);
                return;
            }
        }


        if (selectedPaymentLine.payment_method.code_payment_method === "CREDITO") {
            // const total_amount = Math.abs(this.get_total_amount_order(order));
            const amountInstitucion = localStorage.getItem("AmoutIntitution");
            if (selectedPaymentLine.amount > amountInstitucion) {
                this.popup.add(ErrorPopup, {
                    title: _t("El monto excede el valor de crédito"),
                    body: _t("Se ajustará al valor máximo del crédito."),
                });
                selectedPaymentLine.set_amount(amountInstitucion)
                return;
            }

        }


        const paymentMethod = selectedPaymentLine.payment_method;

        if (paymentMethod.code_payment_method === "CTACLIENTE") {
            const availableCredit = this.state.creditNoteTotal || 0;

            const totalUsedCredit = this.currentOrder
                .get_paymentlines()
                .filter((line) => line.payment_method.code_payment_method === "CTACLIENTE")
                .reduce((sum, line) => sum + line.amount, 0);

            if (totalUsedCredit > availableCredit) {
                const excess = totalUsedCredit - availableCredit;
                const newAmount = selectedPaymentLine.amount - excess;
                selectedPaymentLine.set_amount(newAmount);

                this.popup.add(ErrorPopup, {
                    title: _t("Crédito Excedido"),
                    body: _t("El monto total supera el crédito disponible en notas de crédito."),
                });
            }
        } else if (paymentMethod.name.startsWith("Cuenta de cliente")) {
            const credit_partner = parseFloat(localStorage.getItem("credito")) || 0;

            const totalUsedCredit = this.currentOrder
                .get_paymentlines()
                .filter((line) => line.payment_method.name.startsWith("Cuenta de cliente"))
                .reduce((sum, line) => sum + line.amount, 0);

            if (totalUsedCredit > credit_partner) {
                const excess = totalUsedCredit - credit_partner;
                const newAmount = selectedPaymentLine.amount - excess;
                selectedPaymentLine.set_amount(newAmount);

                this.popup.add(ErrorPopup, {
                    title: _t("Crédito Excedido"),
                    body: _t("El monto total supera el crédito disponible en el crédito del cliente."),
                });
            }

        }
    },

    _isOriginalPaymentMethod(methodId) {
        if (!this.state.originalPaymentMethods) return false;
        return this.state.originalPaymentMethods.some(m => m.payment_method_id === methodId);
    },

    // is_consumer_final(order) {
    //     if (!order) {
    //         return false
    //     }
    //
    //     const partner = order.get_partner()
    //     return partner.vat === "9999999999999" || partner.name.toLowerCase() === "consumidor final"
    // },

    is_consumer_final(order) {
        try {
            if (!order) return false;

            const partner = order.get_partner();
            if (!partner) return false;

            const vatCheck = partner.vat === "9999999999999";
            const nameCheck = partner.name && partner.name.toLowerCase() === "consumidor final";

            return vatCheck || nameCheck;
        } catch (error) {
            console.error("Error in is_consumer_final:", error);
            return false;
        }
    },

    async selectInstitutionAndPay(pm, institutions) {
        if (!institutions || institutions.length === 0) {
            return null;
        }

        // Si solo hay 1 → retornamos directo
        if (institutions.length === 1) {
            return institutions[0];
        }

        // Mapeamos correctamente para el popup
        const choices = institutions.map((inst, index) => ({
            id: String(inst.institution_id ?? index),
            label: `${inst.institution_name} – $${inst.available_amount.toFixed(2)}`,
            item: inst,
        }));

        const {confirmed, payload} = await this.popup.add(SelectionPopup, {
            title: _t("Seleccione la institución"),
            list: choices,
        });

        if (!confirmed) return null;

        // Si payload ya es institución, retornarla
        if (payload && payload.institution_name) {
            return payload;
        }

        // Si payload es un id
        const idToMatch = String(payload?.id || payload);
        const choice = choices.find(c => String(c.id) === idToMatch);
        return choice ? choice.item : null;
    },


    async updatePaymentAsync() {
        this._updatePaymentMethodsDisplayNameWithAccontFavor();
        const institutions = await this.fetch_institutions_by_partner()
        const ORDER = this.currentOrder
        const institution_percentage = localStorage.getItem("percentageInstitution");
        let allPaymentMethods = [];
        const data = JSON.parse(institution_percentage);
        if (institution_percentage) {
            if (data.additional_discount_percentage > 0) {
                allPaymentMethods = this.pos.payment_methods
                    .filter((pm) =>
                        this.pos.config.payment_method_ids.includes(pm.id)
                    )
                    .filter((pm) => pm.name !== "CREDITO");
            } else {
                allPaymentMethods = this.pos.payment_methods.filter((pm) =>
                    this.pos.config.payment_method_ids.includes(pm.id)
                );
            }
        } else {
            let obj_institution = localStorage.getItem("result_institution_client");
            let is_exist_institucion = JSON.parse(obj_institution);

            if (is_exist_institucion) {
                allPaymentMethods = this.pos.payment_methods.filter((pm) =>
                    this.pos.config.payment_method_ids.includes(pm.id)
                );
            } else {
                allPaymentMethods = this.pos.payment_methods.filter((pm) =>
                    this.pos.config.payment_method_ids.includes(pm.id)
                );
            }

        }
        if (!institutions || institutions.length === 0) {
            allPaymentMethods = allPaymentMethods.filter(
                (pm) => pm.code_payment_method !== "CREDITO"
            );
        }

        const paymentLines = this.currentOrder.paymentlines;
        paymentLines.forEach(line => {
            this.currentOrder.remove_paymentline(line);
        });


        const cuentaAFavorClienteMethod = allPaymentMethods.find(pm => pm.code_payment_method === "CTACLIENTE");
        const cashMethod = allPaymentMethods.find(pm => pm.is_cash_count);
        const creditMethod = allPaymentMethods.find(pm => pm.code_payment_method === "CREDITO");


        const credit_partner = parseFloat(localStorage.getItem("credito")) || 0;

        if (this.state.isRefund) {
            let refundPaymentMethods = [];

            if (this.state.originalPaymentMethods && this.state.originalPaymentMethods.length > 0) {

                console.log("🔍 Original Payment Methods:", this.state.originalPaymentMethods);

                // Verificar si hay método CREDITO en los pagos originales
                const hasCreditMethod = this.state.originalPaymentMethods.some(
                    pm => pm.payment_method_name === "CREDITO"
                );

                if (hasCreditMethod) {
                    console.log("✅ Reembolso incluye método CREDITO");

                    // Buscar el credit_institution_id específico
                    const creditPayment = this.state.originalPaymentMethods.find(
                        pm => pm.payment_method_name === "CREDITO"
                    );

                    console.log("📌 Institution ID del pago original:", creditPayment.credit_institution_id);
                }


                let isWithinOneDay = this.state.originalPaymentMethods.some((pm) => {
                    const paymentDate = new Date(pm.order_date);
                    const now = new Date();
                    return paymentDate.toDateString() === now.toDateString();
                });

                let isCreditMethod = false;
                if (creditMethod) {
                    isCreditMethod = this.state.originalPaymentMethods.some(pm => pm.payment_method_id === creditMethod.id);
                }

                if (isCreditMethod) {
                    isWithinOneDay = this.state.originalPaymentMethods.some((pm) => {
                        const day_number = institutions[0].cut_off_date;
                        const orderDate = new Date(pm.order_date);
                        const orderMonth = orderDate.getMonth();
                        const orderYear = orderDate.getFullYear();

                        let cutOffDate;
                        if (orderDate.getDate() < day_number) {
                            cutOffDate = new Date(orderYear, orderMonth, day_number);
                        } else {
                            cutOffDate = new Date(orderYear, orderMonth + 1, day_number);
                        }
                        if (cutOffDate.getDate() !== day_number) {
                            cutOffDate.setDate(0);
                        }

                        const now = new Date();
                        return now < cutOffDate;
                    });
                }
                if (isWithinOneDay) {
                    const originalPaymentMethodIds = this.state.originalPaymentMethods.map(pm => pm.payment_method_id);
                    refundPaymentMethods = allPaymentMethods.filter((pm) =>
                        originalPaymentMethodIds.includes(pm.id)
                    );
                    refundPaymentMethods.forEach(line => {
                        this.addNewPaymentLine(line)
                    });

                } else {
                    if (cuentaAFavorClienteMethod && !refundPaymentMethods.includes(cuentaAFavorClienteMethod)) {
                        refundPaymentMethods.push(cuentaAFavorClienteMethod);
                    }
                    if (cuentaAFavorClienteMethod) {
                        this.addNewPaymentLine(cuentaAFavorClienteMethod)
                    }
                }
            }


            this.state.paymentMethods = refundPaymentMethods;
            if (this.state.isRefund) {
            } else {
                const paymentLines = this.currentOrder.get_paymentlines();
                paymentLines.forEach(line => {
                    if (line.payment_method.id !== cuentaAFavorClienteMethod?.id) {
                        if (ORDER.selected_paymentline === line) {
                            ORDER.select_paymentline(undefined);
                        }
                        this.currentOrder.paymentlines.remove(line);
                    }
                });
            }

        } else {

            if (this.state.clientHasCreditNotes) {
                const creditNoteTotal = this.state.creditNoteTotal || 0;
                if (creditNoteTotal === 0) {
                    this.state.paymentMethods = allPaymentMethods.filter(
                        (pm) => pm.code_payment_method !== "CTACLIENTE"
                    );

                } else {
                    this.state.paymentMethods = allPaymentMethods;
                }
            } else {
                this.state.paymentMethods = allPaymentMethods.filter(
                    (pm) => pm.code_payment_method !== "CTACLIENTE"
                );
            }
        }

        if (credit_partner <= 0) {
            this.state.paymentMethods = this.state.paymentMethods.filter(
                (pm) => pm.originalName !== "Cuenta de cliente"
            );

        }

        const cuenta_cliente = this.state.paymentMethods.filter(
            (pm) => pm.originalName === "Cuenta de cliente"
        );
        if (cuenta_cliente.length === 1) {
            this.state.paymentMethods = cuenta_cliente
        }

        if (this.is_consumer_final(ORDER)) {
            this.state.paymentMethods = this.state.paymentMethods.filter(
                (pm) => pm.id === cashMethod.id
            );
        }


        const order = this.pos.get_order();
        // const order_line = order.orderlines[0].sale_order_line_id;
        const order_line = order.orderlines[0]?.sale_order_line_id ?? null;
        const order_id = this.pos.orders[0].sale_id;
        const get_method_order_chatbot = await this.env.services.orm.call(
            'sale.order',
            'get_order_detail_chatbot',
            [order_id]
        );

        setTimeout(async () => {
            if (order_line !== undefined && order_id !== undefined) {
                const xTipoPago = (get_method_order_chatbot[0]?.x_tipo_pago || '').toString().toLocaleUpperCase();
                const sale_order = allPaymentMethods.find(pm => pm.code_payment_method === xTipoPago);

                if (sale_order) {
                    this.payment_methods_from_config = [sale_order];
                } else {
                    this.payment_methods_from_config = this.state.paymentMethods;
                }

                if (typeof this.renderElement === 'function') {
                    this.renderElement();
                } else if (typeof this.render === 'function') {
                    this.render();
                } else {
                    this.pos.set_screen('payment');
                }
            } else {

                this.payment_methods_from_config = this.state.paymentMethods;
                await this._updateNameCreditInstitutional(institutions);
                if (typeof this.renderElement === 'function') {
                    this.renderElement();
                } else if (typeof this.render === 'function') {
                    this.render();
                } else {
                    this.pos.set_screen('payment');
                }
            }
        }, 100);
    },

    _updatePaymentMethods() {
        this.updatePaymentAsync()
    },

    _updatePaymentMethodsDisplayNameWithAccontFavor() {
        const creditNoteTotal = this.state.creditNoteTotal || 0;
        const credit_partner = this.state.credit_partner;
        this.payment_methods_from_config.forEach((paymentMethod) => {

            if (paymentMethod.originalName === "Cuenta de cliente") {
                paymentMethod.name = `${paymentMethod.originalName} - Crédito: ${credit_partner.toFixed(2)}`;
            } else if (paymentMethod.code_payment_method === "CTACLIENTE") {
                paymentMethod.name = `${paymentMethod.originalName} - Crédito: ${creditNoteTotal.toFixed(2)}`;
            } else {
                paymentMethod.name = paymentMethod.originalName;
            }
        });
    },

    async fetch_institutions_by_partner() {
        try {
            const institutions = await this.orm.call(
                "institution.client",
                "get_institutions_by_partner",
                [this.pos.get_order().partner.id]
            );
            return institutions

        } catch (e) {
            return null
        }
    },

    async _updateNameCreditInstitutional(institutions) {
        try {
            if (institutions && institutions.length > 0) {
                this.payment_methods_from_config.forEach((paymentMethod) => {
                    if (paymentMethod.name.toLowerCase().includes("credito")) {
                        paymentMethod.name = `CREDITO  "${institutions[0].institution_name}" `;
                        paymentMethod.name += ` SALDO DISPONIBLE: $ ${institutions[0].available_amount.toFixed(2)}`;
                    }
                });

                if (institutions && institutions[0]?.available_amount) {
                    localStorage.setItem("AmoutIntitution", institutions[0].available_amount);
                }
            } else {

                // Filtra cualquier método de pago que contenga "credito"
                this.payment_methods_from_config = this.payment_methods_from_config.filter(
                    (paymentMethod) => !paymentMethod.name.toLowerCase().includes("credito")
                );
            }
        } catch (e) {
            console.log(e)
        }

    },

    _updatePaymentMethodsDisplayName() {
        const credit_partner = this.state.credit_partner;
        this.payment_methods_from_config.forEach((paymentMethod) => {
            if (!paymentMethod.originalName) {
                paymentMethod.originalName = paymentMethod.name;
            }
            // Always reset CREDITO to base name to avoid showing previous customer's institution
            if (paymentMethod.code_payment_method === "CREDITO") {
                paymentMethod.name = "CREDITO";
                paymentMethod.originalName = "CREDITO";  // Ensure originalName stays clean
            } else if (paymentMethod.originalName === "Cuenta de cliente") {
                paymentMethod.name = `${paymentMethod.originalName} - Crédito: ${credit_partner.toFixed(2)}`;
            } else {
                paymentMethod.name = paymentMethod.originalName;
            }
        });
    },

    async addNewPaymentLine(paymentMethod) {
        const order = this.currentOrder;

        if (order && order.finalized) {
            console.log("[POS] Intento de agregar línea de pago en orden finalizada bloqueado");
            return false;
        }

        var dato = ""

        if (this.state.isRefund && paymentMethod.code_payment_method === "CREDITO") {
            // Buscar los datos originales de este método en la venta
            let originalCredit = this.state.originalPaymentMethods.find(
                (pm) =>
                    pm.payment_method_id === paymentMethod.id &&
                    pm.credit_institution_id
            );

            // FALLBACK: Si no encontramos la institución, buscar cualquier pago CREDITO
            if (!originalCredit) {
                console.log("⚠️ No se encontró institución exacta, buscando alternativa...");
                originalCredit = this.state.originalPaymentMethods.find(
                    (pm) => pm.payment_method_name === "CREDITO" || pm.payment_method_name.includes("CREDITO")
                );
            }

            // FALLBACK 2: Buscar directamente las instituciones del cliente
            if (!originalCredit || !originalCredit.credit_institution_id) {
                console.log("⚠️ Buscando instituciones del cliente como último recurso...");
                const institutions = await this.fetch_institutions_by_partner();

                if (institutions && institutions.length > 0) {
                    // Si hay solo una institución, usarla automáticamente
                    if (institutions.length === 1) {
                        originalCredit = {
                            credit_institution_id: institutions[0].institution_id,
                            payment_method_id: paymentMethod.id
                        };
                        console.log("✅ Usando única institución del cliente:", institutions[0].institution_name);
                    } else {
                        // Si hay múltiples, mostrar selector
                        const selectionItems = institutions.map(inst => ({
                            id: inst.institution_id,
                            label: `${inst.institution_name} — Disponible: $${inst.available_amount.toFixed(2)}`,
                            item: inst
                        }));

                        const { confirmed, payload } = await this.popup.add(SelectionPopup, {
                            title: _t("Seleccione la institución para el reembolso"),
                            list: selectionItems
                        });

                        if (confirmed && payload) {
                            originalCredit = {
                                credit_institution_id: payload.institution_id,
                                payment_method_id: paymentMethod.id
                            };
                            console.log("✅ Institución seleccionada por usuario:", payload.institution_name);
                        } else {
                            return; // Usuario canceló
                        }
                    }
                }
            }

            if (!originalCredit || !originalCredit.credit_institution_id) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error en Reembolso"),
                    body: _t("No se encontró ninguna institución de crédito asociada al cliente."),
                });
                return;
            }

            const instId = originalCredit.credit_institution_id;
            console.log("🎯 Institution ID final para reembolso:", instId);

            // Ver si ya hay una línea de pago CREDITO en el reembolso
            const institutions = await this.fetch_institutions_by_partner();

            const specificInstitution = institutions.find(
                inst => inst.institution_id === instId
            );

            if (!specificInstitution) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error en Reembolso"),
                    body: _t(`No se encontró la institución con ID ${instId} para el cliente.`),
                });
                return;
            }

            console.log("✅ Institución encontrada para reembolso:", specificInstitution);

            localStorage.setItem("institution_selected", JSON.stringify(specificInstitution));
            localStorage.setItem("AmoutIntitution", specificInstitution.available_amount);

            paymentMethod.name = `CREDITO "${specificInstitution.institution_name}" — $${specificInstitution.available_amount.toFixed(2)}`;
            // Note: Do NOT overwrite originalName here - keep it as "CREDITO" for reset purposes

            // Ver si ya hay una línea de pago CREDITO en el reembolso
            let paymentline = order
                .get_paymentlines()
                .find((line) => line.payment_method.id === paymentMethod.id);

            if (!paymentline) {
                // Crear la línea de pago
                super.addNewPaymentLine(paymentMethod);
                paymentline = this.pos.get_order().selected_paymentline;
            } else {
                order.select_paymentline(paymentline);
            }

            // Asignar la institución correcta usando el objeto completo
            paymentline.set_selecteInstitutionCredit(instId);
            paymentline.institution_discount = instId;

            await this._simulateClickOnPaymentButton(paymentMethod.id);

            await this.ordenate_paymentLines();
            return;
        }

        if (paymentMethod.code_payment_method === "CREDITO") {
            const institutions = await this.fetch_institutions_by_partner();
            const inst = await this.selectInstitutionAndPay(paymentMethod, institutions);
            dato = inst;
            if (!inst) return;

            if (inst.available_amount <= 0) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Crédito no disponible"),
                    body: _t(
                        `La institución "${inst.institution_name}" no tiene saldo disponible.`
                    ),
                });
                return;
            }

            localStorage.setItem("institution_selected", JSON.stringify(inst));
            localStorage.setItem("AmoutIntitution", inst.available_amount);

            // const paymentline = this.pos.get_order().selected_paymentline;
            // if (paymentline) {
            //     paymentline.set_selecteInstitutionCredit(inst.institution_id);
            //     console.log("Institution ID set:", inst.institution_id);
            // }

            paymentMethod.name = `CREDITO "${inst.institution_name}" – $${inst.available_amount.toFixed(2)}`;
            // Note: Do NOT overwrite originalName here - keep it as "CREDITO" for reset purposes
        }

        const creditError = await this.verifyMethodCreditAmount(paymentMethod);
        if (creditError) return;

        const paymentLines = order.get_paymentlines();

        let hasError = false;
        if (order.get_orderlines()[0]?.refunded_orderline_id) {
            hasError = await this.rules_with_refund(paymentLines, paymentMethod, order);
        } else {
            hasError = await this.rules_without_refund(paymentLines, paymentMethod, order);
        }

        // Si hubo error en las validaciones, no continuar
        if (hasError) {
            return;
        }

        let lineExists = order
            .get_paymentlines()
            .some((line) => line.payment_method.id === paymentMethod.id);

        if (!lineExists) {
            super.addNewPaymentLine(paymentMethod);
        }

        const paymentline = this.pos.get_order().selected_paymentline;
        if (paymentMethod.code_payment_method === "CREDITO" && paymentline && dato) {
            paymentline.set_selecteInstitutionCredit(dato.institution_id);
            console.log("✅ Institution ID set for normal sale:", dato.institution_id);
        }

        await this.ordenate_paymentLines();
    },

    async _simulateClickOnPaymentButton(paymentMethodId) {
        await new Promise(resolve => setTimeout(resolve, 100));

        try {
            const paymentButtons = document.querySelectorAll('.paymentmethod');

            console.log(`🔍 Buscando botón para payment method ID: ${paymentMethodId}`);
            console.log(`📋 Total de botones encontrados: ${paymentButtons.length}`);

            for (const button of paymentButtons) {
                // Buscar por el contenido de texto del botón
                const paymentNameElement = button.querySelector('.payment-name');
                const buttonText = paymentNameElement ? paymentNameElement.textContent : button.textContent;

                console.log(`🔎 Analizando botón con texto: "${buttonText?.trim().substring(0, 50)}..."`);

                // Si el texto contiene "CREDITO" y es el método que buscamos
                if (buttonText && buttonText.toUpperCase().includes('CREDITO')) {
                    console.log("🎯 Botón CREDITO encontrado por texto, simulando click...");

                    // Hacer scroll al botón para asegurar que sea visible
                    button.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    await new Promise(resolve => setTimeout(resolve, 100));

                    // Simular eventos de mouse completos
                    const mousedownEvent = new MouseEvent('mousedown', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    button.dispatchEvent(mousedownEvent);

                    await new Promise(resolve => setTimeout(resolve, 50));

                    const clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    button.dispatchEvent(clickEvent);

                    await new Promise(resolve => setTimeout(resolve, 50));

                    const mouseupEvent = new MouseEvent('mouseup', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    button.dispatchEvent(mouseupEvent);

                    console.log("✅ Click simulado exitosamente en botón CREDITO");
                    break;
                }
            }
        } catch (error) {
            console.error("❌ Error al simular click:", error);
        }
    },

    async ordenate_paymentLines() {
        const order = this.currentOrder;
        const paymentLines = order.get_paymentlines();
        if (paymentLines.length > 1) {
            const nonCashLines = paymentLines.filter(line => !line.payment_method.is_cash_count);
            const cashLines = paymentLines.filter(line => line.payment_method.is_cash_count);

            const originalCollection = this.currentOrder.paymentlines;
            originalCollection.reset([]);
            nonCashLines.forEach(line => originalCollection.add(line));
            cashLines.forEach(line => originalCollection.add(line));
        }
    },

    async rules_with_refund(paymentLines, paymentMethod, order) {
        const cuentaAFavorClienteMethod = this.pos.payment_methods.find(pm => pm.code_payment_method === "CTACLIENTE");
        const isCuentaAFavorClienteSelected = paymentLines.some(
            (line) => line.payment_method.id === cuentaAFavorClienteMethod?.id
        );

        if (paymentMethod.id === cuentaAFavorClienteMethod?.id) {
            if (paymentLines.length > 0) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Método de Pago Inválido"),
                    body: _t("No es posible usar 'Cuenta a favor cliente' com otro métodos de pago. Elimine primero los otros metodos de pago."),
                });
                return true; // Indica que hubo error
            }
        } else {
            if (isCuentaAFavorClienteSelected) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Método de Pago Inválido"),
                    body: _t("No es posible usar otros métodos de pago con 'Cuenta a favor cliente'. Primero elimine el método pago 'Cuenta a favor cliente'."),
                });
                return true; // Indica que hubo error
            }
        }

        const existingLine = paymentLines.find(
            (line) => line.payment_method.id === paymentMethod.id
        );

        if (existingLine) {
            order.select_paymentline(existingLine);
        } else {
            if (this.state.isRefund && this._isOriginalPaymentMethod(paymentMethod.id)) {
                super.addNewPaymentLine(paymentMethod);
                const newLine = order.selected_paymentline;
                const originalAmount = this.state.originalAmountsByMethodId[paymentMethod.id];
                if (originalAmount !== undefined) {
                    const difference = this.is_order_with_change(order);
                    if (difference && newLine.payment_method?.is_cash_count) {
                        const newAmount = difference + originalAmount
                        newLine.set_amount(newAmount);
                    } else {
                        newLine.set_amount(originalAmount);
                    }
                }
            } else {
                super.addNewPaymentLine(paymentMethod);
            }
        }
        return false; // Sin error
    },

    is_order_with_change(order) {
        const total_amount = Math.abs(this.get_total_amount_order(order));
        const payment_lines = Object.values(this.state.originalAmountsByMethodId)
            .map(num => Math.abs(num))
            .reduce((a, b) => a + b, 0);

        if (payment_lines > total_amount) {
            return payment_lines - total_amount
        }
        return 0
    },

    get_total_amount_order(order) {
        return order.get_total_with_tax() + order.get_rounding_applied();
    },

    async verifyMethodCreditAmount(paymentMethod) {
        const order = this.currentOrder;

        if (paymentMethod.code_payment_method !== "CREDITO") {
            return false;
        }

        const allowed = parseFloat(localStorage.getItem("AmoutIntitution") || 0);
        const due = Math.abs(order.get_due());

        if (allowed <= 0) {
            await this.popup.add(ErrorPopup, {
                title: _t("Crédito no disponible"),
                body: _t("No existe saldo disponible en la institución seleccionada."),
            });
            return true; // error
        }

        if (allowed < due) {
            // Esto NO agrega líneas, solo informa
            return false;
        }

        return false;
    },


    async rules_without_refund(paymentLines, paymentMethod, order) {
        const cuentaAFavorClienteMethod = this.pos.payment_methods.find(pm => pm.code_payment_method === "CTACLIENTE");
        const isCuentaAFavorClienteSelected = paymentLines.some(
            (line) => line.payment_method.id === cuentaAFavorClienteMethod?.id
        );

        if (isCuentaAFavorClienteSelected) {
            if (paymentMethod.is_cash_count || paymentMethod.originalName === "CREDITO") {
                super.addNewPaymentLine(paymentMethod);
                return false; // Sin error, ya se agregó la línea
            } else {
                await this.popup.add(ErrorPopup, {
                    title: _t("Método de Pago Inválido"),
                    body: "EL método de pago Saldo a favor cliente, solo puedes combinarlo con Efectivo",
                });
                return true; // Indica que hubo error
            }

        }

        if (paymentMethod.id === cuentaAFavorClienteMethod?.id) {
            if (paymentLines.length <= 1) {
                const isCashLineSelected = paymentLines.some(
                    (line) => line.payment_method.is_cash_count === true
                );

                if (paymentLines.length === 0) {
                    const creditNoteTotal = this.state.creditNoteTotal || 0;
                    if (order.get_due() >= creditNoteTotal) {
                        super.addNewPaymentLine(paymentMethod);
                        const newLine = order.selected_paymentline;
                        newLine.set_amount(creditNoteTotal);
                        return false; // Sin error, ya se agregó la línea
                    } else {
                        await this.popup.add(ErrorPopup, {
                            title: _t("El valor de la orden no es suficiente"),
                            body: _t("No es posible usar 'Cuenta a favor cliente' porque se debe usar todo el monto para realizar la compra."),
                        });
                        return true; // Indica que hubo error
                    }
                } else if (isCashLineSelected) {
                    const creditNoteTotal = this.state.creditNoteTotal || 0;
                    const total_order = this.get_total_amount_order(order)
                    if (total_order >= creditNoteTotal) {
                        const diference = this.get_total_amount_order(order) - creditNoteTotal
                        const cash_line = order.selected_paymentline;
                        if (diference < 0) {
                            cash_line.set_amount(0);
                        } else {
                            cash_line.set_amount(diference);
                        }
                        super.addNewPaymentLine(paymentMethod);
                        const newLine = order.selected_paymentline;
                        newLine.set_amount(creditNoteTotal);
                        return false; // Sin error, ya se agregó la línea
                    } else {
                        return true; // Indica que hubo error
                    }


                } else {
                    console.log("eeeeeee")
                    return true; // Caso no manejado, tratar como error
                }
            } else {
                await this.popup.add(ErrorPopup, {
                    title: _t("Método de Pago Inválido"),
                    body: _t("No es posible usar esos metodos de pagos juntos."),
                });
                return true; // Indica que hubo error
            }

        }

        // No llamar a super aquí, se hace en addNewPaymentLine
        return false; // Sin error

    },


    async check_credit_partner(paymentMethod) {
        const currentOrder = this.env.services.pos.get_order();
        const credit_partner = parseFloat(localStorage.getItem("credito")) || 0;

        if (paymentMethod.name.startsWith("Cuenta de cliente")) {
            const totalUsedCredit = currentOrder
                .get_paymentlines()
                .filter((line) => line.payment_method.name.startsWith("Cuenta de cliente"))
                .reduce((sum, line) => sum + line.amount, 0);

            if (totalUsedCredit >= credit_partner) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Crédito Insuficiente"),
                    body: _t("El cliente no tiene suficiente crédito para esta compra."),
                });
                return false;
            }
        }
        return true;
    },

    async validateOrder(isForceValidate) {

        const order = this.currentOrder;

        // Validar que las líneas de pago CREDITO tengan la institución seteada
        const creditPaymentLines = order.get_paymentlines().filter(
            (line) => line.payment_method.code_payment_method === "CREDITO"
        );

        for (const creditLine of creditPaymentLines) {
            const institutionId = creditLine.get_selecteInstitutionCredit();
            if (!institutionId) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Institución de crédito no seleccionada"),
                    body: _t("Debe seleccionar una institución de crédito válida antes de validar el pago."),
                });
                order.remove_paymentline(creditLine);
                return;
            }
        }

        const paymentLinesFavorCliente = order.get_paymentlines().filter(
            (line) => line.payment_method.code_payment_method === "CTACLIENTE"
        );

        if (this.state.isRefund && this.state.originalPaymentMethods && this.state.originalPaymentMethods.length > 0 && paymentLinesFavorCliente.length === 0) {
            const currentPaymentLines = order.get_paymentlines();
            const originalPaymentMethodIds = this.state.originalPaymentMethods.map(m => m.payment_method_id);
            const currentPaymentMethodsIds = currentPaymentLines.map(l => l.payment_method.id);

            for (const originalPMId of originalPaymentMethodIds) {
                if (!currentPaymentMethodsIds.includes(originalPMId)) {
                    this.popup.add(ErrorPopup, {
                        title: _t("Error de Reembolso"),
                        body: _t("Para realizar el reembolso, es necesario utilizar todos los métodos de pago originales de la compra."),
                    });
                    return;
                }
            }
        }


        const paymentLinesUserAccount = order.get_paymentlines().filter(
            (line) => line.payment_method.name.startsWith("Cuenta de cliente")
        );


        const promises = [];

        if (paymentLinesUserAccount.length > 0) {
            try {
                const storedResult = JSON.parse(localStorage.getItem("result_institution_client"));
                const institutionClient = storedResult[0];
                const availableAmount = institutionClient.available_amount;

                const amountPaidWithCuentaCliente = paymentLinesUserAccount.reduce((sum, line) => sum + line.amount, 0);
                const newAvailableAmount = availableAmount - amountPaidWithCuentaCliente;

                const updateCreditPromise = this.orm.write("institution.client", [institutionClient.id], {
                    available_amount: newAvailableAmount,
                });
                promises.push(updateCreditPromise);
                localStorage.setItem('credito', newAvailableAmount.toString());
            } catch (e) {
                console.log(e)
            }
        }

        if (paymentLinesFavorCliente.length > 0) {
            const client = order.get_partner();

            if (client) {
                const amountPaidWithCreditNotes = paymentLinesFavorCliente.reduce((sum, line) => sum + line.amount, 0);

                const updateCreditNotesPromise = this.orm.searchRead(
                    "account.move",
                    [
                        ["partner_id", "=", client.id],
                        ["move_type", "=", "out_refund"],
                        ["state", "=", "posted"],
                    ],
                    ["note_credit"]
                ).then((creditNotes) => {
                    let remainingAmount = amountPaidWithCreditNotes;
                    const writePromises = [];

                    for (const creditNote of creditNotes) {
                        if (remainingAmount <= 0) break;

                        const deduction = Math.min(remainingAmount, creditNote.note_credit);
                        remainingAmount -= deduction;

                        const writePromise = this.orm.write("account.move", [creditNote.id], {
                            note_credit: creditNote.note_credit - deduction,
                        });
                        writePromises.push(writePromise);
                    }

                    return Promise.all(writePromises);
                });

                promises.push(updateCreditNotesPromise);
            }
        }

        Promise.all(promises)
            .then(() => {
                super.validateOrder(isForceValidate);
            })
            .catch((error) => {
                console.log(error)
                this.popup.add(ErrorPopup, {
                    title: _t("Error de Validación"),
                    body: _t("Se produjo un error durante la validación del pedido."),
                });
            });
    },
});