/** @odoo-module **/
/**
     * This file is used to register the a popup for viewing reference number of  transferred stock
*/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useRef, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * This class represents a custom popup for capturing signatures in the Point of Sale.
 * It extends the AbstractAwaitablePopup class.
 */
export class TransferRefPopup extends AbstractAwaitablePopup {
    static template = "TransferRefPopup";
    static defaultProps = {
        confirmText: _t("Save"),
        cancelText: _t("Discard"),
        clearText: _t("Clear"),
        title: "",
        body: "",
    };
    setup() {
        super.setup();
        this.notification = useService("pos_notification");

        // Llamar printReceipt automáticamente después de que el componente esté montado
        onMounted(() => {
            // Usar setTimeout para asegurar que la acción del usuario (crear transferencia)
            // haya completado, permitiendo que window.open funcione correctamente
            setTimeout(() => this.printReceipt(), 100);
        });
    }

    async printReceipt() {
        const recordId = this.props.data.id;

        try {
            // Obtener el action para extraer el nombre del reporte
            const action = await this.env.services.orm.call(
                'stock.picking',
                'action_print_receipt',
                [[recordId]]
            );

            // Construir URL del PDF y abrir con impresión
            const reportName = action.report_name;
            const pdfUrl = `/report/pdf/${reportName}/${recordId}`;

            const printWindow = window.open(pdfUrl, '_blank');

            // Verificar si la ventana se abrió correctamente
            if (printWindow) {
                printWindow.onload = () => {
                    printWindow.focus();
                    printWindow.print();
                };
            } else {
                // El navegador bloqueó el popup, mostrar notificación
                this.notification.add({
                    title: "Aviso",
                    body: "El navegador bloqueó la ventana de impresión. Por favor, permite las ventanas emergentes para este sitio.",
                });
                // Intentar descargar el PDF como alternativa
                const link = document.createElement('a');
                link.href = pdfUrl;
                link.target = '_blank';
                link.download = `transferencia_${this.props.data.name || recordId}.pdf`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        } catch (error) {
            console.error("Error al imprimir recibo:", error);
            this.notification.add({
                title: "Error",
                body: "No se pudo generar el recibo de la transferencia.",
            });
        }
    }
}
