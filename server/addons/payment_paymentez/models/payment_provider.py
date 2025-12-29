# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json

from odoo import _, api, fields, models

from odoo.addons.payment_paymentez import const, utils as paymentez_utils
from werkzeug.urls import url_encode, url_join, url_parse
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.addons.payment import utils as payment_utils


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('paymentez', 'Paymentez')], ondelete={'paymentez': 'set default'})
    paymentez_application_code = fields.Char(string="Paymentez Application Code", help="The key solely used to identify the account with Paymentez",
        required_if_provider='paymentez')
    paymentez_application_key = fields.Char(string="Paymentez Application Key", required_if_provider='paymentez', groups='base.group_system')

    #=== COMPUTE METHODS ===#

    @api.depends('code')
    def _compute_view_configuration_fields(self):
        """ Override of payment to hide the credentials page.

        :return: None
        """
        super()._compute_view_configuration_fields()
        self.filtered(lambda p: p.code == 'paymentez').show_credentials_page = True

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'paymentez').update({
            'support_express_checkout': True,
            'support_manual_capture': 'partial',
            'support_refund': 'partial',
            'support_tokenization': True,
        })

    # === CONSTRAINT METHODS ===#

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'paymentez':
            return default_codes
        return const.DEFAULT_PAYMENT_METHODS_CODES
    
    @api.model
    def _paymentez_get_id(self):
        """ Return the publishable key of the provider.

        This getter allows fetching the publishable key from a QWeb template and through Stripe's
        utils.

        Note: `self.ensure_one()

        :return: The publishable key.
        :rtype: str
        """
        self.ensure_one()

        return paymentez_utils.get_id(self.sudo())

    @api.model
    def _paymentez_get_application_code(self):
        """ Return the publishable key of the provider.

        This getter allows fetching the publishable key from a QWeb template and through Stripe's
        utils.

        Note: `self.ensure_one()

        :rtype: str
        """
        self.ensure_one()

        return paymentez_utils.get_application_code(self.sudo())
    
    @api.model
    def _paymentez_get_application_key(self):
        """ Return the publishable key of the provider.

        This getter allows fetching the publishable key from a QWeb template and through Stripe's
        utils.

        Note: `self.ensure_one()

        :rtype: str
        """
        self.ensure_one()

        return paymentez_utils.get_application_key(self.sudo())
    
    @api.model
    def _paymentez_get_state(self):
        """ Return the publishable key of the provider.

        This getter allows fetching the publishable key from a QWeb template and through Stripe's
        utils.

        Note: `self.ensure_one()

        :return: The publishable key.
        :rtype: str
        """
        self.ensure_one()

        return paymentez_utils.get_state(self.sudo())

    def action_paymentez_verify_apple_pay_domain(self):
        """ Verify the web domain with Stripe to enable Apple Pay.

        The domain is sent to Stripe API for them to verify that it is valid by making a request to
        the `/.well-known/apple-developer-merchantid-domain-association` route. If the domain is
        valid, it is registered to use with Apple Pay.
        See https://stripe.com/docs/stripe-js/elements/payment-request-button#verifying-your-domain-with-apple-pay.

        :return dict: A client action with a success message.
        :raise UserError: If test keys are used to make the request.
        """
        self.ensure_one()

        web_domain = url_parse(self.get_base_url()).netloc
        response_content = self._stripe_make_request('apple_pay/domains', payload={
            'domain_name': web_domain
        })
        if not response_content['livemode']:
            # If test keys are used to make the request, Stripe will respond with an HTTP 200 but
            # will not register the domain. Ask the user to use live credentials.
            raise UserError(_("Please use live credentials to enable Apple Pay."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _("Your web domain was successfully verified."),
                'type': 'success',
            },
        }
    
    def action_paymentez_connect_account(self, menu_id=None):
        """ Create a Stripe Connect account and redirect the user to the next onboarding step.

        If the provider is already enabled, close the current window. Otherwise, generate a Stripe
        Connect onboarding link and redirect the user to it. If provided, the menu id is included in
        the URL the user is redirected to when coming back on Odoo after the onboarding. If the link
        generation failed, redirect the user to the provider form.

        Note: This method serves as a hook for modules that would fully implement Stripe Connect.
        Note: self.ensure_one()

        :param int menu_id: The menu from which the user started the onboarding step, as an
                            `ir.ui.menu` id.
        :return: The next step action
        :rtype: dict
        """
        self.ensure_one()

        if self.env.company.country_id.code not in const.SUPPORTED_COUNTRIES:
            raise RedirectWarning(
                _(
                    "Paymentez Connect is not available in your country, please use another payment"
                    " provider."
                ),
                self.env.ref('payment.action_payment_provider').id,
                _("Other Payment Providers"),
            )

        if self.state == 'enabled':
            self.env['onboarding.onboarding.step'].action_validate_step_payment_provider()
            action = {'type': 'ir.actions.act_window_close'}
        else:
            # Account creation
            connected_account = self._stripe_fetch_or_create_connected_account()

            # Link generation
            if not menu_id:
                # Fall back on `account_payment`'s menu if it is installed. If not, the user is
                # redirected to the provider's form view but without any menu in the breadcrumb.
                menu = self.env.ref('account_payment.payment_provider_menu', False)
                menu_id = menu and menu.id  # Only set if `account_payment` is installed.

            account_link_url = self._stripe_create_account_link(connected_account['id'], menu_id)
            if account_link_url:
                action = {
                    'type': 'ir.actions.act_url',
                    'url': account_link_url,
                    'target': 'self',
                }
            else:
                action = {
                    'type': 'ir.actions.act_window',
                    'model': 'payment.provider',
                    'views': [[False, 'form']],
                    'res_id': self.id,
                }

        return action
    
    def _stripe_get_inline_form_values(
        self, amount, currency, partner_id, is_validation, payment_method_sudo=None, **kwargs
    ):
        """ Return a serialized JSON of the required values to render the inline form.

        Note: `self.ensure_one()`

        :param float amount: The amount in major units, to convert in minor units.
        :param res.currency currency: The currency of the transaction.
        :param int partner_id: The partner of the transaction, as a `res.partner` id.
        :param bool is_validation: Whether the operation is a validation.
        :param payment.method payment_method_sudo: The sudoed payment method record to which the
                                                   inline form belongs.
        :return: The JSON serial of the required values to render the inline form.
        :rtype: str
        """
        self.ensure_one()

        if not is_validation:
            currency_name = currency and currency.name.lower()
        else:
            currency_name = self.with_context(
                validation_pm=payment_method_sudo  # Will be converted to a kwarg in master.
            )._get_validation_currency().name.lower()
        partner = self.env['res.partner'].with_context(show_address=1).browse(partner_id).exists()
        id = self._paymentez_get_id()

        inline_form_values = {
            'currency_name': currency_name,
            'provider_id': id,
            'minor_amount': amount and payment_utils.to_minor_currency_units(amount, currency),
            'capture_method': 'manual' if self.capture_manually else 'automatic',
            'billing_details': {
                'name': partner.name or '',
                'email': partner.email or '',
                'phone': partner.phone or '',
                'address': {
                    'line1': partner.street or '',
                    'line2': partner.street2 or '',
                    'city': partner.city or '',
                    'state': partner.state_id.code or '',
                    'country': partner.country_id.code or '',
                    'postal_code': partner.zip or '',
                },
            },
            'is_tokenization_required': self._is_tokenization_required(**kwargs),
            'payment_methods_mapping': const.PAYMENT_METHODS_MAPPING,
        }
        return json.dumps(inline_form_values)


    def _paymentez_get_inline_form_values(
        self, amount, currency, partner_id, is_validation, payment_method_sudo=None, **kwargs
    ):
        """ Return a serialized JSON of the required values to render the inline form.

        Note: `self.ensure_one()`

        :param float amount: The amount in major units, to convert in minor units.
        :param res.currency currency: The currency of the transaction.
        :param int partner_id: The partner of the transaction, as a `res.partner` id.
        :param bool is_validation: Whether the operation is a validation.
        :param payment.method payment_method_sudo: The sudoed payment method record to which the
                                                   inline form belongs.
        :return: The JSON serial of the required values to render the inline form.
        :rtype: str
        """
        self.ensure_one()

        if not is_validation:
            currency_name = currency and currency.name.lower()
        else:
            currency_name = self.with_context(
                validation_pm=payment_method_sudo  # Will be converted to a kwarg in master.
            )._get_validation_currency().name.lower()
        partner = self.env['res.partner'].with_context(show_address=1).browse(partner_id).exists()
        id = self._paymentez_get_id()
        state = self._paymentez_get_state()
        application_code = self._paymentez_get_application_code()
        application_key = self._paymentez_get_application_key()

        inline_form_values = {
            'provider': {
                'id': id,
                'state': state,
                'application_code': application_code,
                'application_key': application_key
            },
            'currency_name': currency_name,
            'minor_amount': amount and payment_utils.to_minor_currency_units(amount, currency),
            'capture_method': 'manual' if self.capture_manually else 'automatic',
            'billing_details': {
                'name': partner.name or '',
                'email': partner.email or '',
                'phone': partner.phone or '',
                'address': {
                    'line1': partner.street or '',
                    'line2': partner.street2 or '',
                    'city': partner.city or '',
                    'state': partner.state_id.code or '',
                    'country': 'US' or '',
                    'postal_code': partner.zip or '',
                },
            },
            'is_tokenization_required': self._is_tokenization_required(**kwargs),
            'payment_methods_mapping': const.PAYMENT_METHODS_MAPPING,
        }
        return json.dumps(inline_form_values)
