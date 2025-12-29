/** @odoo-module */
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {patch} from "@web/core/utils/patch";
import {CheckInfoPopup} from "@pos_custom_check/js/check_info_popup";
import {get_order_chatbot} from "@pos_custom_check/js/custom_loyalty";
import {usePos} from "@point_of_sale/app/store/pos_hook";


/**
 * Restringue que solo puedan existir dos métodos de pago;
 * cuando se seleccionen dos metodos de pago de por obligación
 * uno de ellos debe ser en efectivo
 * **/

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.payment_restrictions) {
            const paymentLines = this.currentOrder.get_paymentlines();
            if (paymentLines.length >= 2) {
                this.popup.add(ErrorPopup, {
                    title: "Restricción de Métodos de Pago",
                    body: "No puedes seleccionar más de dos métodos de pago para esta factura.",
                });
                return;
            }

            if (paymentLines.length === 1) {
                const firstMethod = paymentLines[0].name.toLowerCase();
                const secondMethod = paymentMethod.name.toLowerCase();

                const isFirstCredit = firstMethod.includes('credito');
                const isFirstCash = firstMethod.includes('efectivo') || firstMethod.includes('efect');

                const isSecondCredit = secondMethod.includes('credito');
                const isSecondCash = secondMethod.includes('efectivo') || secondMethod.includes('efect');

                // Si el primer método es crédito
                if (isFirstCredit) {
                    if (!isSecondCash) {
                        this.popup.add(ErrorPopup, {
                            title: "Restricción de Métodos de Pago",
                            body: "El método de pago CREDITO solo puede combinarse con EFECTIVO.",
                        });
                        return;
                    }
                }
                // Si el primer método es tarjeta o cheque (no efectivo ni crédito)
                else if (!isFirstCash && !isFirstCredit) {
                    if (!isSecondCash) {
                        this.popup.add(ErrorPopup, {
                            title: "Restricción de Métodos de Pago",
                            body: 'Los métodos de pago como TARJETA o CHEQUE / TRANSFERENCIA solo pueden combinarse con EFECTIVO.',
                        });
                        return;
                    }
                }
            }


        } else {
            super.addNewPaymentLine(paymentMethod);
        }
        super.addNewPaymentLine(paymentMethod);
        // abri el modal de informacionde la tarjeta o transferencia
        let check_info = []
        const is_credit_note = await this._veriffy_is_credit_note(this.currentOrder.orderlines)
        if (!is_credit_note) {
            if (paymentMethod.name.toLowerCase().includes('tarjeta')) {
                await this.get_order_chatbot(this.pos.orders[0].sale_id)
                check_info = []
                check_info = await this.currentOrder.selected_paymentline.getCheckInfo()
                if (check_info) {
                    await this._show_payment_info_modal(check_info)
                }
            }
            if (paymentMethod.name.toLowerCase().includes('cheque') || paymentMethod.name.toLowerCase().includes('transferencia')) {
                check_info = []
                check_info = await this.currentOrder.selected_paymentline.getCheckInfo()
                if (check_info) {
                    await this._show_payment_info_modal(check_info)
                }
            }
        }


    },

    validatePaymentReturn() {
        const pos = this.pos || this.env?.services?.pos;
        if (!pos) {
            console.warn("POS service no disponible");
            return;
        }

        const order = pos.get_order();

        // Bandera para saber si encontramos una línea bloqueante
        let foundBlockingLine = false;

        for (const paymentline of order.paymentlines) {
            if (
                (paymentline.name === "CHEQUE / TRANSF")
            ) {
                foundBlockingLine = true;
                this.popup.add(ErrorPopup, {
                    title: "Alerta de pago",
                    body: `No puede volver a la pantalla anterior ya que hubo una validación de pago con ${paymentline.payment_bank_name}.`,
                });
                break;
            } else if (
                paymentline.name === "TARJETA"
            ){
                foundBlockingLine = true;
                this.popup.add(ErrorPopup, {
                    title: "Alerta de pago",
                    body: `No puede volver a la pantalla anterior ya que hubo una validación de pago con Tarjeta.`,
                });
                break;
            }
        }

        // Si no hay línea bloqueante, volvemos a ProductScreen
        if (!foundBlockingLine) {
            pos.showScreen("ProductScreen");
        }
    },

    async get_order_chatbot(id_order) {
        try {
            const order = this.pos.get_order();
            // const order_line = order.orderlines[0].sale_order_line_id;
            const order_line = order.orderlines[0]?.sale_order_line_id ?? null;
            const order_id = this.pos.orders[0].sale_id;
            if (order_line !== undefined && order_id !== undefined) {
                const get_method_order_chatbot = await this.env.services.orm.call(
                    'sale.order',
                    'get_order_detail_chatbot',
                    [order_id]
                );
                if (get_method_order_chatbot.length > 0 && get_method_order_chatbot[0].x_channel === "canal digital") {
                    const jsonString = get_method_order_chatbot[0].card_info;
                    let JSON_object;
                    try {
                        JSON_object = JSON.parse(jsonString);
                    } catch (parseError) {
                        console.error("Error parsing card_info JSON:", parseError);
                        return {
                            card: {
                                bin: null,
                                type: null,
                                number: null,
                                holder_name: null
                            }
                        };
                    }

                    setTimeout(() => {
                        try {
                            const bin_tc = document.getElementById('bin_tc');
                            const number_voucher = document.getElementById('number_voucher');
                            const number_lote = document.getElementById('number_lote');
                            const holder_card = document.getElementById('holder_card');

                            // Check if JSON_object.card exists and has the required properties
                            if (JSON_object.card && JSON_object.card.bin && JSON_object.card.number && JSON_object.card.holder_name) {
                                bin_tc.value = JSON_object.card.bin;
                                number_voucher.value = JSON_object.card.number;
                                number_lote.value = JSON_object.card.number;
                                holder_card.value = JSON_object.card.holder_name;
                            } else {
                                // Optionally, set default values or skip
                                bin_tc.value = '';
                                number_voucher.value = '';
                                number_lote.value = '';
                                holder_card.value = '';
                            }
                        } catch (error) {
                            console.error("Error accessing card properties:", error);
                            // Set default values for the fields
                            const bin_tc = document.getElementById('bin_tc');
                            const number_voucher = document.getElementById('number_voucher');
                            const number_lote = document.getElementById('number_lote');
                            const holder_card = document.getElementById('holder_card');
                            bin_tc.value = '';
                            number_voucher.value = '';
                            number_lote.value = '';
                            holder_card.value = '';
                        }
                    }, 1000);
                }
            }
            return {
                card: {
                    bin: null,
                    type: null,
                    number: null,
                    holder_name: null
                }
            };
        } catch (error) {
            console.error("Error al obtener datos del chatbot:", error);
            return {
                card: {
                    bin: null,
                    type: null,
                    number: null,
                    holder_name: null
                }
            };
        }
    },

    async _show_payment_info_modal(check_info = []) {
        const {confirmed} = await this.popup.add(CheckInfoPopup, {
            title: 'Información de pago',
            array: check_info,
        });
    },
    async _veriffy_is_credit_note(orderlines) {
        let is_credit_note = false
        if (orderlines[0].refunded_orderline_id > 0) {
            is_credit_note = true
        }
        return is_credit_note
    }
});