/** @odoo-module */
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {patch} from "@web/core/utils/patch";
import {CustomMessageAlertPopup} from "@pos_custom_message/js/Popup/AlertPopup";
import {CustomMessageInfoPopup} from "@pos_custom_message/js/Popup/InfoPopup";
import {CustomMessageWarnPopup} from "@pos_custom_message/js/Popup/WarningPopup";
import {rpc} from "@web/core/network/rpc_service";
import {useService} from "@web/core/utils/hooks";

// Patching the ProductScreen to add a function that checks messages periodically
patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm"); // Servicio ORM para hacer consultas
        this.messageDisplayed = false; // Bandera para evitar múltiples ejecuciones
        this.checkMessages(); // Iniciar la verificación
    },

    checkMessages() {
        if (this.messageDisplayed) return; // Si ya se mostró un mensaje, no seguir ejecutando
        const self = this;
        setTimeout(() => {
            if (this.messageDisplayed) return; // Verificar nuevamente antes de ejecutar
            const messages = self.env.services.pos.pos_custom_message;
            if (messages) {
                messages.forEach((msg) => {
                    const ExecutionTime = msg.execution_time;
                    const date_now = new Date()
                    let fecha = new Date(ExecutionTime.replace(" ", "T") + "Z"); // Asegura formato ISO
                    fecha.setHours(fecha.getHours() - 5); // Ajusta la zona horaria
                    fecha.setMinutes(fecha.getMinutes() + 1); // Sumar un minuto

                    let nuevaFechaStr = fecha.toISOString().slice(0, 16).replace("T", " ");
                    if (this.getFormattedDateTime(date_now) === nuevaFechaStr) {
                        console.log("si es igual")
                        this.showPopupMessage(msg)
                        this.messageDisplayed = true;
                    } else {
                    }
                });
            }
            this.search_popup();
            self.checkMessages();
        }, 1000);
    },

    getFormattedDateTime() {
        const now = new Date()
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0'); // Meses en JS van de 0 a 11
        const day = String(now.getDate()).padStart(2, '0');

        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}`;
    },

    async search_popup() {
        const messages = await this.orm.searchRead(
            "pos.custom.message",
            [],
            ["id", "message_type", "title", "message_text", "execution_time"]
        );
    },


    showPopupMessage(msg) {
        if (msg.message_type === "alert") {
            this.popup.add(CustomMessageAlertPopup, {
                title: msg.title,
                body: msg.message_text,
            });
            return
        }
        if (msg.message_type === "warn") {
            this.popup.add(CustomMessageWarnPopup, {
                title: msg.title,
                body: msg.message_text,
            });
            return;
        }
        if (msg.message_type === "info") {
            this.popup.add(CustomMessageInfoPopup, {
                title: msg.title,
                body: msg.message_text,
            });
            return;
        }
    },
});
