/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import VariantMixin from "@website_sale/js/sale_variant_mixin";
import { debounce } from "@web/core/utils/timing";

publicWidget.registry.WebsiteSale.include({

    init: function () {
        this._super.apply(this, arguments);

        this._changeCartQuantity = debounce(this._changeCartQuantity.bind(this), 150);
        this._changeCountry = debounce(this._changeCountry.bind(this), 150);
    },

    start() {
        return this._super(...arguments);
    },
    onClickAddCartJSON(ev) {
        ev.preventDefault();

        const $btn = $(ev.currentTarget);
        const $input = $btn.closest('.input-group').find('input[name="add_qty"], input.js_quantity');
        const max_d = parseFloat($input.data('max')) + 1
        const min = parseFloat($input.data('min') || 0);
        const max = parseFloat(Infinity) || max_d;
        const prev = parseFloat($input.val() || 0);
        const isMinus = $btn.has('.fa-minus').length > 0;

        let next = prev + (isMinus ? -1 : 1);
        next = Math.max(min, Math.min(max, next));

        if (next >= (max_d-1)) {
            this.warning_message = "No es posible agregar más unidades: no hay más stock disponible para este producto.";
            this.$('#max_qty_warning').removeClass('d-none').text(this.warning_message);
        } else {
            this.warning_message = "";
            this.$('#max_qty_warning').addClass('d-none');
        }

        if (next !== prev) {
            $input.val(next).trigger('change');
        }

        return false;
    },

});
