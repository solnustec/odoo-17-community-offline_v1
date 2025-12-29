import { PosGlobalState, Product } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(PosGlobalState, {
    async _fetchLoyaltyDiscounts() {
        if (!this.db || !this.db.product_by_id) return;

        const products = Object.values(this.db.product_by_id).map(product => ({
            product_id: product.id,
            price: product.lst_price,  // Precio base del producto
        }));

        if (products.length === 0) return;

        try {
            const response = await fetch("/website/loyalty_data/point-of-sale", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ products }),
            });

            const data = await response.json();
            console.log(data)
            if (data.rewards) {
                data.rewards.forEach((reward, index) => {
                    const product = this.db.product_by_id[products[index].product_id];
                    if (product) {
                        product.discounted_price = reward.discounted_price;
                    }
                });

                // Forzar actualización del POS
                this.trigger("update-products");
            }
        } catch (error) {
            console.error("Error fetching loyalty discounts:", error);
        }
    },

    async after_load_data() {
        await this._fetchLoyaltyDiscounts();
    },
});
