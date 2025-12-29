/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {ReceiptScreen} from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import {OrderReceipt} from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import {useService} from "@web/core/utils/hooks";

OrderReceipt.props = {
    ...(OrderReceipt.props || {}),
    showCoupons: {type: Boolean, optional: true},
};

patch(ReceiptScreen.prototype, {

    setup() {
        super.setup(...arguments);
        // 🔹 Inyectar el servicio RPC
        this.rpc = useService("rpc");
    },

    async key_sri_load() {
        try {
            const order = this.pos.get_order();
            this.props.data.access_key_sri = await this.rpc("/key_access_sri", {
                key: order.access_token,
            });
            console.log("this.props.data.access_key_sri", this.props.data.access_key_sri);
        } catch (error) {
            console.error("Error al obtener clave SRI:", error);
        }
    },

    async printReceipt() {
        // 🔹 Cambiar icono del botón mientras imprime
        this.buttonPrintReceipt.el.className = "fa fa-fw fa-spin fa-circle-o-notch";

        try {
            const order = this.pos.get_order();

            // 🔹 Obtener clave SRI desde tu controlador HTTP
            const sri_key = await this.rpc("/key_access_sri", {key: order.access_token});

            // 🔹 Obtener número de factura desde tu controlador HTTP
            const invoice_name = await this.rpc("/get_invoice_number", {key: order.access_token});

            // 🔹 Exportar datos del pedido
            const originalExportedData = order.export_for_printing();

            // 🔹 Preparar datos para el recibo
            const printDataWithCoupons = {
                ...originalExportedData,
                access_key_sri: sri_key || "",
                invoice_name: invoice_name || "",
                isBill: this.isBill,
                print_coupons: true,
            };

            // 🔹 Imprimir
            const isPrinted = await this.printer.print(
                OrderReceipt,
                {
                    data: printDataWithCoupons,
                    showCoupons: true,
                    formatCurrency: this.env.utils.formatCurrency,
                },
                {webPrintFallback: true}
            );

            if (isPrinted) {
                this.currentOrder._printed = true;
            }
        } catch (error) {
            console.error("Error al imprimir el recibo:", error);
        } finally {
            // 🔹 Restaurar icono del botón
            if (this.buttonPrintReceipt.el) {
                this.buttonPrintReceipt.el.className = "fa fa-print";
            }
        }
    },
});
