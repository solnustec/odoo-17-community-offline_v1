/** @odoo-module **/

import paymentForm from '@payment/js/payment_form';
import paymentDemoMixin from '@payment_paymentez/js/payment_demo_mixin';
import { jsonrpc, RPCError } from "@web/core/network/rpc_service";
import { _t } from "@web/core/l10n/translation";

paymentForm.include({

    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of Demo for direct payment.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {

        if (providerCode !== 'paymentez') {
            this._super(...arguments);
            return;
        } else if (flow === 'token') {
            return;
        }

        this._setPaymentFlow('direct');

        // Extract and deserialize the inline form values.
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        const stripeInlineForm = inlineForm.querySelector('[name="o_paymentez_element_container"]');
        this.paymentezInlineFormValues = JSON.parse(
            stripeInlineForm.dataset['paymentezInlineFormValues']
        );

        const dataPayment = JSON.parse(localStorage.getItem('dataPayment'))
        const transactionRoute = this.paymentContext['transactionRoute']

        const prepareTransaction = this._prepareTransactionRouteParams(this.paymentezInlineFormValues.provider.id)
        prepareTransaction.provider_id = this.paymentezInlineFormValues.provider.id
        prepareTransaction.tokenization_requested = false
        prepareTransaction.payment_method_id = parseInt(dataPayment.paymentMethodUnknownId)

        let mode = "stg";
        
        if(this.paymentezInlineFormValues.provider.state == "enabled"){
          mode = "prod"
        }

        let paymentCheckout = new PaymentCheckout.modal({
            env_mode: mode, // `prod`, `stg`, `local` to change environment. Default is `stg`
            onOpen: function () {
              console.log("modal open");
            },
            onClose: function () {
              console.log("modal closed");
            },
            onResponse: async (response) => { 
              const processingValues = await jsonrpc(
                transactionRoute,
                prepareTransaction,
              );
              const status_detail = response.transaction.status_detail
              const bin = response.card.bin

              if (status_detail == 3) {
                paymentDemoMixin.processDemoPayment(processingValues, bin, response);
              } else if (status_detail == 9) {
                this._displayErrorDialog(
                  _t("Payment processing failed"),
                  _t("Transacción denegada")
                );
              } else if (status_detail == 11) {
                this._displayErrorDialog(
                  _t("Payment processing failed"),
                  _t("Transacción rechazada por sistema de fraude")
                );
              } else if (status_detail == 12) {
                this._displayErrorDialog(
                  _t("Payment processing failed"),
                  _t("Tarjeta en lista negra")
                );
              } else {
                this._displayErrorDialog(
                  _t("Payment processing failed"),
                  _t("Inténtalo de nuevo más tarde")
                );
              }
              
            }
        });

        const checkbox = document.getElementById('website_sale_tc_checkbox');
        let btnOpenCheckout = document.querySelector('button[name="o_payment_submit_button"]');

        if(checkbox){
                  
              function checkCheckboxStatus() {
                if (checkbox.checked) {
                    document.querySelector('[name="o_payment_submit_button"]')?.removeAttribute('disabled');
                } else {
                    document.querySelector('[name="o_payment_submit_button"]')?.setAttribute('disabled', 'disabled');
                }
            }
        
            checkCheckboxStatus();
          
            checkbox.addEventListener('change', checkCheckboxStatus);
          
        }

        // Remover event listeners existentes
        const clone = btnOpenCheckout.cloneNode(true);
        btnOpenCheckout.parentNode.replaceChild(clone, btnOpenCheckout);
        btnOpenCheckout = clone;

        btnOpenCheckout.addEventListener('click', async (ev) => {
          ev.preventDefault();

          // === Nuevo bloque: actualizar minor_amount desde el servidor ===
          try {
            const data = await jsonrpc('/shop/paymentez/inline_values', {});
            if (data?.error) throw new Error(data.error);

            const isInt = Number.isInteger(data?.minor_amount);
            if (isInt) {
              if (data.minor_amount !== this.paymentezInlineFormValues.minor_amount) {
                this.paymentezInlineFormValues.minor_amount = data.minor_amount;
              }
            } else {
              console.warn('Respuesta sin minor_amount entero:', data);
            }
          } catch (err) {
            console.warn('No se pudo obtener inline_values:', err);
          }
          //=================================================================

          const reference = await this.generatePayment(this.paymentezInlineFormValues);

          if (reference) {
            paymentCheckout.open({
              reference: reference 
            });
          } else {
            
            console.error('Failed to fetch reference');
          }
        });
      
          window.addEventListener('popstate', function () {
              paymentCheckout.close();
          });

    },

      /**
     * Confirm the intent on Stripe's side and handle any next action.
     *
     * @private
     * @param {object} paymentezInlineFormValues
     * @return {string} The processing error, if any.
     */
    async generatePayment(paymentezInlineFormValues){
      
      let application_code = paymentezInlineFormValues.provider.application_code
      let application_key = paymentezInlineFormValues.provider.application_key
      let mode = "stg"

      if(paymentezInlineFormValues.provider.state == "enabled"){
        mode = "prod"
      }

      const minorAmount = paymentezInlineFormValues.minor_amount;
      const dividedAmount = minorAmount / 100;
      const formattedAmount = dividedAmount.toFixed(2);

      const amount = parseFloat(formattedAmount);
      const partner_id = this.paymentContext['partnerId']
      const country = paymentezInlineFormValues.billing_details.address.country;
      const name = paymentezInlineFormValues.billing_details.name;
      const email = paymentezInlineFormValues.billing_details.email;
      const street = paymentezInlineFormValues.billing_details.address.line1;
      const street2 = paymentezInlineFormValues.billing_details.address.line2;
      const zip = paymentezInlineFormValues.billing_details.address.postal_code;
      const city = paymentezInlineFormValues.billing_details.address.city;

      const reference = await this.fetchReference(
        application_code, 
        application_key,
        mode,
        amount,
        partner_id,
        country,
        name,
        email,
        street,
        street2,
        zip,
        city
      );

      return reference
    },

     /**
     * Confirm the intent on Stripe's side and handle any next action.
     *
     * @private
     * @param {string} application_code- The processing values of the transaction.
     * @param {string} application_key - The id of the payment option handling the transaction.
     * @param {string} mode
     * @param {number} partner_id
     * @param {string} country
     * @param {string} name
     * @param {string} email
     * @return {string}
     */
     async fetchReference(
      application_code, 
      application_key,
      mode,
      amount,
      partner_id, 
      country, 
      name, 
      email,
      street,
      street2,
      zip,
      city
    ) {
        try {
          const url = mode === "prod" 
            ? 'https://ccapi.paymentez.com/v2/transaction/init_reference/'
            : 'https://ccapi-stg.paymentez.com/v2/transaction/init_reference/';

          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Auth-Token': await this.generateAuthToken(application_code, application_key) // Use the function to generate token
            },
            body: JSON.stringify({
                locale: country,
                order: {
                    amount: amount,
                    description: name,
                    vat: 0,
                    dev_reference: name,
                    installments_type: 0,
                    taxable_amount: 0.00,
                    tax_percentage: 0,
                },
                user: {
                    id: partner_id,
                    email: email
                },
                conf: {
                    theme: {
                        primary_color: "#00BF84",
                        secondary_color: "#545454"
                    }
                },
                billing_address: {
                    street: street,
                    city: city,
                    country: country,
                    zip: zip,
                    additional_address_info: street2
                }
            })
          });

          if (response.status === 401) {
            // Handle 401 Unauthorized error
            this._displayErrorDialog(
              _t("No autorizado: comuníquese con el soporte."),
            );
            return null;
          }
    
          const data = await response.json();
          return data.reference;
        } catch (error) {
          this._displayErrorDialog(
            _t("Payment processing failed"),
            error
          );
          return null;
        }
      },


    /**
     * Confirm the intent on Stripe's side and handle any next action.
     *
     * @private
     * @param {string} application_code- The processing values of the transaction.
     * @param {string} application_key - The id of the payment option handling the transaction.
     * @return {string} The processing error, if any.
     */
    async generateAuthToken(application_code, application_key) {
      const serverApplicationCode = application_code;
      const serverAppKey = application_key;
  
      // Obter o timestamp atual
      const unixTimestamp = Math.floor(Date.now() / 1000);
  
      // Criar a string única
      const uniqTokenString = serverAppKey + unixTimestamp;
  
      // Gerar o hash SHA-256
      const crypto = window.crypto || window.msCrypto;
      const encoder = new TextEncoder();
      const data = encoder.encode(uniqTokenString);
  
      const hashBuffer = await crypto.subtle.digest('SHA-256', data);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const uniqTokenHash = hashArray.map(byte => byte.toString(16).padStart(2, '0')).join('');
  
      // Gerar o token de autenticação base64
      const authToken = btoa(`${serverApplicationCode};${unixTimestamp};${uniqTokenHash}`);
  
      return authToken;
  },


});
