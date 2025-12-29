/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { AddToCartNotification } from "@website_sale/js/notification/add_to_cart_notification/add_to_cart_notification";
import { formatCurrency } from "@web/core/currency";
import {useService} from "@web/core/utils/hooks";
import { onMounted, useState } from "@odoo/owl";

patch(AddToCartNotification.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            formattedPrices: {}
        });

        onMounted(() => {
            this.loadFormattedPrices();
        });
    },

    async loadFormattedPrices() {
        const pricePromises = this.props?.lines.map(async (line) => {
            try {
                const response = await fetch('/api/product/cart/discount/name', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        product_tmpl_id: line.name,
                        product_uom_qty: line.quantity
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                if (data.result.success) {
                    this.state.formattedPrices[line.id] = data.result.result || 0;
                } else {
                    console.error('API Error:', data.error);
                    this.state.formattedPrices[line.id] = 0;
                }
            } catch (error) {
                console.error('Error getting formatted price:', error);
                this.state.formattedPrices[line.id] = 0;
            }
        });
        await Promise.all(pricePromises);
    },

    getFormattedPrice(line) {
        const price = this.state.formattedPrices[line.id] || 0;
        return parseFloat(price).toFixed(2);
    }
});

