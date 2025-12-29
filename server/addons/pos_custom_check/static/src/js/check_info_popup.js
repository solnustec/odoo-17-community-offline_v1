/** @odoo-module */

import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {_t} from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {useState, onWillStart, onMounted} from "@odoo/owl";
import {PaymentStatusPopup} from "./payment_status_popup";
import {PaymentStatusAhoritaPopup} from "./payment_status_popup_ahorita";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

export class CheckInfoPopup extends AbstractAwaitablePopup {
    static template = "pos_custom_check.CheckInfoPopup";
    static defaultProps = {
        confirmText: _t("Apply"),
        title: _t(""),
        body: '',
        cancelText: _t("Cancel"),
    };

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.notificationService = useService("notification");
        this.rpc = useService("rpc");
        this.orm = useService("orm");


        // Ordenar bancos por id_bank
        this.orderedBanks = [...this.pos.banks].sort((a, b) => {
            if (a.bic < b.bic) return -1;
            if (a.bic > b.bic) return 1;
            return 0;
        });

        const selected_paymentline = this.pos.get_order().selected_paymentline;

        const deunaBank = this.pos.banks.find(bank => bank.name === "DEUNA BCO PICHINCHA");
        const ahoritaBank = this.pos.banks.find(bank => bank.name === "AHORITA BANCO DE LOJA");

        this.state = useState({
            payment_method: this.props.array.payment_method || {type: ''},
            bank_name: this.props.array.bank_name || '',
            owner_name: this.props.array.owner_name || '',
            check_number: this.props.array.check_number || '',
            bank_account: this.props.array.bank_account || '',
            type_card: this.props.array.type_card || '',
            number_voucher: this.props.array.number_voucher || '',
            number_lote: this.props.array.number_lote || '',
            holder_card: this.props.array.holder_card || '',
            bin_tc: this.props.array.bin_tc || '',
            institution_cheque: this.props.array.institution_cheque || '',
            institution_card: this.props.array.institution_card || '',
            orderer_identification: this.props.array.orderer_identification || '',
            date: this.props.array.date || (new Date().toISOString().slice(0, 10)),
            qrCode: null,
            deeplink: null,
            phone_user: '',
            transactionId: null,
            isFieldsReadonly: false,
            enable_advanced_payments: false,
            payment_status: null,
            payment_amount: selected_paymentline ? parseFloat(selected_paymentline.amount) || 0.0 : 0.0,
            bank_id: this.props.array.bank_id || '',
            success_message: '',
            generated_amount: null,
            generated_phone: null,
        });

