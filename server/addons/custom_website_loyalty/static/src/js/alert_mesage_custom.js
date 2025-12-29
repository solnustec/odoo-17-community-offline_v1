/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import cartUtils from "@website_sale/js/website_sale_utils";

patch(cartUtils, {
    showWarning(message) {
        if (!message) {
            return;
        }

        var $page = $('.oe_website_sale');
        var cart_alert = $page.children('#data_warning');
        if (!cart_alert.length) {
            cart_alert = $(
                '<div class="alert alert-warning alert-dismissible custom-warning" role="alert" id="data_warning">' +
                    '<button type="button" class="btn-close" data-bs-dismiss="alert"></button> ' +
                    '<i class="fa fa-exclamation-triangle"></i> ' +
                    '<span></span>' +
                '</div>').prependTo($page);
        }
        cart_alert.children('span:last-child').text(message);
        cart_alert.addClass('fade-in');
    }
});

export default cartUtils;