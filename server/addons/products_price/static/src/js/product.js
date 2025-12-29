/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order, Orderline, Product } from "@point_of_sale/app/store/models";
import {
    formatFloat,
    roundDecimals as round_di,
    roundPrecision as round_pr,
    floatIsZero,
} from "@web/core/utils/numbers";

patch(Order.prototype, {

     ceil2(x) {
        return Math.round(Math.ceil(x * 100) / 100 * 100) / 100;
    },

     async precioAjustado(pvp, q, uc, _pdesc = 0, _piva = 0) {
        pvp = parseFloat(pvp);
        uc = Math.max(parseFloat(uc), 1);
        q = parseFloat(q);

        const descuento = 1 - (parseFloat(_pdesc) / 100);
        const piva = 1 + (parseFloat(_piva) / 100);
        const piva_rest = (parseFloat(_piva) / 100);

        // Precio neto por unidad (con descuento e IVA)
        let precio_unitario = pvp * descuento * piva;


        if (q < uc) {
            precio_unitario = this.ceil2(precio_unitario);
        } else {
            precio_unitario = Math.round(precio_unitario * 10000) / 10000;
        }

        let precio_iva = precio_unitario * piva_rest;


        let prec = precio_unitario / piva
        let prec2 = prec / descuento

        prec2 = Math.round(prec2 * 10000) / 10000;

        return [prec2, prec];
    },

    get_tax_product(line){
        const pos = this.pos

        let currentTaxes = pos.getTaxesByIds(line.product.taxes_id)
        const order = pos.get_order();
        const taxes = pos.get_taxes_after_fp(line.product.taxes_id, order && order.fiscal_position);
        return taxes[0]?.amount
    },

     async prices_update_in_lines(){
        // Evitar modificar órdenes finalizadas
        if (this.finalized) {
            return;
        }

        const orderlines = this.get_orderlines()
        for (const line of orderlines) {
            if (line.is_reward_line){
                continue
            }

            let price = line.get_lst_price()
            let qty = line.quantity
            let uc = line.product.uom_po_factor_inv
            let percent_discount = line.product.discount
            if (!this.restrict_in_refund()){
                const [value_with_discount, valor_without_discount] = await this.precioAjustado(price, qty, uc, line.get_discount(), this.get_tax_product(line))
                line.set_unit_price(value_with_discount)
                line.set_price_without_discount(valor_without_discount)
            }
        }
    },

    restrict_in_refund() {
        const firstLine = this.get_orderlines()[0];
        return firstLine
            ? !!(firstLine.refunded_orderline_id || firstLine.sale_order_line_id)
            : false;
    },
})

patch(Orderline.prototype, {

    setup() {
        super.setup(...arguments);
        this.price_without_discount = 0;
    },

    set_price_without_discount(price){
        this.price_without_discount = price
    },
})

patch(Product.prototype, {

    ceil2(x) {
        return Math.round(Math.ceil(x * 100) / 100 * 100) / 100;
    },

    get_display_price_custom({
        pricelist = this.pos.getDefaultPricelist(),
        quantity = 1,
        price = this.get_price(pricelist, quantity),
        iface_tax_included = this.pos.config.iface_tax_included,
    } = {}) {
        const order = this.pos.get_order();
        const taxes = this.pos.get_taxes_after_fp(this.taxes_id, order && order.fiscal_position);
        const currentTaxes = this.pos.getTaxesByIds(this.taxes_id);
        const priceAfterFp = this.pos.computePriceAfterFp(price, currentTaxes);

        return priceAfterFp;
    },

    getFormattedUnitPrice() {

        const pos = this.pos

        let currentTaxes = pos.getTaxesByIds(this.taxes_id)
        const order = pos.get_order();
        const taxes = pos.get_taxes_after_fp(this.taxes_id, order && order.fiscal_position);

        const piva = 1 + (parseFloat(taxes[0]?.amount) / 100);

        const val_discount = 1
        const discount = (this.discount) / 100
        let price_unit = this.get_display_price_custom() * val_discount * piva

        const price_discount = this.get_display_price_custom() * discount

        if (1 < this.uom_po_factor_inv) {
            price_unit = this.ceil2(price_unit);
        } else {
            price_unit = Math.round(price_unit * 10000) / 10000;
        }

        const formattedUnitPrice = this.env.utils.formatCurrency(price_unit);

        if (this.to_weight) {
            return `${formattedUnitPrice}/${this.get_unit().name}`;
        } else {
            return formattedUnitPrice;
        }
    }
})

