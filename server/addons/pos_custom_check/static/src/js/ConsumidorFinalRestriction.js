/** @odoo-module */
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {patch} from "@web/core/utils/patch";

/**
 * Restringe que solo puedan existir dos métodos de pago;
 * cuando se seleccionen dos métodos de pago, por obligación
 * uno de ellos debe ser en efectivo
 **/
patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        // Obtener y verificar el cliente actual
        const currentPartner = this.currentOrder.get_partner();
        const isConsumerFinal = currentPartner && currentPartner.name.trim().toLowerCase() === "consumidor final";
        super.addNewPaymentLine(paymentMethod);
        setTimeout(() => {
            const paymentLinesObj = this.currentOrder.get_paymentlines();
            const idInstitution = localStorage.getItem("institutionId")
            if (paymentLinesObj[0].payment_method.type === "cash" && idInstitution) {
                const icono = document.querySelector(".pruebaaaa i");
                icono.addEventListener("click", function () {
                    console.log("El icono ha sido clickeado");
                });
                icono.click();
                setTimeout(() => {
                    const button_confirm = document.getElementById("confirmado")
                    button_confirm.addEventListener("click", function () {
                        console.log("confirmado");
                    });
                    button_confirm.click();
                }, 30)
            }
            if (isConsumerFinal) {
                const paymentLines = this.currentOrder.get_paymentlines();
                const totalAmount = Array.from(paymentLines)
                    .filter((line) => line.payment_method.name.toLowerCase().includes('efectivo') || line.payment_method.name.toLowerCase().includes('efect'))
                    .reduce((sum, line) => {
                        return sum + parseFloat(line.amount || 0);
                    }, 0);
                if (totalAmount > 1.00) {
                    const lastPaymentLine = paymentLines[paymentLines.length - 1];
                    // Utilizar deleteLine desde la lógica de la plantilla XML
                    if (this.deletePaymentLine) {
                        this.deletePaymentLine(lastPaymentLine.cid);
                    } else {
                        // Si deletePaymentLine no está disponible, eliminar manualmente
                        this.currentOrder.remove_paymentline(lastPaymentLine.cid);
                    }
                    this.popup.add(ErrorPopup, {
                        title: "Monto Máximo Excedido",
                        body: "Cuando el cliente es 'Consumidor Final', el monto máximo permitido en efectivo es 1.00.",
                    });
                }
            }
        }, 50); // Retraso de 50 ms para esperar la inicialización de `amount`
    },
});