        onWillStart(async () => {
            this.state.owner_name = this.pos.get_order().partner.name.trim() || '';

            const order = this.pos.get_order();
            const order_id = order.sale_id;

            if (order_id) {
                const result = await this.env.services.orm.call(
                    'sale.order',
                    'get_order_detail_chatbot',
                    [order_id]
                );
                const orderData = result?.[0] || {};
                const x_channel = orderData.x_channel || '';
                const pay_deuna_id = orderData.pay_deuna_id || null;
                const pay_ahorita_id = orderData.pay_ahorita_id || null;

                this.state.channel = x_channel;
                this.state.transactionId = pay_deuna_id;
                this.state.transactionId = pay_ahorita_id;

                // Caso 1: Canal digital CON pay_deuna_id
                if (x_channel === "canal digital" && pay_deuna_id && deunaBank) {
                    this.state.bank_name = deunaBank.name;
                    this.state.bank_id = deunaBank.id;
                    this.state.bank_codigo = deunaBank.codigo_banco;
                    this.state.enable_advanced_payments = true;
                    this.state.payment_status = "APPROVED";
                    // this.state.isFieldsReadonly = true;

                    // Rellenar automáticamente los campos si hay datos
                    if (orderData.payment_details) {
                        this.state.bank_account = orderData.payment_details.transfer_number || '';
                        this.state.check_number = orderData.payment_details.transfer_number || '';
                        this.state.orderer_identification = orderData.payment_details.orderer_identification || '';
                    }
                } else if (x_channel === "canal digital" && pay_ahorita_id && ahoritaBank) {
                    this.state.bank_name = ahoritaBank.name;
                    this.state.bank_id = ahoritaBank.id;
                    this.state.bank_codigo = ahoritaBank.codigo_banco;
                    this.state.enable_advanced_payments = true;
                    this.state.payment_status = "payment_confirmed";
                    // this.state.isFieldsReadonly = true;

                    // Rellenar automáticamente los campos si hay datos
                    if (orderData.payment_details) {
                        this.state.bank_account = orderData.payment_details.transfer_number || '';
                        this.state.check_number = orderData.payment_details.transfer_number || '';
                        this.state.orderer_identification = orderData.payment_details.orderer_identification || '';
                    }
                }
            }

            this.syncToPaymentline();
            await this.updateAdvancedPayments();
            this.syncToPaymentline();
        });
        onMounted(() => {
            this.formatPaymentAmount();
        });
    }

    syncToPaymentline() {
        const spl = this.pos.get_order().selected_paymentline;
        if (!spl) return;
        spl.payment_bank_name = this.state.bank_name || '';
        spl.enable_advanced_payments = !!this.state.enable_advanced_payments;
        spl.channel = this.state.channel || '';
    }

    async updateAdvancedPayments() {

        if (this.state.bank_name === 'DEUNA BCO PICHINCHA') {
            try {
                const order = this.pos.get_order();
                const order_id = order.sale_id;

                if (order_id) {
                    const result = await this.env.services.orm.call(
                        'sale.order',
                        'get_order_detail_chatbot',
                        [order_id]
                    );
                    const x_channel = result?.[0]?.x_channel || '';
                    const pay_deuna_id = result?.[0]?.pay_deuna_id || null;
                    this.state.channel = x_channel;
                    this.state.transactionId = pay_deuna_id;
                } else {
                    this.state.transactionId = null;
                }
                const pos_session_id = this.pos.pos_session.id;
                const config = await this.rpc('/get_deuna_config', {
                    pos_session_id: this.pos.pos_session.id,
                });
                this.state.enable_advanced_payments = config.enable_advanced_payments || false;
            } catch (error) {
                console.error('Error fetching DEUNA config:', error);
                this.state.enable_advanced_payments = false;
            }
        } else if (this.state.bank_name === 'AHORITA BANCO DE LOJA') {
            try {
                const order = this.pos.get_order();
                const order_id = order.sale_id;

                if (order_id) {
                    const result = await this.env.services.orm.call(
                        'sale.order',
                        'get_order_detail_chatbot',
                        [order_id]
                    );
                    const x_channel = result?.[0]?.x_channel || '';
                    const pay_ahorita_id = result?.[0]?.pay_ahorita_id || null;
                    this.state.channel = x_channel;
                    this.state.transactionId = pay_ahorita_id;
                } else {
                    this.state.transactionId = null;
                }
                const pos_session_id = this.pos.pos_session.id;
                const config = await this.rpc('/get_ahorita_config', {
                    pos_session_id: this.pos.pos_session.id,
                });
                this.state.enable_advanced_payments = config.enable_advanced_payments || false;
            } catch (error) {
                console.error('Error fetching AHORITA config:', error);
                this.state.enable_advanced_payments = false;
            }
        } else {
            this.state.enable_advanced_payments = false;
        }

        this.syncToPaymentline();
    }

    onPaymentAmountChange(event) {
        const value = event.target.value;
        // Handle empty input or invalid values
        if (value === '' || value === '.') {
            this.state.payment_amount = 0.0;
        } else {
            const parsedValue = parseFloat(value);
            this.state.payment_amount = isNaN(parsedValue) ? 0.0 : parsedValue;
        }
    }

    //funcaio para formatear a dos decimales el input de monto de pago en ahoraita y bando de pichincha
    formatPaymentAmount(/* event */) {
        const rounded = Math.round((this.state.payment_amount || 0) * 100) / 100;
        this.state.payment_amount = rounded;
        const input = document.getElementById('payment_amount');
        if (input) {
            input.value = rounded.toFixed(2);
        }
    }

    async validateFields() {
        try {
            let requiredFields = [];
            if (this.state.payment_method.name.includes('CHEQUE') || this.state.payment_method.name.includes('TRANSF')) {
                requiredFields = ["bank_name", "owner_name", "bank_account", "check_number"];
                if (this.state.enable_advanced_payments && this.state.bank_codigo === 'DEUNA BCO PICHINCHA') {
                    requiredFields.push("orderer_identification");
                } else if (this.state.enable_advanced_payments && this.state.bank_codigo === 'AHORITA BANCO DE LOJA') {
                    requiredFields.push("orderer_identification");
                }
            }

            if (this.state.payment_method.name.includes('TARJETA')) {
                requiredFields = ["number_voucher", "type_card", "number_lote", "holder_card", "bin_tc"];
            }

            if (this.state.payment_method.name.includes('EFECTIVO') || this.state.payment_method.name.includes('EFECT')) {
                requiredFields = [];
            }

            // Validar el monto de pago
            const selected_paymentline = this.pos.get_order().selected_paymentline;
            if (this.state.payment_method.name.includes('CHEQUE') || this.state.payment_method.name.includes('TRANSF')) {
                if (isNaN(this.state.payment_amount) || this.state.payment_amount <= 0) {
                    await this.popup.add(ErrorPopup, {
                        title: _t("Error"),
                        body: _t("El monto de pago debe ser mayor que cero y un número válido."),
                    });
                    return false;
                }
                if (this.state.payment_amount > parseFloat(selected_paymentline.amount)) {
                    await this.popup.add(ErrorPopup, {
                        title: _t("Error"),
                        body: _t("El monto de pago no puede ser mayor que el monto original."),
                    });
                    return false;
                }
            }

            for (let field of requiredFields) {
                if (!this.state[field]) {
                    await this.popup.add(ErrorPopup, {
                        title: _t("Error"),
                        body: `El campo ${field} no puede estar vacío.`,
                    });
                    return false;
                }
            }
            return true;
        } catch (error) {
            console.error('Error validating fields:', error);
            return false;
        }
    }

    /**
     * Obtiene y valida el ID de institución desde localStorage
     * @returns {string|null} ID válido de institución o null si no es válido
     */
    getValidInstitutionId() {
        try {
            const institution_id = localStorage.getItem("institutionId");
            if (!institution_id) return null;

            const parsed = JSON.parse(institution_id);
            // Validar que no sea vacío, cero, o solo ceros
            if (!parsed || parsed === "000000000000" || parseInt(parsed, 10) === 0) {
                return null;
            }
            return parsed;
        } catch (error) {
            console.error('Error parsing institutionId:', error);
            return null;
        }
    }

    /**
     * Obtiene y valida los datos de la institución desde localStorage
     * @returns {object|null} Objeto de institución o null si no es válido
     */
    getValidInstitutionData() {
        try {
            const institution = localStorage.getItem("percentageInstitution");
            if (!institution) return null;

            const obj = JSON.parse(institution);
            // Validar que tenga id_institutions válido
            if (!obj || !obj.id_institutions || obj.id_institutions === "000000000000" || parseInt(obj.id_institutions, 10) === 0) {
                return null;
            }
            return obj;
        } catch (error) {
            console.error('Error parsing percentageInstitution:', error);
            return null;
        }
    }

    async confirm() {
        const order = this.pos.get_order();
        const selected_paymentline = order.selected_paymentline;
        if (this.state.payment_method.name === "CHEQUE / TRANSF") {
            const owner_name = document.getElementById("owner_name")?.value;
            const check_number = document.getElementById("check_number")?.value;
            const bank_account = document.getElementById("bank_account")?.value;
            const bank_id = document.getElementById("bank_id")?.value;

            // Usar métodos de validación para obtener datos de institución
            const obj = this.getValidInstitutionData();
            const data_order = this.getValidInstitutionId();
            const orderer_identification = this.state.orderer_identification || '';
            const response_obj = await this.orm.call("digital.payment.config", "get_enable_digital_payment", []);
            let select_options = document.getElementById("bank_id").value;

            if (
                this.state.enable_advanced_payments &&
                ['DEUNA BCO PICHINCHA', 'AHORITA BANCO DE LOJA'].includes(this.state.bank_name) &&
                !['APPROVED', 'CONFIRMADO', 'APROBADO'].includes(this.state.payment_status)
            ) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Pago no aprobado"),
                    body: _t("La transacción aún no ha sido aprobada. Valide el estado del pago antes de continuar."),
                });
                return;
            }


            if (!bank_id || bank_id === "") {
                await this.popup.add(ErrorPopup, {
                    title: _t("Banco no seleccionado"),
                    body: _t("Por favor, seleccione un banco antes de aplicar."),
                });
                return;
            }

            if (!owner_name || !check_number || !bank_account) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t("No se han ingresado los datos del cheque o la transferencia. Por favor, ingresa todos los datos del formulario, para poder continuar."),
                });
                return;
            }

            try {
                let list_banks = response_obj.map(item => item.id_bank);
                if (list_banks.includes(parseInt(select_options))) {
                    this.pos.isNumpadDisabled = true;
                }
            } catch (e) {

            }

            if (selected_paymentline) {
                // Usar -1 como valor por defecto cuando no hay institución válida
                const dataInstitution = (obj && obj.id_institutions) ? parseInt(obj.id_institutions, 10) : -1;
                selected_paymentline.set_owner_name(owner_name);
                selected_paymentline.set_check_number(check_number);
                selected_paymentline.set_bank_account(bank_account);
                selected_paymentline.set_bank_id(bank_id);
                selected_paymentline.set_institution_cheque(dataInstitution > 0 ? dataInstitution : -1);
                selected_paymentline.set_institution_id(data_order || null);
                selected_paymentline.enable_advanced_payments = this.state.enable_advanced_payments;
                const bancosPermitidos = ['DEUNA BCO PICHINCHA', 'AHORITA BANCO DE LOJA'];
                if (this.state.enable_advanced_payments && bancosPermitidos.includes(this.state.bank_name)) {
                    selected_paymentline.set_payment_transfer_number(this.state.check_number);
                    selected_paymentline.set_payment_transaction_id(this.state.transactionId);
                    selected_paymentline.set_payment_bank_name(this.state.bank_name);
                    selected_paymentline.set_orderer_identification(orderer_identification);
                    selected_paymentline.amount = parseFloat(this.state.payment_amount) || 0.0;
                }
            }
            this.syncToPaymentline();
            return super.confirm();
        } else if (this.state.payment_method.name === "TARJETA") {
            const number_voucher = document.getElementById("number_voucher")?.value;
            const type_card = document.getElementById("type_card")?.value;
            const number_lote = document.getElementById("number_lote")?.value;
            const holder_card = document.getElementById("holder_card")?.value;
            const bin_tc = document.getElementById("bin_tc")?.value;

            // Usar métodos de validación para obtener datos de institución
            const obj = this.getValidInstitutionData();
            const data_order = this.getValidInstitutionId();

            if (!number_voucher || !type_card || !number_lote || !holder_card || !bin_tc) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t("No se han ingresado los datos de la tarjeta. Por favor, ingresa todos los datos del formulario, para poder continuar."),
                });
                return;
            }

            if (selected_paymentline) {
                // Usar -1 como valor por defecto cuando no hay institución válida
                const dataInstitution = (obj && obj.id_institutions) ? parseInt(obj.id_institutions, 10) : -1;
                selected_paymentline.set_number_voucher(number_voucher);
                selected_paymentline.set_type_card(type_card);
                selected_paymentline.set_number_lote(number_lote);
                selected_paymentline.set_holder_card(holder_card);
                selected_paymentline.set_bin_tc(bin_tc);
                selected_paymentline.set_institution_card(dataInstitution > 0 ? dataInstitution : -1);
                selected_paymentline.set_institution_id(data_order || null);
            }
            this.syncToPaymentline();
            return super.confirm();
        } else if (
            this.state.payment_method.type === 'cash') {
            // Usar métodos de validación para obtener datos de institución
            const obj = this.getValidInstitutionData();
            const data_order = this.getValidInstitutionId();

            if (selected_paymentline) {
                // Usar -1 como valor por defecto cuando no hay institución válida
                const dataInstitution = (obj && obj.id_institutions) ? parseInt(obj.id_institutions, 10) : -1;
                selected_paymentline.set_institution_card(dataInstitution > 0 ? dataInstitution : -1);
                selected_paymentline.set_institution_id(data_order || null);
            }
            this.syncToPaymentline();
        }
        this.state.success_message = '';
        return super.confirm();
    }

    deletePaymentLine(cid) {
        const lines = this.pos.get_order().get_paymentlines();
        for (const line of lines) {
            this.pos.get_order().remove_paymentline(line);
        }
    }

    async cancel() {
        const order = await this.pos.get_order();
        const paymentLines = order.get_paymentlines();
        for (const paymentLine of paymentLines) {
            this.deletePaymentLine(paymentLine.cid);
        }
        this.props.close({confirmed: false, payload: null});
    }

    getPayload() {
        return {
            newArray: this.state,
        };
    }

    async onBankChange(ev) {
        // const selectedOption = ev.target.options[ev.target.selectedIndex];
        const bankId = parseInt(ev.target.value) || null;
        const selectedBank = this.pos.banks.find(b => b.id == bankId);
        if (selectedBank) {
            this.state.bank_name = selectedBank.name;
            this.state.bank_id = bankId;
            this.state.bank_codigo = selectedBank.codigo_banco;
        } else {
            this.state.bank_name = '';
            this.state.bank_id = '';
            this.state.bank_codigo = null;
        }

        const fieldsToReset = [
            'check_number', 'bank_account',
            'institution_cheque', 'institution_card',
            'qrCode', 'deeplink', 'phone_user',
            'transactionId', 'payment_status', 'success_message', 'success_type'
        ];
        for (const field of fieldsToReset) {
            this.state[field] = (field === 'qrCode' || field === 'deeplink') ? null : '';
        }

        const inputIds = [
            'check_number', 'bank_account',
            'orderer_identification', 'phone'
        ];
        inputIds.forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.value = '';
            }
        });

        const unlockIds = [
            'check_number', 'bank_account',
            'phone', 'bank_id'
        ];
        unlockIds.forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.removeAttribute('readonly');
                input.removeAttribute('disabled');
            }
        });

        await this.updateAdvancedPayments();
        this.syncToPaymentline();
    }

    normalizePhoneNumber(phone) {
        // if (!this.state.enable_advanced_payments || this.state.bank_codigo !== 'DEUNA BCO PICHINCHA') return null;
        const bancosPermitidos = ['DEUNA BCO PICHINCHA', 'AHORITA BANCO DE LOJA'];
        if (!this.state.enable_advanced_payments || !bancosPermitidos.includes(this.state.bank_name)) return;

        let cleaned = phone.replace(/\D/g, '');
        if (cleaned.startsWith('0')) {
            cleaned = cleaned.slice(1);
        }
        if (!cleaned.startsWith('593')) {
            cleaned = '593' + cleaned;
        }
        if (!cleaned.match(/^593\d{9}$/)) {
            throw new Error('Número de teléfono inválido. Debe tener 9 dígitos después del código 593.');
        }
        return cleaned;
    }

    async send_whatsapp_message(phone, deeplink, payment_amount) {
        // if (!this.state.enable_advanced_payments || this.state.bank_codigo !== 'DEUNA BCO PICHINCHA') return;
        const bancosPermitidos = ['DEUNA BCO PICHINCHA', 'AHORITA BANCO DE LOJA'];
        if (!this.state.enable_advanced_payments || !bancosPermitidos.includes(this.state.bank_name)) return;
        try {
            const normalizedPhone = this.normalizePhoneNumber(phone);

            if (!deeplink) {
                throw new Error("No hay un enlace de pago (deeplink) disponible.");
            }

            const response = await this.rpc('/send_whatsapp_message', {
                phone: normalizedPhone,
                deeplink: deeplink,
                amount: payment_amount
            });

            if (response.error) {
                throw new Error(response.error || "Error desconocido al enviar WhatsApp");
            }
            this.notificationService.add(_t("Mensaje de WhatsApp enviado con éxito"), {
                type: 'success',
                sticky: false,
            });
        } catch (error) {
            if (error.status_code === 500 || error.message?.includes('qr.imageSync')) {
                this.state.success_message = _t("⚠️ No fue posible enviar el mensaje por WhatsApp. Pida al cliente escanear el código QR para completar el pago digital.");
                this.state.success_type = 'warning';
            } else {
                this.state.success_message = _t("✅ Enlace de pago enviado correctamente por WhatsApp.");
                this.state.success_type = 'success';
            }

            throw error;
        }
    }

    async send_message_user() {
        if (!this.state.enable_advanced_payments || this.state.bank_name !== 'DEUNA BCO PICHINCHA') return;

        if (this.state.transactionId) {
            let normalizedPhonePreview = null;
            const inputPhone = document.getElementById("phone")?.value?.trim();
            if (inputPhone) {
                try {
                    normalizedPhonePreview = this.normalizePhoneNumber(inputPhone);
                } catch (_) {}
            }

            const montoCambiado = this.state.generated_amount !== this.state.payment_amount;
            const telefonoCambiado = this.state.generated_phone !== normalizedPhonePreview;

            if (!montoCambiado && !telefonoCambiado) {
                const confirmOverwrite = await this.popup.add(ConfirmPopup, {
                    title: _t("Confirmación requerida"),
                    body: _t(
                        "Ya existe un link de pago generado para esta transacción.\n" +
                        "Si continúas, se generará un nuevo link y el anterior quedará invalidado.\n\n" +
                        "¿Deseas continuar?"
                    ),
                    confirmText: _t("Sí, reemplazar"),
                    cancelText: _t("No, cancelar"),
                });

                if (!confirmOverwrite.confirmed) {
                    return;
                }
            }
        }

        try {
            let normalizedPhone = null;
            const phone = document.getElementById("phone")?.value?.trim();
            if (phone) {
                normalizedPhone = this.normalizePhoneNumber(phone);
            }

            const selected_paymentline = this.pos.get_order().selected_paymentline;
            if (!selected_paymentline || isNaN(this.state.payment_amount) || this.state.payment_amount <= 0) {
                throw new Error("El monto del pago no es válido.");
            }
            if (this.state.payment_amount > parseFloat(selected_paymentline.amount)) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t(`El monto ingresado (${this.state.payment_amount}) no puede ser mayor al monto original (${selected_paymentline.amount}).`),
                });
                return;
            }
            const paymentResponse = await this.rpc('/deuna/payment/request', {amount: this.state.payment_amount});
            this.state.qrCode = paymentResponse.qr || null;
            this.state.deeplink = paymentResponse.deeplink || null;
            this.state.transactionId = paymentResponse.transactionId || null;

            const order = this.pos.get_order();
            const order_id = this.pos.orders[0]?.sale_id;

            const get_method_order_chatbot = await this.env.services.orm.call(
                'sale.order',
                'get_order_detail_chatbot',
                [order_id]
            );

            const order_data = get_method_order_chatbot[0] || {};
            const x_channel = order_data.x_channel;
            const transaction_id = order_data.pay_deuna_id;

            try {
                const order_id = this.pos.get_order().name;
                const response = await this.rpc('/deuna/create_record', {
                    order_id: order_id,
                    transactionId: this.state.transactionId,
                });
                if (response.error) {
                    console.error("❌ Error creando registro DEUNA:", response.message);
                }
            } catch (error) {
                console.error("❌ Error inesperado creando registro DEUNA:", error);
            }


            if (x_channel === "canal digital" && transaction_id) {
                this.state.transactionId = transaction_id;
                this.state.deeplink = "Pago previamente generado";

                this.notificationService.add(_t("Pago validado para canal digital"), {
                    type: 'success',
                    sticky: false,
                });
                return;
            }

            if (transaction_id) {
                this.state.transactionId = transaction_id;
            }

            if (!this.state.deeplink || !this.state.transactionId) {
                throw new Error("Existe un error con el pago. Contacte a soporte.");
            }

            this.state.success_message = _t("✅ Solicitud de pago generada correctamente.");
            this.state.success_type = 'success';

            this.notificationService.add(_t("Solicitud de pago completada"), {
                type: 'success',
                sticky: false,
            });

            this.state.generated_amount = this.state.payment_amount;
            this.state.generated_phone = normalizedPhone;
        } catch (error) {
            if (error?.status_code === 500 || error.message?.includes('qr.imageSync')) {
                return;
            }

            // Otros errores sí muestran popup
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Error al procesar la solicitud: ") + (error.message || "Contacte al soporte."),
            });

            this.state.success_message = '';
            this.state.success_type = '';
        } finally {
            this.syncToPaymentline();
        }
    }

    async send_message_user_ahorita() {
        if (!this.state.enable_advanced_payments || this.state.bank_name !== 'AHORITA BANCO DE LOJA') {
            console.warn("No se cumple con las condiciones para enviar mensaje");
            return;
        }

        if (this.state.transactionId) {
            let normalizedPhonePreview = null;
            const inputPhone = document.getElementById("phone")?.value?.trim();
            if (inputPhone) {
                try {
                    normalizedPhonePreview = this.normalizePhoneNumber(inputPhone);
                } catch (_) {}
            }

            const montoCambiado = this.state.generated_amount !== this.state.payment_amount;
            const telefonoCambiado = this.state.generated_phone !== normalizedPhonePreview;

            if (!montoCambiado && !telefonoCambiado) {
                const confirmOverwrite = await this.popup.add(ConfirmPopup, {
                    title: _t("Confirmación requerida"),
                    body: _t(
                        "Ya existe un link de pago generado para esta transacción.\n" +
                        "Si generas uno nuevo, el anterior dejará de ser válido.\n\n" +
                        "¿Deseas continuar?"
                    ),
                    confirmText: _t("Sí, reemplazar"),
                    cancelText: _t("No, cancelar"),
                });

                if (!confirmOverwrite.confirmed) {
                    return;
                }
            }
        }

        try {
            this.state.loading = true;

            const phoneInput = document.getElementById("phone");
            if (!phoneInput) {
                throw new Error("Campo de teléfono no encontrado en el formulario");
            }

            const phone = phoneInput.value?.trim();

            if (!phone || phone.length < 10) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t("Por favor, ingrese un número de teléfono válido (mínimo 10 dígitos)."),
                });
                return;
            }

            const normalizedPhone = this.normalizePhoneNumber(phone);
            if (!normalizedPhone) {
                throw new Error("El número de teléfono no pudo ser normalizado");
            }

            const order = this.pos.get_order();
            const order_id = order.name;
            const userId = 415472;
            const selected_paymentline = order.selected_paymentline;

            if (!selected_paymentline || isNaN(this.state.payment_amount) || this.state.payment_amount <= 0) {
                throw new Error("El monto del pago no es válido.");
            }

            if (this.state.payment_amount < 0.10) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t(`El monto ingresado (${this.state.payment_amount}) para pagos con Ahorita no puede ser menor o igual a 0.09 ctvs.`),
                });
                return;
            } else if (this.state.payment_amount > parseFloat(selected_paymentline.amount)) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Error"),
                    body: _t(`El monto ingresado (${this.state.payment_amount}) no puede ser mayor al monto original (${selected_paymentline.amount}).`),
                });
                return;
            }

            const now = new Date();
            const timestamp = now.getTime();
            const pad = (num, size = 2) => String(num).padStart(size, '0');
            const transactionId = `AHORITA-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
            const messageId = `PK Factura ${timestamp}`;

            const deeplink_response = await this.rpc('/ahorita/generate_deeplink', {
                userId: userId,
                messageId: messageId,
                transactionId: transactionId,
                deviceId: '127.0.0.1',
                amount: this.state.payment_amount,
            });

            if (!deeplink_response || deeplink_response.error) {
                throw new Error(deeplink_response?.error || "No se recibió respuesta del servidor");
            }

            this.state.qrCode = deeplink_response.qr || null;

            const deeplink_url = deeplink_response.deeplink?.deeplink;
            const deeplink_id = deeplink_response.deeplink?.deeplink_id;

            if (!deeplink_url) {
                throw new Error("El servidor no devolvió un enlace de pago válido");
            }


            const get_method_order_chatbot = await this.env.services.orm.call(
                'sale.order',
                'get_order_detail_chatbot_name',
                [order_id]
            );

            const order_data = get_method_order_chatbot[0] || {};
            const x_channel = order_data.x_channel;
            const transaction_id = order_data.pay_ahorita_id;


            // Guardar registro en backend
            try {
                const response = await this.rpc('/ahorita/create_record', {
                    order_id: order_id,
                    transactionId: transactionId,
                    deeplink_id: deeplink_id,
                });

            } catch (error) {
                console.error("Error al crear el registro en backend:", error);
            }

            if (x_channel === "canal digital" && transaction_id) {
                this.state.transactionId = transaction_id;
                this.state.deeplink = "Pago previamente generado";

                this.notificationService.add(_t("Pago validado para canal digital"), {
                    type: 'success',
                    sticky: false,
                });
                return;
            }

            Object.assign(this.state, {
                transactionId: transactionId,
                deeplink: deeplink_url,
                deeplink_id: deeplink_id,
            });

            await this.send_whatsapp_message(normalizedPhone, this.state.deeplink, this.state.payment_amount);
            this.state.success_message = _t("✅ Enlace de pago enviado correctamente por WhatsApp.");
            this.state.success_type = 'success';

            this.state.generated_amount = this.state.payment_amount;
            this.state.generated_phone = normalizedPhone;

        } catch (error) {
            if (error?.status_code === 500 || error.message?.includes('qr.imageSync')) {
                return;
            }

            // Otros errores sí muestran popup
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Error al procesar la solicitud: ") + (error.message || "Contacte al soporte."),
            });

            this.state.success_message = '';
            this.state.success_type = '';

        } finally {
            this.state.loading = false;
            this.syncToPaymentline();
        }
    }


    async checkPaymentStatus() {
        if (!this.state.enable_advanced_payments || this.state.bank_name !== 'DEUNA BCO PICHINCHA') return;
        try {
            const transactionId = this.state.transactionId;
            if (!transactionId) {
                throw new Error("No se ha generado aún un transactionId para consultar.");
            }
            const result = await this.rpc('/deuna/payment/status', {
                transaction_id: transactionId
            });
            this.state.payment_status = result.status;
            const resultPopup = await this.popup.add(PaymentStatusPopup, {
                status: result.status === "APPROVED" ? "APROBADO" : "PENDIENTE",
                statusColor: result.status === "APPROVED" ? "green" : "orange",
                transactionId: result.transactionId || "-",
                internalReference: result.internalTransactionReference || "-",
                ordererName: result.ordererName || "-",
                ordererIdentification: result.ordererIdentification || "-",
                transferNumber: result.transferNumber || "-",
                date: result.date || "-",
                amount: result.amount || "-",
                currency: result.currency || "",
                description: result.description || "",
            });
            if (result.status === "APPROVED" && resultPopup.confirmed) {
                const transfer = result.transferNumber || '';
                const orderer_identification = result.ordererIdentification || '';
                this.state.bank_account = transfer;
                this.state.check_number = transfer;
                this.state.orderer_identification = orderer_identification;
                this.state.isFieldsReadonly = true;
                const bankInput = document.getElementById("bank_account");
                const checkInput = document.getElementById("check_number");
                const ordererInput = document.getElementById("orderer_identification");
                const bankSelect = document.getElementById("bank_id");
                const ownerInput = document.getElementById("owner_name");
                const dateInput = document.getElementById("date");
                const phoneInput = document.getElementById("phone");
                if (bankInput) {
                    bankInput.value = transfer;
                    bankInput.setAttribute("readonly", true);
                }
                if (checkInput) {
                    checkInput.value = transfer;
                    checkInput.setAttribute("readonly", true);
                }
                if (ordererInput) {
                    ordererInput.value = orderer_identification;
                    ordererInput.setAttribute("readonly", true);
                }
                if (bankSelect) {
                    bankSelect.setAttribute("disabled", true);
                }
                if (ownerInput) {
                    ownerInput.setAttribute("readonly", true);
                }
                if (dateInput) {
                    dateInput.setAttribute("readonly", true);
                }
                if (phoneInput) {
                    phoneInput.setAttribute("readonly", true);
                }
            }
        } catch (error) {
            console.error("Error consultando el estado del pago:", error);
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("No se pudo consultar el estado del pago: ") + (error.message || "Error desconocido"),
            });
        } finally {
            this.syncToPaymentline();
        }
    }

    async checkPaymentStatusAhorita() {
        if (!this.state.enable_advanced_payments || this.state.bank_name !== 'AHORITA BANCO DE LOJA') return;

        try {
            const transactionId = this.state.transactionId;
            const deeplink_id = this.state.transactionId;
            const deeplink_idPos = this.state.deeplink_id;

            if (!transactionId) {
                throw new Error("No se ha generado un transactionId para consultar.");
            }

            let deeplink = deeplink_idPos || deeplink_id

            const result = await this.rpc('/ahorita/payment/status', {
                deeplink_id: deeplink,
                transaction_id: transactionId
            });


            this.state.payment_status = result.status === "payment_confirmed" ? "APROBADO" : "PENDIENTE";

            const resultPopup = await this.popup.add(PaymentStatusAhoritaPopup, {
                status: this.state.payment_status,
                statusColor: result.status === "payment_confirmed" ? "green" : "orange",
                transactionId: result.transactionId || "-",
                internalReference: result.metadata?.paymentReference || "-",
                ordererName: result.sender?.name || "-",
                ordererIdentification: result.sender?.clientId || "-",
                transferNumber: result.metadata?.bankReference || "-",
                date: result.transactionDate || "-",
                amount: result.amount || "-",
                currency: result.currency || "USD",
                description: result.metadata?.paymentPurpose || "Pago electrónico"
            });


            if (result.status === "payment_confirmed" && resultPopup.confirmed) {
                const transfer = result.metadata?.bankReference || '';
                const orderer_identification = result.sender?.clientId || '';

                this.state.bank_account = transfer;
                this.state.check_number = transfer;
                this.state.orderer_identification = orderer_identification;
                this.state.isFieldsReadonly = true;

                // Bloquear campos relevantes
                const fieldsToLock = [
                    "bank_account", "check_number", "orderer_identification",
                    "bank_id", "owner_name", "date", "phone", "payment_amount"
                ];

                fieldsToLock.forEach(fieldId => {
                    const element = document.getElementById(fieldId);
                    if (element) {
                        if (fieldId === "bank_account") element.value = transfer;
                        if (fieldId === "check_number") element.value = transfer;
                        if (fieldId === "orderer_identification") element.value = orderer_identification;
                        element.setAttribute("readonly", true);
                    }
                });

                const bankSelect = document.getElementById("bank_id");
                if (bankSelect) bankSelect.setAttribute("disabled", true);
            }
        } catch (error) {
            console.error("Error consultando el estado del pago Ahorita:", error);
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("No se pudo consultar el estado del pago: ") + (error.message || "Error desconocido"),
            });
        } finally {
            this.syncToPaymentline();
        }
    }

    async copyDeeplink() {
        if (!this.state.deeplink) {
            this.notificationService.add(_t("No hay un enlace de pago para copiar."), {
                type: 'danger',
                sticky: false,
            });
            return;
        }
        try {
            await navigator.clipboard.writeText(this.state.deeplink);
            this.notificationService.add(_t("Enlace de pago copiado al portapapeles."), {
                type: 'success',
                sticky: false,
            });
        } catch (error) {
            console.error('Error al copiar el deeplink:', error);
            this.notificationService.add(_t("No se pudo copiar el enlace. Por favor, cópielo manualmente."), {
                type: 'danger',
                sticky: false,
            });
        }
    }


}