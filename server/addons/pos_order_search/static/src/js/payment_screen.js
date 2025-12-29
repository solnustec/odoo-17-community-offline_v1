import { PaymentScreen } from "@point_of_sale/app/screens/payment/payment_screen";
import { ErrorPopup } from "@point_of_sale/app/popups/error_popup";

const CustomPaymentScreen = PaymentScreen.extend({
    async updatePaymentAsync() {
        const client = this.currentOrder.get_partner();

        if (!client) {
            await this.showPopup('ErrorPopup', {
                title: 'Cliente no seleccionado',
                body: 'Debes seleccionar un cliente antes de continuar con el pago.',
            });
            return; // Detiene el flujo de pago
        }

        // tu lógica normal...
        await this._super.apply(this, arguments);
    }
});

