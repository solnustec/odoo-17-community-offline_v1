/** @odoo-module **/
/* global Stripe */

import { _t } from '@web/core/l10n/translation';
import { paymentExpressCheckoutForm } from '@payment/js/express_checkout_form';

paymentExpressCheckoutForm.include({
    init() {
        this._super(...arguments);
        this.rpc = this.bindService("rpc");
    },

    /**
     * Update the amount of the express checkout form.
     *
     * @override method from payment.express_form
     * @private
     * @param {number} newAmount - The new amount.
     * @param {number} newMinorAmount - The new minor amount.
     * @return {void}
     */
    _updateAmount(newAmount, newMinorAmount) {
        this.paymentContext['amount'] = newAmount.toFixed(2)
        localStorage.setItem('dataPayment', JSON.stringify(this.paymentContext))
        this._super(...arguments);
    },

  // #=== WIDGET LIFECYCLE ===#


  /**
   * @override
   */
  start: async function () {

      await this._super(...arguments);
      document.querySelector('[name="o_payment_submit_button"]')?.removeAttribute('disabled');
      localStorage.setItem('dataPayment', JSON.stringify(this.paymentContext))
  },
});