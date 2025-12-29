/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
const { DateTime } = luxon;
import { Domain, InvalidDomainError } from "@web/core/domain";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {

    async load_server_data() {
        await super.load_server_data(...arguments);
        if (this.selectedOrder) {
            this.selectedOrder._updateRewards();
        }
    },


     async _loadLoyaltyData(products) {
        if (products !== undefined) {
            this.rewards.forEach((reward, index) => {
                if (reward.discount_line_product_id && reward.discount_line_product_id.length > 0) {
                    const productId = reward.discount_line_product_id[0];
                    delete this.db.product_by_id[productId];
                }
            });

            super._loadProductProduct(products);
        }

        this.program_by_id = {};
        this.reward_by_id = {};

        for (const program of this.programs) {

            this.program_by_id[program.id] = program;
            if (program.date_from) {
                program.date_from = DateTime.fromISO(program.date_from);
            }
            if (program.date_to) {
                program.date_to = DateTime.fromISO(program.date_to);
            }
            program.rules = [];
            program.rewards = [];
        }

        for (const rule of this.rules) {
            rule.valid_product_ids = new Set(rule.valid_product_ids);
            // rule.program_id = this.program_by_id[rule.program_id[0]];
            rule.program_id = typeof rule.program_id === 'object' && rule.program_id.id
                ? rule.program_id
                : this.program_by_id[rule.program_id[0]];
            rule.program_id.rules.push(rule);
        }
        for (const reward of this.rewards) {

            reward.program_id = this.program_by_id[reward.program_id[0]];
            if (
//                reward.reward_type === "product" &&
                reward?.date_from &&
                reward?.date_to
            ) {
                const dateFrom = DateTime.fromISO(reward.date_from).startOf("day");
                const dateTo = DateTime.fromISO(reward.date_to).endOf("day");
                const now = DateTime.now();
                if (dateFrom > now || dateTo < now) {
                    continue;
                }
            }
            this.reward_by_id[reward.id] = reward;

            reward.discount_line_product_id = this.db.get_product_by_id(
                reward.discount_line_product_id[0]
            );
            reward.all_discount_product_ids = new Set(reward.all_discount_product_ids);
            reward.program_id.rewards.push(reward);
        }
        await this._loadRewardsCustom(products)
     },

    async _loadRewardsCustom(products) {
        if (!this._cachedProductList) {
            this._cachedProductList = products //Object.values(this.db.product_by_id);
        }
        const productList = this._cachedProductList;

        // Procesar recompensas en lotes y en paralelo
        const batchSize = 1000;
        for (let i = 0; i < this.rewards.length; i += batchSize) {
            const batch = this.rewards.slice(i, i + batchSize);
            await Promise.all(
                batch.map(reward => this.compute_discount_product_ids(reward, productList))
            );
        }

        this.rewards = this.rewards.filter(reward => reward && reward.valid);
    },

    compute_discount_product_ids(reward, products) {
        const reward_product_domain = JSON.parse(reward.reward_product_domain);

        if (!reward_product_domain) {
            return;
        }

        const domain = new Domain(reward_product_domain);

        try {
            products
                .filter((product) => domain.contains(product))
                .forEach((product) => reward.all_discount_product_ids.add(product.id));
        } catch (error) {
            if (!(error instanceof InvalidDomainError || error instanceof TypeError)) {
                throw error;
            }
            const index = this.rewards.indexOf(reward);
            if (index != -1) {
                this.env.services.popup.add(ErrorPopup, {
                    title: _t("A reward could not be loaded"),
                    body: _t(
                        'The reward "%s" contain an error in its domain, your domain must be compatible with the PoS client',
                        this.rewards[index].description
                    ),
                });
                this.rewards[index] = null;
            }
        }
    },

    getPotentialFreeProductRewards() {
        const order = this.get_order();
        const allCouponPrograms = Object.values(order.couponPointChanges)
            .map((pe) => {
                return {
                    program_id: pe.program_id,
                    coupon_id: pe.coupon_id,
                };
            })
            .concat(
                order.codeActivatedCoupons.map((coupon) => {
                    return {
                        program_id: coupon.program_id,
                        coupon_id: coupon.id,
                    };
                })
            );
        const result = [];
        for (const couponProgram of allCouponPrograms) {
            const program = this.program_by_id[couponProgram.program_id];
            if (
                program &&
                program.pricelist_ids &&
                program.pricelist_ids.length > 0 &&
                (!order.pricelist || !program.pricelist_ids.includes(order.pricelist.id))
            ) {
                continue;
            }

            const points = order._getRealCouponPoints(couponProgram.coupon_id);
            const hasLine = order.orderlines.filter((line) => !line.is_reward_line).length > 0;
            if (program?.rewards){
                for (const reward of program.rewards.filter(
                (reward) => reward.reward_type == "product" && reward.reward_product_ids.length > 0
                )) {
                    if (points < reward.required_points) {
                        continue;
                    }
                    // Loyalty program (applies_on == 'both') should needs an orderline before it can apply a reward.
                    const considerTheReward =
                        program.applies_on !== "both" || (program.applies_on == "both" && hasLine);
                    if (reward.reward_type === "product" && considerTheReward) {
                        let hasPotentialQty = true;
                        let potentialQty;
                        for (const productId of reward.reward_product_ids) {
                            const product = this.db.get_product_by_id(productId);
                            potentialQty = order._computePotentialFreeProductQty(
                                reward,
                                product,
                                points
                            );
                            if (potentialQty <= 0) {
                                hasPotentialQty = false;
                            }
                        }
                        if (hasPotentialQty) {
                            result.push({
                                coupon_id: couponProgram.coupon_id,
                                reward: reward,
                                potentialQty,
                            });
                        }
                    }
                }
            }
        }
        return result;
    },

});

