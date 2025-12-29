/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";
import {OkeyPopup} from "../popups/okey_popup";
import {useService} from "@web/core/utils/hooks";
import { roundPrecision as round_pr, floatIsZero } from "@web/core/utils/numbers";


patch(PosStore.prototype, {

    async addProductFromUi(product, options) {
        const order = this.get_order();

        if (this.restrict_in_refund(order)){
            return ;
        }

        let selectedProgram = null;

        const orderTotal = this.get_order().get_total_with_tax();
        if (
            selectedProgram &&
            ["gift_card", "ewallet"].includes(selectedProgram.program_type) &&
            orderTotal < 0
        ) {
            options.price = -orderTotal;
        }
        if (selectedProgram && selectedProgram.program_type == "gift_card") {
            const shouldProceed = await this._setupGiftCardOptions(selectedProgram, options);
            if (!shouldProceed) {
                return;
            }
        } else if (selectedProgram && selectedProgram.program_type == "ewallet") {
            const shouldProceed = await this.setupEWalletOptions(selectedProgram, options);
            if (!shouldProceed) {
                return;
            }
        }

        this.get_order().add_product(product, options);
        await order._updatePrograms();

        order._updateRewards();
        return options;
    },


    restrict_in_refund(order){
        const orderlines = order.get_orderlines();
        if (!orderlines || orderlines.length === 0) {
            return false;
        }
        return !!orderlines[0].refunded_orderline_id;
    },


    _mergeFreeProductRewards(freeProductRewards, potentialFreeProductRewards) {
        const result = [];
        for (const reward of potentialFreeProductRewards) {
            if (!freeProductRewards.find((item) => item.reward.id === reward.reward.id)) {
                result.push(reward);
            }
        }
        return freeProductRewards.concat(result);
    },

    async _getPotentialRewardsCustom() {
        const order = this.get_order();
        const orderlines = order.get_orderlines();
        const normal_orderlines = order._get_normal_lines();
        // Claimable rewards excluding those from eWallet programs.
        // eWallet rewards are handled in the eWalletButton.
        let rewards = [];
        if (order) {
            const claimableRewards = order.getClaimableRewardsCustom();
            rewards = claimableRewards.filter(
                ({reward}) => reward.program_id.program_type !== "ewallet"
            );
        }
        const discountRewards = rewards.filter(({reward}) => reward.reward_type == "discount");
        const potentialFreeProductRewards = this.getPotentialFreeProductRewardsCustom();
        // const potentialFreeProductRewards = rewards.filter(({reward}) => reward.reward_type == "product");

//        const reward_firs_filter = this.priority_discount_filter(discountRewards)

        const discount_rewards = this._filtrado(discountRewards, orderlines)

//        const discount_rewards = this._filtrado(reward_firs_filter, orderlines)
        const new_discountRewards = this.process_discounts(discount_rewards);
        const new_product_result = this._filtrado(potentialFreeProductRewards, orderlines)
        const processedRewards = await this.review_limit_for_partner(new_product_result)
        const processedRewardsNew = await this.process_discounts(processedRewards)

        return new_discountRewards.concat(processedRewardsNew);

    },

    process_discounts(array) {
        if (!Array.isArray(array)) {
            return [];
        }

        // Paso 1: Agrupar por tres criterios
        const groupedByProducts = {};
        for (const item of array) {
            if (!item || !item.reward || !item.reward.all_discount_product_ids || !item.reward.program_id) {
                continue;
            }

            const productIds = Array.from(item.reward.all_discount_product_ids).join(",");
            const trigger = item.reward.program_id.trigger || "unknown";
            const programId = item.reward.program_id.id || "no_program";

            if (!groupedByProducts[productIds]) {
                groupedByProducts[productIds] = {};
            }
            if (!groupedByProducts[productIds][trigger]) {
                groupedByProducts[productIds][trigger] = {};
            }
            if (!groupedByProducts[productIds][trigger][programId]) {
                groupedByProducts[productIds][trigger][programId] = [];
            }

            groupedByProducts[productIds][trigger][programId].push(item);
        }

        const result = [];
        let limit_exceded = false;
        const order = this.get_order();
        const orderlines = order._get_normal_lines();
        const quantityMap = new Map();
        orderlines.forEach(line => {
            const productId = line.product.id;
            quantityMap.set(productId, (quantityMap.get(productId) || 0) + line.quantity);
        });

        // Función para obtener la cantidad total para un grupo de IDs
        const getQuantityForProductGroup = (productIdsString) => {
            const idsArray = productIdsString.split(',').map(id => parseInt(id.trim()));
            return idsArray.reduce((total, id) => total + (quantityMap.get(id) || 0), 0);
        };

        for (const productIds in groupedByProducts) {
            const byProduct = groupedByProducts[productIds];
            let withCodeCount = 0;

            // Obtener la cantidad total para todos los IDs del grupo
            let totalQuantityForGroup = getQuantityForProductGroup(productIds);

            let remainingQty = totalQuantityForGroup;

            // Primero procesamos todos los "with_code"
            for (const trigger in byProduct) {
                if (trigger === "with_code") {
                    const byTrigger = byProduct[trigger];
                    for (const programId in byTrigger) {
                        const group = byTrigger[programId];
                        const initialLength = result.length;

                        if (group && group[0].reward.discount_applicability == "order"){
                            result.push(...group)
                        } else {
                            limit_exceded = this.filter_by_cupon_limit(group, result, remainingQty);
                            const addedCount = result.length - initialLength;
                            withCodeCount += addedCount;
                            remainingQty -= addedCount;
                        }
                    }
                }
            }


            // Luego procesamos los que no son "with_code"
            for (const trigger in byProduct) {
                if (trigger !== "with_code") {
                    const byTrigger = byProduct[trigger];
                    for (const programId in byTrigger) {
                        const group = byTrigger[programId];

                        group.forEach(item => {
                            item.potentialQty = remainingQty;
                        });

                        if (remainingQty > 0) {
                            const itemsToAdd = group.slice(0, remainingQty);
                            result.push(...itemsToAdd);
                            remainingQty -= itemsToAdd.length;
                        }
                    }
                }
            }
        }

        if (limit_exceded && limit_exceded.exceedsOrderLimit) {
            this.message("Límite de cupones aplicables superado");
        } else if (limit_exceded && limit_exceded.exceedsQuantityLimit) {
            this.message("No hay suficiente cantidad de producto para aplicar el cupón");
        }

        return result;
    },


    async message(messageText) {
        await this.env.services.popup.add(OkeyPopup, {
            title: "No se pudo aplicar el cupón",
            body: messageText,
        });
        this.get_order().recreate_discount_lines()
    },

    filter_by_cupon_limit(group, result, quantity_products) {
        const limitFromOrder = group[0]?.reward?.program_id?.limit_for_order || 0;
        const applies_by_boxes = group[0]?.reward?.program_id?.applies_by_boxes;
        const max_boxes_limit = group[0]?.reward?.program_id?.max_boxes_limit;
        const discount_applicability = group[0]?.reward?.discount_applicability;

        const actualLimit = (applies_by_boxes && max_boxes_limit)
            ? (limitFromOrder === 0 ? 0 : limitFromOrder)
            : limitFromOrder;


        let exceedsOrderLimit = group.length > actualLimit;
        exceedsOrderLimit = (actualLimit === 0) ? false : exceedsOrderLimit;

        if (discount_applicability == "order"){
            quantity_products = 1
        }

        const effectiveLimit = (quantity_products !== undefined && (quantity_products < actualLimit || actualLimit === 0))
            ? quantity_products
            : actualLimit;

        const exceedsQuantityLimit = quantity_products !== undefined && group.length > quantity_products;

        if (effectiveLimit === 0 && !exceedsQuantityLimit) {
            result.push(...group);
        } else {
            result.push(...group.slice(0, effectiveLimit));
        }

        return {
            exceedsOrderLimit,
            exceedsQuantityLimit
        };
    },


    getPotentialFreeProductRewardsCustom() {
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

        // 1. Primero, recolecta los programas en un objeto
        const programById = {};

        for (const couponProgram of allCouponPrograms) {
            const program = this.program_by_id[couponProgram.program_id];

            if (program) {
                programById[couponProgram.program_id] = program;
            }
        }

        const findGroup = createRewardsFinder(programById);

        for (const couponProgram of allCouponPrograms) {
            const program = this.program_by_id[couponProgram.program_id];
            if(program === undefined){
                continue;
            }
            if (
                program.pricelist_ids.length > 0 &&
                (!order.pricelist || !program.pricelist_ids.includes(order.pricelist.id))
            ) {
                continue;
            }

            const points = order._getRealCouponPoints(couponProgram.coupon_id);
            const hasLine = order.orderlines.filter((line) => !line.is_reward_line).length > 0;
            // const reward_list = program.rewards.filter(
            //     (reward) => reward.reward_type === "product" && reward.reward_product_ids.length > 0
            // )
            const reward_list = program.rewards
            const group = findGroup(program);

            for (const reward of reward_list) {
                if (points < reward.required_points) {
                    continue;
                }
                // Loyalty program (applies_on == 'both') should needs an orderline before it can apply a reward.
                const considerTheReward =
                    program.applies_on !== "both" || (program.applies_on === "both" && hasLine);
                if (reward.reward_type === "product" && considerTheReward) {
                    let hasPotentialQty = true;
                    let potentialQty;
                    for (const productId of reward.reward_product_ids) {
                        const product = this.db.get_product_by_id(productId);
                        potentialQty = order._computePotentialFreeProductQtyCustom(
                            reward,
                            product,
                            points,
                            group
                        );
                        if (potentialQty <= 0) {
                            hasPotentialQty = false;
                        }
                    }
                    if (hasPotentialQty) {
                        result.push({
                            coupon_id: couponProgram.coupon_id,
                            reward: reward,
                            potentialQty: potentialQty,
                            potentialQtySelect: potentialQty
                        });
                    }
                }
            }
        }
        return result;
    },

    priority_discount_filter(array) {
        if (!Array.isArray(array)) return [];

        const max_discount_map = {};
        const with_code_items = [];

        for (const item of array) {
            const trigger_product = item?.reward?.program_id?.trigger_product_ids?.[0];
            const discount_percentage = item.reward.discount || 0;
            const trigger = item?.reward?.program_id?.trigger;

            if (!trigger_product && trigger !== "with_code") continue;

            if (trigger === "with_code") {
                with_code_items.push(item);
                continue;
            }

            if (
                !max_discount_map[trigger_product] ||
                discount_percentage > (max_discount_map[trigger_product].reward.discount || 0)
            ) {
                max_discount_map[trigger_product] = item;
            }
        }

        return [...Object.values(max_discount_map), ...with_code_items];
    },

    _filtrado(array, orderlines) {
        if (!Array.isArray(array)) {
            return [];
        }
        if (!Array.isArray(orderlines)) {
            return array;
        }
        const orderlineIds = new Set(orderlines.map(orderline => orderline.reward_id));
        return array.filter(item => !orderlineIds.has(item.reward.id));
    },

    async review_limit_for_partner(result){
        const order = this.get_order();
        const partner_id = order.partner?.id;
        let processedRewards = [];

        for (let reward of result) {
            let reward_id = reward.reward?.id
            let product_reward_id_ = reward.reward?.discount_line_product_id?.id
            let product_reward_id = reward.reward?.program_id?.trigger_product_ids[0]

            if (!product_reward_id || !reward_id || !partner_id) continue

            const limit = await order._search_limit_for_reward(product_reward_id, reward_id, partner_id)

            if (limit.unlimited) {
                processedRewards.push(reward);
                continue;
            }

            if (limit.limit_items === 0) {
                continue;

            } else if (reward.potentialQty > limit.limit_items){
                reward.potentialQty = limit.limit_items;
            }

            processedRewards.push(reward);

        }
        return processedRewards
    },


});


function createRewardsFinder(programById) {
    const groupMap = new Map();

    for (const program of Object.values(programById)) {
        const triggerProductId = program.trigger_product_ids?.[0];
        if (triggerProductId !== undefined) {
            if (!groupMap.has(triggerProductId)) {
                groupMap.set(triggerProductId, []);
            }
            groupMap.get(triggerProductId).push(program.rewards || []);
        }
    }

    return (targetProgram) => {
        const triggerProductId = targetProgram.trigger_product_ids?.[0];

        if (triggerProductId === undefined) {
            return targetProgram.rewards || [];
        }

        const rewardsArrays = groupMap.get(triggerProductId) || [targetProgram.rewards || []];
        return rewardsArrays.flat();
    };
}


