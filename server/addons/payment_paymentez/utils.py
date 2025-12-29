# Part of Odoo. See LICENSE file for full copyright and licensing details.
def get_application_code(provider_sudo):
    
    return provider_sudo.paymentez_application_code

def get_application_key(provider_sudo):
    
    return provider_sudo.paymentez_application_key

def get_id(provider_sudo):

    return provider_sudo.id


def get_state(provider_sudo):

    return provider_sudo.state

def include_shipping_address(tx_sudo):
    """ Include the shipping address of the related sales order or invoice to the payload of the API
    request. If no related sales order or invoice exists, the addres is not included.

    Note: `self.ensure_one()`

    :param payment.transaction tx_sudo: The sudoed transaction of the payment.
    :return: The subset of the API payload that includes the billing and delivery addresses.
    :rtype: dict
    """
    tx_sudo.ensure_one()

    if 'sale_order_ids' in tx_sudo._fields and tx_sudo.sale_order_ids:
        order = tx_sudo.sale_order_ids[:1]
        return format_shipping_address(order.partner_shipping_id)
    elif 'invoice_ids' in tx_sudo._fields and tx_sudo.invoice_ids:
        invoice = tx_sudo.invoice_ids[:1]
        return format_shipping_address(invoice.partner_shipping_id)
    return {}


def format_shipping_address(shipping_partner):
    """ Format the shipping address to comply with the payload structure of the API request.

    :param res.partner shipping_partner: The shipping partner.
    :return: The formatted shipping address.
    :rtype: dict
    """
    return {
        'shipping[address][city]': shipping_partner.city,
        'shipping[address][country]': shipping_partner.country_id.code,
        'shipping[address][line1]': shipping_partner.street,
        'shipping[address][line2]': shipping_partner.street2,
        'shipping[address][postal_code]': shipping_partner.zip,
        'shipping[address][state]': shipping_partner.state_id.name,
        'shipping[name]': shipping_partner.name or shipping_partner.parent_id.name,
    }
