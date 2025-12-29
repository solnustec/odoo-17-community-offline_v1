/** @odoo-module **/

import {Component, useState, onWillStart} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class GoogleSheetModal extends Component {
    static template = "sales_report.GoogleSheetModal";
    // static props = {
    //     // productId: String,
    //     // product_sales: String,
    //     // stock: String,
    //     // location: String,
    //     // observation: String,
    //     google_url: String,
    //     isOpen: {type: Boolean, optional: true},
    //     onClose: {type: Function, optional: true},
    // };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            isOpenGoogleModal: this.props.isOpenGoogleModal || false,
            product_name: this.props.reportData.product_name || '',
            product_sales: this.props.reportData.product_sales || 0,
            stock: this.props.reportData.stock || 0,
            location: 'Colocar ',
            google_url: this.props.google_url || '',
            uom_po_id: this.props.reportData.uom_po_id || 'Unidad x 1',
            observation: '',
            sending: false,
        });
    }


    closeModal() {
        this.state.isOpen = false;
        if (this.props.onClose) {
            this.props.onClose();
        }
    }

    onClickOutside(ev) {
        if (ev.target.id === 'modal') {
            this.closeModal();
        }
    }

    showError(message) {
        this.notification.add(message, {type: 'danger'});
    }

    showSucess(message) {
        this.notification.add(message, {type: 'success'})
    }

    sendToGoogleSheet = async () => {

        const payload = {
            nombre: this.state.product_name,
            cantidad: this.state.product_sales,
            stock: this.state.stock,
            colocar: this.state.location,
            descripcion: this.state.observation,
        };
        if (!this.state.google_url) {
            this.showError('Google Spreadsheet URL is not configured.');
            return;
        }
        try {
            this.state.sending = true
            await fetch(this.state.google_url, {
                method: 'POST',
                mode: 'no-cors',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
                redirect: "follow"
            });
            this.state.sending = false
            this.closeModal();
            this.showSucess('Datos guardados en Google Sheet!');
        } catch (error) {
            this.closeModal();
            this.showError('An error occurred. Please try again.', error);
        }
    }
}

