/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { registry } from "@web/core/registry";
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Componente personalizado de recibo
export class CustomOrderReceipt extends OrderReceipt {
    setup() {
        super.setup();
        this.state = useState({
            custom_message: "¡Gracias por su compra!",
            custom_info: "Información adicional aquí"
        });
    }

    get receiptData() {
        let data = super.receiptData;
        console.log("Datos del recibo:", data);

        return {
            ...data,
            custom_message: this.state.custom_message,
            custom_info: this.state.custom_info
        };
    }
}

// Componente personalizado de pantalla de recibo
export class CustomReceiptScreen extends ReceiptScreen {
    setup() {
        super.setup();
        this.printer = useService("printer");
        this.customData = this.props.customData || {};
    }

    get receiptComponent() {
        return CustomOrderReceipt;  // Usa el recibo modificado
    }

    get receiptData() {
        return {
            ...this.customData,
            custom_message: "¡Gracias por su compra!",
            custom_info: "Información adicional aquí"
        };
    }
}


// Registrar componentes en el registry
registry.category("pos_screens").add("CustomReceiptScreen", CustomReceiptScreen);
registry.category("pos_receipt").add("CustomOrderReceipt", CustomOrderReceipt);
