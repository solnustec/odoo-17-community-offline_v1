/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { jsonrpc, RPCError } from "@web/core/network/rpc_service";

export default {

    /**
     * Simulate a feedback from a payment provider and redirect the customer to the status page.
     *
     * @private
     * @param {object} processingValues - The processing values of the transaction.
     * @param {string} custom 
     * @return {void}
     */
    async processDemoPayment(processingValues, custom, data) {
        
        const simulatedPaymentState = "done"
        jsonrpc('/payment/paymentez/simulate_payment', {
            'reference': processingValues.reference,
            'payment_details': custom,
            'simulated_state': simulatedPaymentState,
            'data': data,
        }).then(() => {
            window.location = '/payment/status';
        }).catch(error => {
            if (error instanceof RPCError) {
                this._displayErrorDialog(_t("Payment processing failed"), error.data.message);
                this._enableButton?.(); // This method doesn't exists in Express Checkout form.
            } else {
                return Promise.reject(error);
            }
        });
    },

};
