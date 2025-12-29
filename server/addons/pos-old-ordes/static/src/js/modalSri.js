/** @odoo-module **/
import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";

export class PopupSriSearch extends AbstractAwaitablePopup {
    static template = "pos-old-ordes.PopupSri";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.product = this.props.product;
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            selectedDate: '',
            claveAccesoComprobante: '',
            selectedPaymentMethodId: null,
            paymentMethods: [],
            responseMessage: '',
            invoices: [],
            client_name: '',
            client_id: '',
            loading: false,
            message_status: "",
            statusCreateOrder: false
        });

        this.mounted()
    }

    async mounted() {
        try {
            const userId = this.env.services.user.userId;
            const paymentMethods = await this.orm.call(
                'pos.session',
                'get_payment_methods_by_user_pos',
                [userId]
            );
            this.state.paymentMethods = paymentMethods;
            this.state.selectedPaymentMethodId = paymentMethods[0]?.id || null;
        } catch (error) {
            this.popup.add(ErrorPopup, {
                title: _t("Error al cargar métodos de pago"),
                body: error.message || _t("No se pudieron obtener los métodos de pago."),
            });
        }

    }


    async btnSriSearchInput() {
        try {
            this.state.loading = true;  // 🔥 Mostrar loading
            const invoiceNumber = document.getElementById("claveAccesoComprobante").value;
            const resultClient = await this.orm.call(
                'pos.session',
                'search_cliente_id_old',
                [invoiceNumber]
            );
            const invoices = await this.SearchInvoicesApi(resultClient.id_database_old);
            if (Array.isArray(invoices) && invoices.length > 0) {
                this.state.invoices = invoices;
                this.state.client_name = resultClient.name
                this.state.client_id = resultClient.id
            } else {
                this.state.invoices = []
            }
        } catch (e) {
            console.log(e)
        } finally {
            this.state.loading = false;
        }

    }

    onSelectInvoiceTable(item) {
        this.searchSessionPosExist(item)
    }

    async SearchInvoicesApi(identification) {
        try {
            const response = await fetch('/proxy_invoices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({identification: identification}),
            });

            if (!response.ok) {
                throw new Error(`Error en la API: ${response.status} ${response.statusText}`);
            }

            const response_api = await response.json();
            const data = response_api.filter(invoice => invoice.idbodega === this.pos.config.point_of_sale_id);
            console.log('Facturas filtradas por bodega:', data);
            return data;

        } catch (error) {
            console.error('Error consultando la API:', error);
            return null;
        }
    }

    async searchSessionPosExist(item) {
        const get_cashier = this.env.services.user.userId;
        const listProduct = [];
        let totalAmount = 0;
        const IVA_15_ID = 1;  // <-- ajústalo al ID correcto que viste en Contabilidad


        // Recorremos cada detalle de factura
        for (const product of item.invoicedet) {
            const quantity = product.QUANTITY || 1;
            // ✨ Usamos el total que ya nos dio la API
            const lineTotal = parseFloat(product.total) || 0;
            totalAmount += lineTotal;

            // Buscamos dinámicamente el product_id
            const foundProduct = await this.orm.call(
                'product.product',
                'get_product_by_id_database_old',
                [product.IDITEM]
            );
            const productId = foundProduct
                ? foundProduct.product_id
                : 241215;  // fallback si no lo encuentra

            const taxIds = product.LIVA === 1 ? [IVA_15_ID] : [];
            listProduct.push({
                product_id: productId,
                qty: quantity,
                price_unit: product.PRICE,
                discount: product.PDESCUNIT,
                tax_ids_after_fiscal_position: [[6, 0, taxIds]],
                tax_ids: [[6, 0, taxIds]],
            });
        }
        totalAmount = parseFloat(totalAmount.toFixed(2));

        const payload = {
            user_id: get_cashier,
            selected_date: item.date,
            partner_id: this.state.client_id,
            amount_total: totalAmount,
            amount_paid: totalAmount,
            amount_tax: 0.0,
            payment_method_id: this.state.selectedPaymentMethodId,
            lines: listProduct,
            payment_method: item.FORMAPAGO,
            key_order: item.AUTORIZACION,
            date: item.date
        };

        console.log(payload)
        try {
            const result = await this.orm.call(
                'pos.session',
                'check_session_by_user_and_date_and_create_order',
                [payload]
            );
            console.log("Orden creada en la sesión:", result);
            this.state.statusCreateOrder = true
            this.state.message_status = "La orden ha sido ingresada correctamente. Por favor, cierre este modal y búsquela en el listado por la fecha."
            // Ocultarlo tras 5 segundos
            setTimeout(() => {
                this.state.statusCreateOrder = false;
                this.state.message_status = "";
            }, 4000);
        } catch (error) {
            await this.popup.add(ErrorPopup, {
                title: _t("Error al crear la orden"),
                body: "Notifique el error.",
            });
        }
    }


    confirm() {
        console.log("Confirmado");
        // Aquí puedes implementar la lógica que necesites con el producto
    }

    cancel() {
        this.props.close({confirmed: false, payload: null});
    }
}
