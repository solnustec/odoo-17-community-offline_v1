/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {Mutex} from "@web/core/utils/concurrency";
import {roundPrecision} from "@web/core/utils/numbers";
import {Order} from "@point_of_sale/app/store/models";
import {PosLoyaltyCard} from "@pos_loyalty/overrides/models/loyalty";

import {_t} from "@web/core/l10n/translation";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import {OkeyPopup} from "../popups/okey_popup";
import {
    formatFloat,
    roundDecimals as round_di,
    roundPrecision as round_pr,
    floatIsZero,
} from "@web/core/utils/numbers";


const mutex = new Mutex(); // Used for sequential cache updates
const updateRewardsMutex = new Mutex();
let pointsForProgramsCountedRules = {};


const recreateDiscountLinesDebouncer = (() => {
    let timeoutId = null;
    const delay = 200;

    return async (callback) => {
        if (timeoutId) {
            clearTimeout(timeoutId);
        }

        timeoutId = setTimeout(async () => {
            await callback();
            timeoutId = null;
        }, delay);
    };
})();

const fetchDataPromotionsDebouncer = (() => {
    let timeoutId = null;
    const delay = 300;

    return async (callback) => {
        if (timeoutId) {
            clearTimeout(timeoutId);
        }

        timeoutId = setTimeout(async () => {
            await callback();
            timeoutId = null;
        }, delay);
    };
})();

function _combinePercentSequential(pExistente, pWeekday) {
    const e = Math.max(0, Math.min(100, Number(pExistente || 0))) / 100;
    const w = Math.max(0, Math.min(100, Number(pWeekday || 0))) / 100;
    if (w <= 0) return 0;
    const denom = (1 - e);
    if (denom <= 0) return 100; // caso extremo (ya 100%)
    return Math.min(100, (w * denom) * 100);
}

function _getExistingPercentOnSpecific(order, reward) {
    const applicable = reward?.all_discount_product_ids; // Set de product_ids
    if (!applicable || !applicable.size) return 0;
    let maxPct = 0;

    const allLines = order.get_orderlines?.() || [];

    for (const line of allLines) {
        const pid = line.get_product?.().id;
        if (!pid) continue;
        if (applicable.has(pid)) {
            const p = Number(line.percent_discount || 0);
            if (p > maxPct) maxPct = p;
        }
    }
    return maxPct;
}

patch(Order.prototype, {

    get_total_discount() {
        const ignored_product_ids = this._get_ignored_product_ids_total_discount();
        return round_pr(
            this.orderlines.reduce((sum, orderLine) => {
                if (!ignored_product_ids.includes(orderLine.product.id)) {
                    sum +=
                        orderLine.get_all_prices(1).priceWithoutTaxBeforeDiscount *
                        (orderLine.get_discount() / 100) *
                        orderLine.get_quantity();
                    if (
                        orderLine.display_discount_policy() === "without_discount" &&
                        !(orderLine.price_type === "manual")
                    ) {
                        sum +=
                            (orderLine.get_taxed_lst_unit_price() -
                                orderLine.getUnitDisplayPriceBeforeDiscount()) *
                            orderLine.get_quantity();
                    }
                }
                return sum;
            }, 0),
            this.pos.currency.rounding
        );
    },

    _apply_daily_discount() {
        const discountPercent = Number(this.pos.getWeekdayPromoPercent?.() || 0);
        if (discountPercent <= 0) return;

        const isDigitalOrder =
            (this.x_channel || "").toLowerCase() === "canal digital";

        const lines = this._get_normal_lines?.() || [];

        for (const line of lines) {
            const product = line.get_product();
            const productId = product?.id;

            if (!productId) continue;

            // 1) Nunca tocar la línea de envío
            const isShippingProduct =
                product?.is_delivery_product === true ||
                product?.default_code === "ENVIOSCHATBOT" ||
                line.is_delivery === true;

            if (isShippingProduct) {
                continue;
            }

            // 2) Si viene del sitio web y la línea original viene de sale.order → NO tocar
            if (isDigitalOrder && line.is_from_sale_order) {
                continue;
            }

            // 3) Respetar productos de reward / promociones especiales
            const rewardActive = this.pos.rewards?.find(
                (reward) =>
                    reward.reward_product_ids?.includes(productId) &&
                    reward.active !== false &&
                    reward.is_archived !== true
            );

            if (rewardActive) {
                continue;
            }

            // 4) Lógica de descuento acumulable
            const existing = Number(line.discount || 0);

            if (existing >= discountPercent) {
                continue;
            }

            const newDiscount = Math.min(100, existing + discountPercent);

            line.set_discount(newDiscount);
            line.is_promo_line = true;

            line.discount_reason =
                existing > 0
                    ? `Descuento combinado (${existing}% + ${discountPercent}%)`
                    : `Descuento del día (${discountPercent}%)`;

            line.percent_discount = newDiscount;
            line.discount = newDiscount;
        }
    },


    _getRealCouponPoints(coupon_id) {
        let points = 0;
        const dbCoupon = this.pos.couponCache[coupon_id];
        if (dbCoupon) {
            points += dbCoupon.balance;
        }
        Object.values(this.couponPointChanges).some((pe) => {
            if (pe.coupon_id === coupon_id) {
                if (this.pos.program_by_id[pe.program_id] && this.pos.program_by_id[pe.program_id].applies_on !== "future") {
                    points += pe.points;
                }
                // couponPointChanges is not supposed to have a coupon multiple times
                return true;
            }
            return false;
        });
        for (const line of this.get_orderlines()) {
            if (line.is_reward_line && line.coupon_id === coupon_id) {
                points -= line.points_cost;
            }
        }
        return points;
    },

    async add_product(product, options) {
        const line = await super.add_product(...arguments);
        line.set_reward_product_id(options.reward_product_id)
        line.set_original_id_reward(options.original_id_reward)
        return line;
    },

    setup() {
        super.setup(...arguments);
        this.list_rewards_selected = [];
        this.cupon_by_id = {}
//        this.notification = useService("notification");
    },

    initNotifiedRewards() {
        if (!this.notified_rewards) {
            this.notified_rewards = new Set();
        }
        if (!this.active_reward_ids) {
            this.active_reward_ids = new Set();
        }
    },


    async popupNotificationReward() {
        this.initNotifiedRewards();
        const lines_reward = this.get_orderlines().filter(line =>
            line.is_reward_line
        );
        const current_reward_ids = new Set(
            lines_reward.map(line => line.reward_id)
        );
        for (const old_reward_id of this.active_reward_ids) {
            if (!current_reward_ids.has(old_reward_id)) {
                this.notified_rewards.delete(old_reward_id);
            }
        }

        this.active_reward_ids = current_reward_ids;

        for (const line of lines_reward) {
            const reward_id = line.reward_id;
            const program_id = line.program_id;

            if (!this.notified_rewards.has(reward_id)) {
                this.notified_rewards.add(reward_id);
                const programNote = this.pos.program_by_id[program_id]?.note_promotion;

                if (programNote) {
                    await this.env.services.popup.add(OkeyPopup, {
                        title: _t("Recompensa agregada"),
                        body: _t(`"${programNote}"`),
                    });
                }
            }
        }
    },

    export_as_JSON() {
        const result = super.export_as_JSON(...arguments);
        result.is_reward_line = this.is_reward_line;
        result.reward_id = this.reward_id;
        result.original_id_reward = this.original_id_reward;
        result.reward_prod_id = this.reward_prod_id;
        result.reward_product_id = this.reward_product_id;
        result.program_id = this.program_id;
        result.percent_discount = this.percent_discount;
        result.total_with_discount = this.total_with_discount;
        result.reward_with_code = this.reward_with_code;
        result.coupon_id = this.coupon_id;
        result.limit_for_order = this.limit_for_order;
        result.reward_identifier_code = this.reward_identifier_code;
        result.points_cost = this.points_cost;
        result.giftBarcode = this.giftBarcode;
        result.giftCardId = this.giftCardId;
        result.amount_applied = this.amount_applied;
        result.quantity_applied = this.quantity_applied;
        result.eWalletGiftCardProgramId = this.eWalletGiftCardProgram
            ? this.eWalletGiftCardProgram.id
            : null;
        result.full_product_name = this.full_product_name || result.full_product_name || result.name;
        result.name = this.full_product_name || result.name || result.full_product_name;
        return result;
    },

    init_from_JSON(json) {
        if (json.is_reward_line) {
            this.is_reward_line = json.is_reward_line;
            this.reward_id = json.reward_id;
            // Since non existing coupon have a negative id, of which the counter is lost upon reloading
            //  we make sure that they are kept the same between after a reload between the order and the lines.
            this.coupon_id = this.order.oldCouponMapping[json.coupon_id] || json.coupon_id;
            this.reward_identifier_code = json.reward_identifier_code;
            this.points_cost = json.points_cost;
            this.reward_prod_id = json.reward_prod_id;
            this.reward_with_code = json.reward_with_code;
        }
        this.limit_for_order = json.limit_for_order;
        this.percent_discount = json.percent_discount;
        this.total_with_discount = json.total_with_discount;
        this.program_id = json.program_id;
        this.original_id_reward = json.original_id_reward;
        this.reward_product_id = json.reward_product_id;
        this.giftBarcode = json.giftBarcode;
        this.giftCardId = json.giftCardId;
        this.amount_applied = json.amount_applied;
        this.quantity_applied = json.quantity_applied;
        this.eWalletGiftCardProgram = this.pos.program_by_id[json.eWalletGiftCardProgramId];
        super.init_from_JSON(...arguments);

    },

    set_orderline_options(line, options) {
        super.set_orderline_options(...arguments);
        if (options && options.is_reward_line) {
            line.is_reward_line = options.is_reward_line;
            line.reward_id = options.reward_id;
            line.program_id = options.program_id;
            line.reward_prod_id = options.reward_prod_id;
            line.reward_type = options.reward_type
            line.coupon_id = options.coupon_id;
            line.reward_identifier_code = options.reward_identifier_code;
            line.points_cost = options.points_cost;
            line.price_type = "automatic";
            line.is_selected = options.is_selected;
            line.is_selectionable = options.is_selectionable;
            line.reward_with_code = options.reward_with_code;
        }
        if (options.is_part_of_reward) {
            line.is_part_of_reward = options.is_part_of_reward;
            line.reward_prod_id = options.reward_prod_id;
            line.reward_type = options.reward_type
        }
        line.limit_for_order = options.limit_for_order;
        line.percent_discount = options.percent_discount;
        line.total_with_discount = options.total_with_discount;
        line.original_id_reward = options.original_id_reward;
        line.program_id = options.program_id;
        line.reward_product_id = options.reward_product_id;
        line.giftBarcode = options.giftBarcode;
        line.amount_applied = options.amount_applied;
        line.quantity_applied = options.quantity_applied;
        line.giftCardId = options.giftCardId;
        line.eWalletGiftCardProgram = options.eWalletGiftCardProgram;
        if (options?.full_product_name) line.full_product_name = options.full_product_name;
        if (options?.name) line.full_product_name = line.full_product_name || options.name;
    },


    _get_normal_lines() {
        if (this.orderlines) {
            return this.orderlines.filter((line) => !line.reward_product_id);
        }
        return this.orderlines;

        this.state.subtotalTax0 = subtotalTax0
        this.state.subtotalTax15 = subtotalTax15

    },

    _get_reward_lines_custom() {
        if (this.orderlines) {
            return this.orderlines.filter((line) => line.reward_product_id);
        }
        return this.orderlines;
    },

    async validate_order_first() {
        if (this.orderlines.length === 0) {
            await this.env.services.popup.add(OkeyPopup, {
                title: _t("Orden no válida"),
                body: _t("No hay líneas de pedido aún."),
            });
            return false;
        }

        if (this.partner === undefined) {
            await this.env.services.popup.add(OkeyPopup, {
                title: _t("Orden no válida"),
                body: _t("Se requiere un cliente para procesar el pago de la orden."),
            });
            return false;
        }

        return true;
    },

    async pay() {

        const validate = await this.validate_order_first()

        if (!this.orderlines[0]?.sale_order_line_id) {
            this.sale_id = null
        }

        if (!validate) {
            return;
        }
        const orderlines = this.get_orderlines()

        const eWalletLine = orderlines.find(
            (line) => line.getEWalletGiftCardProgramType() === "ewallet"
        );
        if (eWalletLine && !this.get_partner()) {
            const {confirmed} = await this.env.services.popup.add(ConfirmPopup, {
                title: _t("Customer needed"),
                body: _t("eWallet requires a customer to be selected"),
            });
            if (confirmed) {
                const {confirmed, payload: newPartner} =
                    await this.env.services.pos.showTempScreen("PartnerListScreen", {
                        partner: null,
                    });
                if (confirmed) {
                    this.set_partner(newPartner);
                }
            }
        } else {
            return await super.pay(...arguments);
        }
    },

    _updateRewardLines() {
        if (!this.orderlines.length) {
            return;
        }
        const rewardLines = this._get_reward_lines();
        if (!rewardLines.length) {
            return;
        }
        const productRewards = [];
        const otherRewards = [];
        const paymentRewards = []; // Gift card and ewallet rewards are considered payments and must stay at the end
        for (const line of rewardLines) {
            const claimedReward = {
                reward: this.pos.reward_by_id[line.reward_id],
                coupon_id: line.coupon_id,
                args: {
                    product: line.reward_product_id,
                    price: line.price,
                    quantity: line.quantity,
                    cost: line.points_cost,
                },
                reward_identifier_code: line.reward_identifier_code,
            };
            if (
                claimedReward.reward.program_id.program_type === "gift_card" ||
                claimedReward.reward.program_id.program_type === "ewallet"
            ) {
                paymentRewards.push(claimedReward);
            } else if (claimedReward.reward.reward_type === "product") {
                productRewards.push(claimedreward_product_ideward);
            } else if (
                !otherRewards.some(
                    (reward) =>
                        reward.reward_identifier_code === claimedReward.reward_identifier_code
                )
            ) {
                otherRewards.push(claimedReward);
            }
        }
        const allRewards = productRewards.concat(otherRewards).concat(paymentRewards);
        const allRewardsMerged = [];
        allRewards.forEach((reward) => {
            if (reward.reward.reward_type == "discount") {
                allRewardsMerged.push(reward);
            } else {
                const reward_index = allRewardsMerged.findIndex(
                    (item) =>
                        item.reward.id === reward.reward.id && item.args.price === reward.args.price
                );
                if (reward_index > -1) {
                    allRewardsMerged[reward_index].args.quantity += reward.args.quantity;
                    allRewardsMerged[reward_index].args.cost += reward.args.cost;
                } else {
                    allRewardsMerged.push(reward);
                }
            }
        });

        for (const claimedReward of allRewardsMerged) {
            // For existing coupons check that they are still claimed, they can exist in either `couponPointChanges` or `codeActivatedCoupons`
            if (
                !this.codeActivatedCoupons.find(
                    (coupon) => coupon.id === claimedReward.coupon_id
                ) &&
                !this.couponPointChanges[claimedReward.coupon_id]
            ) {
                continue;
            }
        }
    },


    getLoyaltyPoints() {
        // map: couponId -> LoyaltyPoints
        try {
            const loyaltyPoints = {};
            for (const pointChange of Object.values(this.couponPointChanges)) {
                const {coupon_id, points, program_id} = pointChange;
                const program = this.pos.program_by_id[program_id];
                if (program?.program_type !== "loyalty") {
                    // Not a loyalty program, skip
                    continue;
                }
                const loyaltyCard = this.pos.couponCache[coupon_id] || /* or new card */ {
                    id: coupon_id,
                    balance: 0,
                };
                let [won, spent, total] = [0, 0, 0];
                const balance = loyaltyCard.balance;
                // won += points - this._getPointsCorrection(program);
                won += points
                if (coupon_id !== 0) {
                    for (const line of this._get_reward_lines()) {
                        if (line.coupon_id === coupon_id) {
                            let reward = this.pos.reward_by_id[line.reward_id];
                            spent += (line.points_cost * line.get_quantity()) / reward?.reward_product_qty;
                        }
                    }
                }
                total = balance + won - spent;
                const name = program.portal_visible ? program.portal_point_name : _t("Points");
                loyaltyPoints[coupon_id] = {
                    won: parseFloat(won.toFixed(2)),
                    spent: parseFloat(spent.toFixed(2)),
                    // Display total when order is ongoing.
                    total: parseFloat(total.toFixed(2)),
                    // Display balance when order is done.
                    balance: parseFloat(balance.toFixed(2)),
                    name,
                    program,
                };
            }
            return Object.entries(loyaltyPoints).map(([couponId, points]) => ({
                couponId,
                points,
                program: points.program,
            }));
        } catch (e) {
            console.log(e)
        }
    },

    _getPointsCorrection(program) {
        // Validación temprana
        if (!program || !program.rules) {
            return 0;
        }

        const rewardLines = this.orderlines.filter((line) => line.is_reward_line);
        let res = 0;

        for (const rule of program.rules) {
            for (const line of rewardLines) {
                const reward = this.pos.reward_by_id[line.reward_id];
                if (reward && this._validForPointsCorrection(reward, line, rule)) {
                    if (rule.reward_point_mode === "order") {
                        res += rule.reward_point_amount;
                    } else if (rule.reward_point_mode === "money") {
                        res -= roundPrecision(
                            rule.reward_point_amount * line.get_price_with_tax(),
                            0.01
                        );
                    } else if (rule.reward_point_mode === "unit") {
                        res += rule.reward_point_amount * line.get_quantity();
                    }
                }
            }
        }
        return res;
    },

    _isRewardProductPartOfRules(reward, product) {
        if (reward && product?.id) {
            return (reward.program_id.rules.filter((rule) => rule.any_product || rule.valid_product_ids.has(product.id)).length > 0);
        }
        return false;
    },


    _computePotentialFreeProductQtyCustom(reward, product, remainingPoints, reward_list) {
        if (reward.program_id.trigger == "auto") {
            if (
                product?.id &&
                reward &&
                this._isRewardProductPartOfRules(reward, product) &&
                reward.program_id.applies_on !== "future"
            ) {
                const line = this.get_orderlines().find(
                    (line) => line.reward_product_id === product.id
                );
                // Compute the correction points once even if there are multiple reward lines.
                // This is because _getPointsCorrection is taking into account all the lines already.
                const claimedPoints = line ? this._getPointsCorrection(reward.program_id) : 0;

                const limit = distributePointsWithPrograms(remainingPoints, reward_list, this.list_rewards_selected, this.get_orderlines())
                if (limit?.distribution[reward.id] !== undefined) {
                    return (limit.distribution[reward.id]) * reward.reward_product_qty
                } else {
                    return Math.floor(
                        ((remainingPoints - claimedPoints) / reward.required_points) *
                        reward.reward_product_qty
                    );
                }

            } else {
                const limit = distributePointsWithPrograms(remainingPoints, reward_list, this.list_rewards_selected, this.get_orderlines())
                if (limit?.distribution[reward.id] !== undefined) {
                    return (limit.distribution[reward.id]) * reward.reward_product_qty
                } else {
                    return Math.floor(
                        (remainingPoints / reward.required_points) * reward.reward_product_qty
                    );
                }
            }
        } else if (reward.program_id.trigger == "with_code") {
            if (this.verifi_values_of_cupon(reward)) {
                return Math.floor(
                    (remainingPoints / reward.required_points) * reward.reward_product_qty
                );
            } else {
                return 0
            }

        }
    },

    verifi_values_of_cupon(reward) {
        const rules = reward.program_id.rules;
        const orderLines = this.get_orderlines();

        if (!orderLines || !orderLines.length || !rules || !rules.length) {
            return false;
        }

        for (const rule of rules) {
            const validProductIds = rule?.valid_product_ids;

            if (!validProductIds) {
                return false;
            }

            const targetProductId = validProductIds[0];
            const minimumQty = rule?.minimum_qty || 0;

            const matchingLine = orderLines.find(line => line.product_id === targetProductId);

            if (!matchingLine) {
                return false;
            }

            const lineQuantity = matchingLine.quantity || 0;
            if (lineQuantity < minimumQty) {
                return false;
            }
        }
        return true;
    },

    async update_extra_info_lines_discount() {
        let orderlines = this._get_normal_lines();
        let allLines = this.get_orderlines();

        for (let normalLine of orderlines) {
            // Buscar todas las líneas de descuento que coincidan con el producto
            let discountLines = allLines.filter(line =>
                line.reward_prod_id &&
                line.reward_prod_id === normalLine.product.id &&
                line.price !== 0
            );

            let discountLineToUse = null;

            if (discountLines.length > 0) {
                // Prioridad 1: Buscar líneas con coupon_id negativo
                let negativeCouponLines = discountLines.filter(line =>
                    line.coupon_id && line.coupon_id < 0
                );

                if (negativeCouponLines.length > 0) {
                    // Usar la primera línea con coupon_id negativo
                    discountLineToUse = negativeCouponLines[0];
                } else {
                    // Prioridad 2: Buscar líneas con coupon_id positivo
                    let positiveCouponLines = discountLines.filter(line =>
                        line.coupon_id && line.coupon_id > 0
                    );

                    if (positiveCouponLines.length > 0) {
                        // Usar la primera línea con coupon_id positivo
                        discountLineToUse = positiveCouponLines[0];
                    } else {
                        // Prioridad 3: Si no hay líneas con coupon_id, usar la primera que encontramos
                        discountLineToUse = discountLines[0];
                    }
                }
            }

            if (discountLineToUse) {
                normalLine.set_percent_discount(discountLineToUse.percent_discount);
            } else {
                normalLine.set_percent_discount(0);
            }
        }
    },

    async update_extra_info_lines() {
        let orderlines = this._get_normal_lines();

        let allLines = this.get_orderlines();

        for (let normalLine of orderlines) {
            let discountLine = allLines.find(line =>
                line.reward_prod_id &&
                line.reward_prod_id === normalLine.product.id &&
                line.price !== 0
            );

            if (discountLine) {
                normalLine.set_total_with_discount(normalLine.get_price_with_tax() + discountLine.get_price_with_tax());
            } else {
                normalLine.set_total_with_discount(0);
            }
        }
    },

    async update_amount_applied() {
        let allLines = this.get_orderlines();

        let rewardLines = allLines.filter(line => line.reward_prod_id);

        for (let rewardLine of rewardLines) {
            let productLine = allLines.find(line =>
                line.product.id === rewardLine.reward_prod_id &&
                !line.reward_prod_id
            );

            if (productLine) {

                let pointsPerUnit;
                let reward = this.pos.reward_by_id[rewardLine.reward_id]
                for (let ruleKey in reward?.program_id?.rules) {
                    let rule = reward.program_id.rules[ruleKey];
                    if (rule.reward_point_amount) {
                        pointsPerUnit = rule.reward_point_amount
                    }
                }
                let cost_reward_points = rewardLine.points_cost || 1

                let pointsUsed = rewardLine.quantity_applied * cost_reward_points;
                let amountApplied = pointsUsed / pointsPerUnit;

                rewardLine.set_amount_applied(amountApplied);
            }
        }
    },

    async discount_institutions_applicable(btn_inst) {
        if (btn_inst) {
            const vals_inst = btn_inst.state.selected
            if (vals_inst) {
                await btn_inst.loadInstitutionDetails(vals_inst)
            }
        }
    },

    async recreate_discount_lines() {

        //funcion para agregar promociones
        if (!this.partner) return;


        // instituciones para resetear precios
        const btn_inst = this.pos?.DeleteOrderLines
        if (btn_inst) {
            await btn_inst?.reset_prices()
        }

        let orderlines = this.get_orderlines()

        if (orderlines.some(line => line.quantity < 0)) return;


//        elimina promociones para recalcular
        const discount_lines = orderlines.filter(line => line.is_reward_line);
        discount_lines.forEach(line => this.orderlines.remove(line));


//        recalculo de puntos de odoo
        await this._updateLoyaltyPrograms()
        this.clear_all_discounts();


        // funcion para traer todas las promociones
        let potentialRewards = await this.pos._getPotentialRewardsCustom();


        //en caso de no haber solo actualiza
        if (potentialRewards === undefined || potentialRewards.length <= 0) {
            const orderLines = this.get_orderlines();

            for (const line of orderLines) {
                const product = line.get_product();
                await this.mergeAssociatedNormalLines(product);
            }

            this.clear_all_discounts();
            this.list_rewards_selected = [];

            await this.popupNotificationReward()
            await this.remove_coupons_general()
            await this.update_amount_applied()
            await this.update_extra_info_lines_discount()
            await this.prices_update_in_lines()
            await this.update_extra_info_lines()
            await this.discount_institutions_applicable(btn_inst)

            this._apply_daily_discount();


            return;
        }


        //ordenamiento de promociones segun su importancia
        potentialRewards = sortRewards(potentialRewards, this.list_rewards_selected);

        let arg = {}

//        merge de lineas
        const orderLines = this.get_orderlines();

        for (const line of orderLines) {
            const product = line.get_product();
            await this.mergeAssociatedNormalLines(product);
        }

        //aplicador de promociones
        for (let {coupon_id, reward, potentialQty, potentialQtySelect} of potentialRewards) {
            const loyaltyProgram = reward.program_id;

            //promociones obligatorias
            if (loyaltyProgram.mandatory_promotion && !loyaltyProgram.applies_to_the_second) {
                arg = {}

                const verifycate_type_coupon = await this.verifyExistingCouponMandatory(potentialRewards, reward)

                if (reward.reward_type === "discount" && !verifycate_type_coupon) {
                    arg["quantity"] = potentialQty
                } else {
                    arg["quantity"] = potentialQtySelect
                }
                await this._applyReward(reward, coupon_id, arg)

            } else if (loyaltyProgram.mandatory_promotion && loyaltyProgram.applies_to_the_second) {
                arg = {}

                const verifycate_type_coupon = await this.verifyExistingCouponMandatory(potentialRewards, reward)

                if (reward.reward_type === "discount" && !verifycate_type_coupon) {
                    arg["quantity"] = potentialQtySelect
                } else {
                    arg["quantity"] = potentialQtySelect
                }

                await this._applyReward(reward, coupon_id, arg)

            } else {

//                orderlines = this.get_orderlines()
//                const lines_reward = orderlines.filter(line =>
//                    (line.is_reward_line) && line.program_id === loyaltyProgram?.id
//                );

                arg = {}
                if (this.list_rewards_selected.includes(reward.id)) {
                    arg["is_selected"] = true
                }

                const verifycate_type_coupon = await this.verifyExistingCoupon(potentialRewards, reward)


                if (verifycate_type_coupon) {
                    arg["quantity"] = potentialQty
                } else {
                    arg["quantity"] = potentialQtySelect
                }
                arg["is_selectionable"] = true
                await this._applyReward(reward, coupon_id, arg)
            }

        }

        //borrado de promociones sin un producto asociado es decir solo existe la promocion pero no su producto activador

        const lines_reward = orderlines.filter(line =>
            line.is_part_of_reward || line.is_reward_line
        );

        if (lines_reward.length > 0) {
            const discount_lines = orderlines.filter(line =>
                    !line.is_part_of_reward && !line.is_reward_line && (
                        lines_reward.some(reward => reward.reward_prod_id === line.product.id)
                    )
            );
            if (discount_lines.length === 0) {
                lines_reward.forEach(line => this.orderlines.remove(line));
            }
        }


        //actuizado de datos extras
        await this.popupNotificationReward()
        await this.remove_coupons_general()
        await this.update_amount_applied()
        await this.update_extra_info_lines_discount()
        await this.prices_update_in_lines()
        await this.update_extra_info_lines()

        await this.discount_institutions_applicable(btn_inst)

        this._apply_daily_discount();
    },

    async verifyExistingCoupon(rewardsList, reward) {
        if (!reward?.program_id?.trigger_product_ids?.[0]) {
            return false;
        }

        const targetProductId = reward?.program_id?.trigger_product_ids[0];

        return rewardsList.some(rewardItem => {
            const item = rewardItem.reward;

            if (!item?.program_id) {
                return false;
            }

            const program = item.program_id;
            return (
                program.trigger === "with_code" &&
                program.applies_by_boxes !== true &&
                program.trigger_product_ids?.[0] === targetProductId
            );
        });
    },

    async verifyExistingCouponMandatory(rewardsList, reward) {
        if (!reward?.program_id?.trigger_product_ids?.[0]) {
            return false;
        }

        const targetProductId = reward?.program_id?.trigger_product_ids[0];

        return rewardsList.some(rewardItem => {
            const item = rewardItem.reward;

            if (!item?.program_id) {
                return false;
            }

            const program = item.program_id;
            return (
                program.trigger === "with_code" &&
                program.applies_by_boxes === true &&
                program.trigger_product_ids?.[0] === targetProductId
            );
        });
    },

    async remove_coupons_general() {
        try {
            const usedCoupons = this.get_orderlines()
                .filter(line => (line?.coupon_id > 0) || !!line?.cupon_alter)
                .map(line => line.cupon_alter ?? line.coupon_id);


            const updatePromises = this.codeActivatedCoupons.map(async (element) => {

                if (!usedCoupons.includes(element.id)) {
                    await this.env.services.orm.call(
                        'loyalty.card',
                        'mark_coupon_as_used',
                        [element.code, false]
                    );
                }

                this.codeActivatedCoupons = this.codeActivatedCoupons.filter(
                    item => usedCoupons.includes(item.id)
                );
            });

            await Promise.all(updatePromises);

        } catch (error) {
            console.error("Error in remove_coupons_general:", error);
            throw error;
        }
    },


    _getGlobalDiscountLines() {
        return this.get_orderlines().filter(
            (line) => this.pos.reward_by_id[line.reward_id] && this.pos.reward_by_id[line.reward_id].is_global_discount
        );
    },

    set_partner(partner) {
        const oldPartner = this.get_partner();
        super.set_partner(partner);
        const delete_orderlines = this.pos.DeleteOrderLines
        if (delete_orderlines) {
            delete_orderlines.loadInstitutions()
            delete_orderlines.reset_prices()
        }

        if (this.couponPointChanges && oldPartner !== this.get_partner()) {
            // Remove couponPointChanges for cards in is_nominative programs.
            // This makes sure that counting of points on loyalty and ewallet programs is updated after partner changes.
            const loyaltyProgramIds = new Set(
                this.pos.programs
                    .filter((program) => program?.is_nominative)
                    .map((program) => program.id)
            );
            for (const [key, pointChange] of Object.entries(this.couponPointChanges)) {
                if (loyaltyProgramIds.has(pointChange.program_id)) {
                    delete this.couponPointChanges[key];
                }
            }
            this._delete_all_lines_reward()
        }
    },

    async _delete_all_lines_reward() {
        const orderlines = this.orderlines
        const rewardLines = orderlines.filter(line => line.is_part_of_reward || line.is_reward_line);
        rewardLines.forEach(line => orderlines.remove(line));
        await this.remove_coupons_general()
    },

    getClaimableRewards(coupon_id = false, program_id = false, auto = false) {
        const allCouponPrograms = Object.values(this.couponPointChanges)
            .map((pe) => {
                return {
                    program_id: pe.program_id,
                    coupon_id: pe.coupon_id,
                };
            })
            .concat(
                this.codeActivatedCoupons.map((coupon) => {
                    return {
                        program_id: coupon.program_id,
                        coupon_id: coupon.id,
                    };
                })
            );
        const result = [];
        const totalWithTax = this.get_total_with_tax();
        const totalWithoutTax = this.get_total_without_tax();
        const totalIsZero = totalWithTax === 0;
        const globalDiscountLines = this._getGlobalDiscountLines();
        const globalDiscountPercent = globalDiscountLines.length
            ? this.pos.reward_by_id[globalDiscountLines[0].reward_id].discount
            : 0;
        for (const couponProgram of allCouponPrograms) {
            const program = this.pos.program_by_id[couponProgram.program_id];
            if (program === undefined) {
                continue;
            }
            if (
                program.pricelist_ids.length > 0 &&
                (!this.pricelist || !program.pricelist_ids.includes(this.pricelist.id))
            ) {
                continue;
            }
            if (program.trigger == "with_code") {
                // For coupon programs, the rules become conditions.
                // Points to purchase rewards will only come from the scanned coupon.
                if (!this._canGenerateRewards(program, totalWithTax, totalWithoutTax)) {
                    continue;
                }
            }
            if (
                (coupon_id && couponProgram.coupon_id !== coupon_id) ||
                (program_id && couponProgram.program_id !== program_id)
            ) {
                continue;
            }
            const points = this._getRealCouponPoints(couponProgram.coupon_id);
            for (const reward of program.rewards) {
                if (points < reward.required_points) {
                    continue;
                }
                if (auto && this.disabledRewards.has(reward.id)) {
                    continue;
                }
                // Try to filter out rewards that will not be claimable anyway.
                if (reward && reward.is_global_discount && reward.discount <= globalDiscountPercent) {
                    continue;
                }
                if (reward.reward_type === "discount" && totalIsZero) {
                    continue;
                }
                let unclaimedQty;
                if (reward.reward_type === "product") {
                    if (!reward.multi_product) {
                        const product = this.pos.db.get_product_by_id(reward.reward_product_ids[0]);
                        if (!product) {
                            continue;
                        }

                        unclaimedQty = this._computeUnclaimedFreeProductQty(
                            reward,
                            couponProgram.coupon_id,
                            product,
                            points
                        );
                    }
                    if (!unclaimedQty || unclaimedQty <= 0) {
                        continue;
                    }
                }
                result.push({
                    coupon_id: couponProgram.coupon_id,
                    reward: reward,
                    potentialQty: unclaimedQty,
                });
            }
        }
        return result;
    },

    getClaimableRewardsCustom(coupon_id = false, program_id = false, auto = false) {
        const allCouponPrograms = Object.values(this.couponPointChanges)
            .map((pe) => {
                return {
                    program_id: pe.program_id,
                    coupon_id: pe.coupon_id,
                };
            })
            .concat(
                this.codeActivatedCoupons.map((coupon) => {
                    return {
                        program_id: coupon.program_id,
                        coupon_id: coupon.id,
                    };
                })
            );
        const result = [];
        const totalWithTax = this.get_total_with_tax();
        const totalWithoutTax = this.get_total_without_tax();
        const totalIsZero = totalWithTax === 0;
        const globalDiscountLines = this._getGlobalDiscountLines();
        const globalDiscountPercent = globalDiscountLines.length
            ? this.pos.reward_by_id[globalDiscountLines[0].reward_id].discount
            : 0;

//        const validPrograms = Object.fromEntries(
//            allCouponPrograms
//                .map(cp => [cp.program_id, this.pos.program_by_id[cp.program_id]])
//                .filter(([id, program]) => program !== undefined)
//        );
        const validPrograms = allCouponPrograms
            .map(cp => this.pos.program_by_id[cp.program_id])
            .filter(program => program !== undefined);

        for (const couponProgram of allCouponPrograms) {
            const program = this.pos.program_by_id[couponProgram.program_id];

            if (program === undefined) {
                continue;
            }
            if (
                program.pricelist_ids.length > 0 &&
                (!this.pricelist || !program.pricelist_ids.includes(this.pricelist.id))
            ) {
                continue;
            }
            if (program.trigger == "with_code") {
                // For coupon programs, the rules become conditions.
                // Points to purchase rewards will only come from the scanned coupon.
                if (!this._canGenerateRewards(program, totalWithTax, totalWithoutTax)) {
                    continue;
                }
            }
            if (
                (coupon_id && couponProgram.coupon_id !== coupon_id) ||
                (program_id && couponProgram.program_id !== program_id)
            ) {
                continue;
            }
            const points = this._getRealCouponPoints(couponProgram.coupon_id);

            let point_program = {}

            const findGroup = createRewardsFinder(validPrograms);

            for (const reward of program.rewards) {

                if (points < reward.required_points) {
                    continue;
                }
                if (auto && this.disabledRewards.has(reward.id)) {
                    continue;
                }
                // Try to filter out rewards that will not be claimable anyway.
                if (reward && reward.is_global_discount && reward.discount <= globalDiscountPercent) {
                    continue;
                }

                if (reward?.reward_type === "discount" && totalIsZero) {
                    continue;
                }
                let unclaimedQty;
                let quanty;


                if (!reward.multi_product) {
                    let product = this.pos.db.get_product_by_id(reward.reward_product_ids[0]);


                    if (!product) {
                        product = this.pos.db.get_product_by_id(reward.discount_product_ids[0]);
                    }

                    if (!product) {
                        product = this.pos.db.get_product_by_id(reward.discount_line_product_id.id);
                    }

                    if (!product) {
                        continue
                    }

                    const group = findGroup(program);

                    [unclaimedQty, quanty] = this._computeUnclaimedFreeProductQtyCustom(
                        reward,
                        couponProgram.coupon_id,
                        product,
                        points,
                        group
                    );


                    if (!unclaimedQty || unclaimedQty <= 0) {
                        continue;
                    }

                    result.push({
                        coupon_id: couponProgram.coupon_id,
                        reward: reward,
                        potentialQty: unclaimedQty,
                        quantityProduct: quanty,
                        potentialQtySelect: unclaimedQty
                    });
                }
            }
        }

        return result;
    },

    async _search_limit_for_reward(productId, reward, partnerId) {
        try {
            const result = await this.env.services.orm.call(
                'loyalty.reward',
                'check_promotion_limit',
                [partnerId, productId, reward]
            );
            if (result) {
                return {
                    limit: result.limit,
                    limit_items: result.limit_items,
                    limit_local: result.limit_local,
                    unlimited: result.unlimited
                };

            } else {
                return {limit: 0, limit_items: 0, limit_local: 0, unlimited: false};
            }
        } catch (error) {
            console.error("Error al llamar a check_promotion_limit:", error);
        }
    },

    async _updatePrograms() {
        const changesPerProgram = {};
        const programsToCheck = new Set();
        // By default include all programs that are considered 'applicable'
        for (const program of this.pos.programs) {
            if (this._programIsApplicable(program)) {
                programsToCheck.add(program.id);
            }
        }
        for (const pe of Object.values(this.couponPointChanges)) {
            if (!changesPerProgram[pe.program_id]) {
                changesPerProgram[pe.program_id] = [];
                programsToCheck.add(pe.program_id);
            }
            changesPerProgram[pe.program_id].push(pe);
        }
        for (const coupon of this.codeActivatedCoupons) {
            programsToCheck.add(coupon.program_id);
        }
        const programs = [...programsToCheck].map((programId) => this.pos.program_by_id[programId]);
        const pointsAddedPerProgram = this.pointsForPrograms(programs);
        for (const program of this.pos.programs) {
            // Future programs may split their points per unit paid (gift cards for example), consider a non applicable program to give no points
            const pointsAdded = this._programIsApplicable(program)
                ? pointsAddedPerProgram[program.id]
                : [];
            // For programs that apply to both (loyalty) we always add a change of 0 points, if there is none, since it makes it easier to
            //  track for claimable rewards, and makes sure to load the partner's loyalty card.
            if (program?.is_nominative && !pointsAdded.length && this.get_partner()) {
                pointsAdded.push({points: 0});
            }
            const oldChanges = changesPerProgram[program.id] || [];
            // Update point changes for those that exist
            for (let idx = 0; idx < Math.min(pointsAdded.length, oldChanges.length); idx++) {
                Object.assign(oldChanges[idx], pointsAdded[idx]);
            }
            if (pointsAdded.length < oldChanges.length) {
                const removedIds = oldChanges.map((pe) => pe.coupon_id);
                this.couponPointChanges = Object.fromEntries(
                    Object.entries(this.couponPointChanges).filter(([k, pe]) => {
                        return !removedIds.includes(pe.coupon_id);
                    })
                );
            } else if (pointsAdded.length > oldChanges.length) {
                for (const pa of pointsAdded.splice(oldChanges.length)) {
                    const coupon = await this._couponForProgram(program);
                    this.couponPointChanges[coupon.id] = {
                        points: pa.points,
                        program_id: program.id,
                        coupon_id: coupon.id,
                        barcode: pa.barcode,
                        appliedRules: pointsForProgramsCountedRules[program.id],
                        giftCardId: pa.giftCardId
                    };
                }
            }
        }
        // Also remove coupons from codeActivatedCoupons if their program applies_on current orders and the program does not give any points
        this.codeActivatedCoupons = this.codeActivatedCoupons.filter((coupon) => {
            const program = this.pos.program_by_id[coupon.program_id];
            if (
                program &&
                program.applies_on === "current" &&
                pointsAddedPerProgram[program.id].length === 0
            ) {
                return false;
            }
            return true;
        });
    },

    pointsForPrograms(programs) {
        let filteredPrograms = programs; // Mantener el arreglo original por defecto

        if (programs && programs.length >= 2) {
            programs = programs.filter(item => item !== undefined);
        }

        if (!filteredPrograms || filteredPrograms.length <= 0 || (filteredPrograms.length === 1 && filteredPrograms[0] === undefined)) {
            return {};
        }

        pointsForProgramsCountedRules = {};
        const orderLines = this.get_orderlines();
        const linesPerRule = {};
        for (const line of orderLines) {
            const reward = line.reward_id ? this.pos.reward_by_id[line.reward_id] : undefined;
            const isDiscount = reward && reward.reward_type === "discount";
            const rewardProgram = reward && reward.program_id;
            // Skip lines for automatic discounts.
            if (isDiscount && rewardProgram.trigger === "auto") {
                continue;
            }
            for (const program of programs) {
                // Skip lines for the current program's discounts.
                if (isDiscount && rewardProgram.id === program.id) {
                    continue;
                }
                for (const rule of program.rules) {
                    // Skip lines to which the rule doesn't apply.
                    if (rule.any_product || rule.valid_product_ids.has(line.get_product().id)) {
                        if (!linesPerRule[rule.id]) {
                            linesPerRule[rule.id] = [];
                        }
                        linesPerRule[rule.id].push(line);
                    }
                }
            }
        }
        const result = {};
        for (const program of programs) {
            let points = 0;
            const splitPoints = [];
            for (const rule of program.rules) {
                if (
                    rule.mode === "with_code" &&
                    !this.codeActivatedProgramRules.includes(rule.id)
                ) {
                    continue;
                }
                const linesForRule = linesPerRule[rule.id] ? linesPerRule[rule.id] : [];
                const amountWithTax = linesForRule.reduce(
                    (sum, line) => sum + line.get_price_with_tax(),
                    0
                );
                const amountWithoutTax = linesForRule.reduce(
                    (sum, line) => sum + line.get_price_without_tax(),
                    0
                );
                const amountCheck =
                    (rule.minimum_amount_tax_mode === "incl" && amountWithTax) || amountWithoutTax;
                if (rule.minimum_amount > amountCheck) {
                    continue;
                }
                let totalProductQty = 0;
                // Only count points for paid lines.
                const qtyPerProduct = {};
                let orderedProductPaid = 0;
                for (const line of orderLines) {
                    if (
                        ((!line.reward_product_id &&
                                (rule.any_product ||
                                    rule.valid_product_ids.has(line.get_product().id))) ||
                            (line.reward_product_id &&
                                (rule.any_product ||
                                    rule.valid_product_ids.has(line.reward_product_id)))) &&
                        !line.ignoreLoyaltyPoints({program})
                    ) {
                        // We only count reward products from the same program to avoid unwanted feedback loops
                        if (line.is_reward_line) {
                            const reward = this.pos.reward_by_id[line.reward_id];
                            if ((program.id === reward?.program_id?.id) || ['gift_card', 'ewallet'].includes(reward?.program_id?.program_type)) {
                                continue;
                            }
                        }
                        const lineQty = line.reward_product_id
                            ? -line.get_quantity()
                            : line.get_quantity();
                        if (qtyPerProduct[line.reward_product_id || line.get_product().id]) {
                            qtyPerProduct[line.reward_product_id || line.get_product().id] +=
                                lineQty;
                        } else {
                            qtyPerProduct[line.reward_product_id || line.get_product().id] =
                                lineQty;
                        }
                        orderedProductPaid += line.get_price_with_tax();
                        if (!line.is_reward_line) {
                            totalProductQty += lineQty;
                        }
                    }
                }
                if (totalProductQty < rule.minimum_qty) {
                    // Should also count the points from negative quantities.
                    // For example, when refunding an ewallet payment. See TicketScreen override in this addon.
                    continue;
                }
                if (!(program.id in pointsForProgramsCountedRules)) {
                    pointsForProgramsCountedRules[program.id] = [];
                }
                pointsForProgramsCountedRules[program.id].push(rule.id);
                if (
                    program.applies_on === "future" &&
                    rule.reward_point_split &&
                    rule.reward_point_mode !== "order"
                ) {
                    // In this case we count the points per rule
                    if (rule.reward_point_mode === "unit") {
                        splitPoints.push(
                            ...Array.apply(null, Array(totalProductQty)).map((_) => {
                                return {points: rule.reward_point_amount};
                            })
                        );
                    } else if (rule.reward_point_mode === "money") {
                        for (const line of orderLines) {
                            if (
                                line.is_reward_line ||
                                !rule.valid_product_ids.has(line.get_product().id) ||
                                line.get_quantity() <= 0 ||
                                line.ignoreLoyaltyPoints({program})
                            ) {
                                continue;
                            }
                            const pointsPerUnit = roundPrecision(
                                (rule.reward_point_amount * line.get_price_with_tax()) /
                                line.get_quantity(),
                                0.01
                            );
                            if (pointsPerUnit > 0) {
                                splitPoints.push(
                                    ...Array.apply(null, Array(line.get_quantity())).map(() => {
                                        if (line.giftBarcode && line.get_quantity() == 1) {
                                            return {
                                                points: pointsPerUnit,
                                                barcode: line.giftBarcode,
                                                giftCardId: line.giftCardId,
                                            };
                                        }
                                        return {points: pointsPerUnit};
                                    })
                                );
                            }
                        }
                    }
                } else {
                    // In this case we add on to the global point count
                    if (rule.reward_point_mode === "order") {
                        points += rule.reward_point_amount;
                    } else if (rule.reward_point_mode === "money") {
                        // NOTE: unlike in sale_loyalty this performs a round half-up instead of round down
                        points += roundPrecision(
                            rule.reward_point_amount * orderedProductPaid,
                            0.01
                        );
                    } else if (rule.reward_point_mode === "unit") {
                        points += rule.reward_point_amount * totalProductQty;
                    }
                }
            }
            const res = points || program.program_type === "coupons" ? [{points}] : [];
            if (splitPoints.length) {
                res.push(...splitPoints);
            }
            result[program.id] = res;
        }
        return result;
    },

    async _resetProgramsSelectionable(line) {

        //borra todas las otras promociones, asociadas al mismo pograma exepcto la de descunto por que se borra el producto activador

        const orderlines = this.get_orderlines()

        const lines_to_remove = orderlines.filter(line_to_remove => line_to_remove.is_reward_line && line_to_remove.program_id == line.program_id);
        lines_to_remove.forEach(line => this.orderlines.remove(line));
    },


    async _resetPrograms() {
        this.disabledRewards = new Set();
        this.codeActivatedProgramRules = [];
        this.codeActivatedCoupons = [];
        this.couponPointChanges = {};
        this.list_rewards_selected = [];
        const orderlines = this.get_orderlines()
        const selected_rewards = orderlines.filter(line => line.is_reward_line && line.is_selected);
        this.list_rewards_selected = selected_rewards.map(line => line.reward_id);
        const rewardLines = orderlines.filter(line => line.is_part_of_reward || line.is_reward_line);
//        const new_list = this._options_for_reward(rewardLines)
        new_list.forEach(line => this.orderlines.remove(line));
        if (new_list.length > 0) {
            await this._updateRewards(false, true);
        }
    },

    _computeUnclaimedFreeProductQtyCustom(reward, coupon_id, product, remainingPoints, potentialRewards) {
        let claimed = 0;
        let available = product.type === "service" ? 1 : 0;

        let shouldCorrectRemainingPoints = false;
        for (const line of this.get_orderlines()) {

            if (reward.reward_product_ids.includes(product.id) && reward.reward_product_ids.includes(line.product.id) ||
                reward.discount_product_ids.includes(product.id) && reward.discount_product_ids.includes(line.product.id)) {
                if (this._get_reward_lines() === 0) {
                    if (line.get_product().id === product.id) {
                        available += line.get_quantity();
                    }
                } else {
                    available += line.get_quantity();
                }
            } else if (reward.reward_product_ids.includes(line.reward_product_id)) {
                if (line.reward_id === reward.id) {
                    remainingPoints += line.points_cost;
                    claimed += line.get_quantity();
                } else {
                    shouldCorrectRemainingPoints = true;
                }
            }
        }

        let freeQty;

        if (reward.program_id.trigger === "auto") {

            if (
                product?.id &&
                reward &&
                this._isRewardProductPartOfRules(reward, product) &&
                reward.program_id.applies_on !== "future"
            ) {

                // OPTIMIZATION: Pre-calculate the factors for each reward-product combination during the loading.
                // For points not based on quantity, need to normalize the points to compute free quantity.
                const appliedRulesIds = this.couponPointChanges[coupon_id].appliedRules;
                const appliedRules =
                    appliedRulesIds !== undefined
                        ? reward.program_id.rules.filter((rule) =>
                            appliedRulesIds.includes(rule.id)
                        )
                        : reward.program_id.rules;
                let factor = 0;
                let orderPoints = 0;
                for (const rule of appliedRules) {
                    if (rule.any_product || rule.valid_product_ids.has(product.id)) {
                        if (rule.reward_point_mode === "order") {
                            orderPoints += rule.reward_point_amount;
                        } else if (rule.reward_point_mode === "money") {
                            factor += roundPrecision(
                                rule.reward_point_amount * product.lst_price,
                                0.01
                            );
                        } else if (rule.reward_point_mode === "unit") {
                            factor += rule.reward_point_amount;
                        }
                    }
                }
                if (factor === 0) {
                    freeQty = Math.floor(
                        (remainingPoints / reward.required_points) * reward.reward_product_qty
                    );
                } else {
                    const point_distrib = distributePointsWithPrograms(remainingPoints, potentialRewards, this.list_rewards_selected, this.get_orderlines())

                    if (point_distrib?.distribution[reward.id] !== undefined) {
                        freeQty = (point_distrib.distribution[reward.id])
                    } else {
                        freeQty = Math.floor(
                            (remainingPoints / reward.required_points) * reward.reward_product_qty
                        );
                    }

                    if (reward?.program_id?.applies_by_boxes && reward.is_main) {
                        let maxBoxes = reward?.program_id?.max_boxes_limit || 0; // 0 = sin límite
                        let calculatedBoxes = freeQty;

                        if (maxBoxes > 0) {
                            calculatedBoxes = Math.min(freeQty, maxBoxes);
                        }
                        freeQty = calculatedBoxes * product?.uom_po_factor_inv;
                    }

                }

            } else {
                if ((reward?.program_id?.mandatory_promotion)) {

                    const point_distrib = distributePointsWithPrograms(remainingPoints, potentialRewards, this.list_rewards_selected, this.get_orderlines())
                    if (point_distrib?.distribution[reward.id] !== undefined) {
                        freeQty = (point_distrib.distribution[reward.id]) * reward.reward_product_qty
                    } else {
                        freeQty = Math.floor(
                            (remainingPoints / reward.required_points) * reward.reward_product_qty
                        );
                    }
                } else {
                    freeQty = Math.floor(
                        (remainingPoints / reward.required_points) * reward.reward_product_qty
                    );
                }

            }
        } else if (reward.program_id.trigger === "with_code") {

            if (reward?.program_id?.applies_by_boxes) {
                let maxBoxes = reward?.program_id?.max_boxes_limit || 0; // 0 = sin límite
                let calculatedBoxes;

                if (available % product?.uom_po_factor_inv === 0) {
                    calculatedBoxes = Math.floor(available);
                } else {
                    calculatedBoxes = Math.floor(available / product.uom_po_factor_inv);
                }

                if (maxBoxes > 0) {
                    calculatedBoxes = Math.min(calculatedBoxes, maxBoxes);
                }

                freeQty = calculatedBoxes * product?.uom_po_factor_inv;
            } else {
                freeQty = Math.floor(
                    (remainingPoints / reward.required_points) * reward.reward_product_qty
                );
            }
        }

        let original = Math.min(available, freeQty) - claimed

        let custom = freeQty - Math.min(available, freeQty)
        return [original, custom];
    },


    async _updateRewards(action = false, fetch = false) {

        /// Funcion principal para detectar movimientos en el pos como aumentar cantidad, agregar produto, etc
        try {
            if (!fetch) {
                const orderlines = this.get_orderlines();
                const productIds = [...new Set(orderlines.map(line => line.product.id))].filter(Boolean);
                await fetchDataPromotionsDebouncer(() => this.loadCustomLoyaltyData(productIds));
            }

        } catch (error) {
            console.error("Error al procesar líneas de pedido:", error);
        }
        // Calls are not expected to take some time besides on the first load + when loyalty programs are made applicable
        if (this.pos.programs.length === 0) {
            if (action) {
                recreateDiscountLinesDebouncer(() => this.recreate_discount_lines());
                this.invalidCoupons = true;
            }
            return;
        }

        updateRewardsMutex.exec(() => {
            return this._updateLoyaltyPrograms().then(async () => {
                // Try auto claiming rewards
                const claimableRewards = this.getClaimableRewards(false, false, true);
                let changed = false;

                // Rewards may impact the number of points gained
                if (changed) {
                    await this._updateLoyaltyPrograms();
                }
                if (action) {
                    recreateDiscountLinesDebouncer(() => this.recreate_discount_lines());
                    this.invalidCoupons = true;
                }
            });
        });
    },

    _mergeLoyaltyData(existingData, newData) {
        const mergedData = [...existingData]; // Copia los datos existentes

        for (const item of newData) {
            // Evitar duplicados comprobando el campo `id`
            if (!mergedData.some(existingItem => existingItem.id === item.id)) {
                mergedData.push(item);
            }
        }
        return mergedData;
    },


    async loadCustomLoyaltyData(product_ids) {
        try {
            const env = this?.env;
            if (!env) {
                return;
            }
            if (!env.services.pos || !env.services.pos.config || !env.services.pos.config.id) {
                return;
            }

            // Consulta de programas de lealtad por productos específicos
            const response = await fetch("/pos/loyalty_data", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({
                    product_ids: product_ids,
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const loyaltyData = await response.json();

            // Consulta de cupones generales (sin productos específicos)
            const couponsResponse = await fetch("/pos/general_coupons", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({}),
            });


            let couponsData = {result: {}};
            if (couponsResponse.ok) {
                couponsData = await couponsResponse.json();
                if (couponsData.error) {
                    console.warn("Cupones generales no disponibles:", couponsData.error);
                    couponsData = {result: {}};
                }
            }

            // Verificar errores del backend principal
            if (loyaltyData.error) {
                console.error("Error from backend:", loyaltyData.error);
                env.services.pos.selectedOrder._updateRewards(true, true);
                return;
            }

            // Inicializar cache
            env.services.pos.couponCache = {};
            env.services.pos.partnerId2CouponIds = {};

            // Función auxiliar para eliminar duplicados por ID
            const removeDuplicates = (array, key = 'id') => {
                const seen = new Set();
                return array.filter(item => {
                    const id = item[key];
                    if (seen.has(id)) return false;
                    seen.add(id);
                    return true;
                });
            };

            // Fusionar datos de lealtad con cupones generales y eliminar duplicados
            env.services.pos.rewards = removeDuplicates([
                ...(loyaltyData.result.loyalty_reward || []),
                ...(couponsData.result?.loyalty_reward || [])
            ]);

            env.services.pos.programs = removeDuplicates([
                ...(loyaltyData.result.loyalty_program || []),
                ...(couponsData.result?.loyalty_program || [])
            ]);

            env.services.pos.rules = removeDuplicates([
                ...(loyaltyData.result.loyalty_rule || []),
                ...(couponsData.result?.loyalty_rule || [])
            ]);

            // Fusionar productos de recompensa
            const mergedRewardProducts = removeDuplicates([
                ...(loyaltyData.result.reward_products || []),
                ...(couponsData.result?.reward_products || [])
            ]);

            // Verificar si hay reglas disponibles
            if (!env.services.pos.rules || env.services.pos.rules.length === 0) {
                env.services.pos.selectedOrder._updateRewards(true, true);
                return;
            }

            // Procesar recompensas
            for (const reward of env.services.pos.rewards) {
                reward.all_discount_product_ids = new Set(reward.all_discount_product_ids);
            }

            // Cargar productos de recompensa fusionados
            await env.services.pos._loadLoyaltyData(mergedRewardProducts);

            // Actualizar recompensas
            env.services.pos.selectedOrder._updateRewards(true, true);

        } catch (error) {
            console.error("Error loading custom loyalty data:", error);
            const env = this?.env;
            if (!env) {
                return;
            }
            env.services.pos.selectedOrder._updateRewards(true, true);
        }
    },

    _programIsApplicable(program) {
        if (
            program &&
            program.trigger === "auto" &&
            !program.rules.find(
                (rule) => rule.mode === "auto" || this.codeActivatedProgramRules.includes(rule.id)
            )
        ) {
            return false;
        }
        if (
            program.trigger === "with_code" &&
            !program.rules.find((rule) => this.codeActivatedProgramRules.includes(rule.id))
        ) {
            return false;
        }
        if (program?.is_nominative && !this.get_partner()) {
            return false;
        }
//        if (program?.date_from && program?.date_from?.startOf("day") > DateTime.now()) {
//            return false;
//        }
//        if (program?.date_to && program?.date_to?.endOf("day") < DateTime.now()) {
//            return false;
//        }
        if (program?.limit_usage && program?.total_order_count >= program?.max_usage) {
            return false;
        }
        if (
            program?.pricelist_ids?.length > 0 &&
            (!this.pricelist || !program?.pricelist_ids.includes(this.pricelist.id))
        ) {
            return false;
        }
        return true;
    },


    _getRewardLineValuesProduct(args) {
        const reward = args["reward"];
        const product = this.pos.db.get_product_by_id(
            args["product"] || reward.reward_product_ids[0]
        );
        const points = this._getRealCouponPoints(args["coupon_id"]);
        let unclaimedQty = 1
        const claimable_count = reward.clear_wallet
            ? 1
            : Math.min(
                Math.ceil(unclaimedQty / reward.reward_product_qty),
                Math.floor(points / reward.required_points)
            );
        const cost = reward.clear_wallet ? points : claimable_count * reward.required_points;
        // In case the reward is the product multiple times, give it as many times as possible
        const freeQuantity = Math.min(unclaimedQty, reward.reward_product_qty * claimable_count);

        const weekdayPct = Number(this.pos?.getWeekdayPromoPercent?.() || 0);
        let finalDiscountPct = 0;

        const order = this;
        const existingLine = order.get_orderlines?.().find((l) => {
            const pid = l.get_product?.().id;
            return pid === product.id && !l.is_reward_line;
        });

        if (weekdayPct > 0) {
            if (existingLine) {
                finalDiscountPct = Math.max(Number(existingLine.discount || existingLine.percent_discount || 0), weekdayPct);
                console.log("final discount", finalDiscountPct);
            } else {
                finalDiscountPct = weekdayPct;
                console.log("final discount2: ", finalDiscountPct);
            }
        }

        console.log(finalDiscountPct);
        console.log("estoy con la existingline", existingLine);

        if (existingLine && finalDiscountPct > 0) {
            existingLine.set_discount(finalDiscountPct);
            existingLine.discount_reason = `Descuento combinado (${existingLine.discount}% + ${weekdayPct}%)`;
            existingLine.is_promo_line = true;
            existingLine.percent_discount = finalDiscountPct;

            console.log("final discount TEST", existingLine.percent_discount);
        }

        const price = 0;

        return [
            {
                product: reward.discount_line_product_id,
                price: product.lst_price,
                tax_ids: product.taxes_id,
                discount: 100,
                quantity: args["quantity"] || freeQuantity,
                quantity_applied: args["quantity"] || freeQuantity,
                reward_id: reward.id,
                program_id: reward.program_id.id,
                is_reward_line: true,
                reward_with_code: reward.program_id.trigger,
                reward_product_id: product.id,
                reward_prod_id: reward.program_id.trigger_product_ids[0],
                coupon_id: args["coupon_id"],
                points_cost: args["cost"] || cost,
                reward_identifier_code: _newRandomRewardCode(),
                merge: false,
                is_selected: args["is_selected"] || false,
                is_selectionable: args["is_selectionable"] || false,
                discount_reason: finalDiscountPct > 0
                    ? (existingLine
                        ? `Descuento combinado (${existingLine.discount}% + ${weekdayPct}%)`
                        : `Descuento del día (${weekdayPct}%)`)
                    : undefined,
                percent_discount: finalDiscountPct,
            },
        ];
    },


    _getRewardLineValuesDiscount(args) {
        const reward = args["reward"];
        const coupon_id = args["coupon_id"];
        reward.quantity = args["quantity"];
        const rewardAppliesTo = reward.discount_applicability;
        let getDiscountable;
        if (rewardAppliesTo === "order") {
            getDiscountable = this._getDiscountableOnOrder.bind(this);
        } else if (rewardAppliesTo === "cheapest") {
            getDiscountable = this._getDiscountableOnCheapest?.bind(this);
        } else if (rewardAppliesTo === "specific") {
            getDiscountable = this._getDiscountableOnSpecific?.bind(this);
        }
        if (!getDiscountable) {
            return _t("Unknown discount type");
        }
        let {discountable, discountablePerTax, quanty} = getDiscountable(reward);

        discountable = Math.min(this.get_total_with_tax(), discountable);
        if (!discountable) {
            return [];
        }

        const weekdayPct = Number(this.pos?.getWeekdayPromoPercent?.() || 0);

        const baseRewardPct = Number(reward.discount || 0);

        const suppressDiscountSecondProduct =
            (reward?.is_main === true) &&
            (reward?.program_id?.applies_to_the_second === true);

        const addWeekdayPct = suppressDiscountSecondProduct ? 0 : weekdayPct;

        const effectivePercent = Math.max(0, Math.min(100, baseRewardPct + addWeekdayPct));

        const roundedEffectivePercent = round_pr(effectivePercent, 0.01);

        let maxDiscount = reward.discount_max_amount || Infinity;
        if (reward.discount_mode === "per_point") {
            // Rewards cannot be partially offered to customers
            const points = (["ewallet", "gift_card"].includes(reward.program_id.program_type)) ?
                this._getRealCouponPoints(coupon_id) :
                Math.floor(this._getRealCouponPoints(coupon_id) / reward.required_points) * reward.required_points;
            maxDiscount = Math.min(
                maxDiscount,
                reward.discount * points
            );

        } else if (reward.discount_mode === "per_order") {
            maxDiscount = Math.min(maxDiscount, reward.discount);

        } else if (reward.discount_mode === "percent") {
            maxDiscount = Math.min(maxDiscount, discountable * (roundedEffectivePercent / 100));
        }

        const rewardCode = (typeof window._newRandomRewardCode === "function")
            ? window._newRandomRewardCode()
            : Math.random().toString(36).slice(2, 10);

        let pointCost = reward.clear_wallet
            ? this._getRealCouponPoints?.(coupon_id)
            : reward.required_points;
        if (reward.discount_mode === "per_point" && !reward.clear_wallet) {
            pointCost = Math.min(maxDiscount, discountable) / reward.discount;
        }

        // These are considered payments and do not require to be either taxed or split by tax
        const discountProduct = reward.discount_line_product_id;
        const targetProdId = reward.reward_product_ids?.[0] || reward.program_id.trigger_product_ids?.[0];
        const targetProd = this.pos.db.get_product_by_id(targetProdId);
        const baseName = targetProd ? targetProd.display_name : (reward.name || _t("Producto"));
        const label = `${roundedEffectivePercent}% en ${baseName}`;  // Use rounded for clean display (e.g., 49%)

        if (["ewallet", "gift_card"].includes(reward.program_id.program_type)) {
            const taxes_to_apply = discountProduct.taxes_id.map((id) => {
                return {...this.pos.taxes_by_id[id], price_include: true};
            });
            const tax_res = this.pos.compute_all(
                taxes_to_apply,
                -Math.min(maxDiscount, discountable),
                1,
                this.pos.currency.rounding
            );
            let new_price = tax_res["total_excluded"];
            new_price += tax_res.taxes
                .filter((tax) => this.pos.taxes_by_id[tax.id].price_include)
                .reduce((sum, tax) => (sum += tax.amount), 0);

            return [{
                product: discountProduct,
                price: new_price,
                quantity_applied: args["quantity"],
                quantity: 1,
                reward_id: reward.id,
                reward_product_id: reward.reward_product_ids[0],
                reward_prod_id: reward.program_id.trigger_product_ids[0],
                percent_discount: (reward.discount_mode === "percent") ? roundedEffectivePercent : reward.discount,
                is_reward_line: true,
                reward_with_code: reward.program_id.trigger,
                program_id: reward.program_id.id,
                coupon_id: coupon_id,
                points_cost: pointCost,
                reward_identifier_code: "WD-" + rewardCode, // marca weekday
                merge: false,
                taxIds: discountProduct.taxes_id,
                is_selected: args["is_selected"] || false,
                is_selectionable: args["is_selectionable"] || false,

                // 👇 añade ambos campos de nombre:
                name: label,
                full_product_name: label,
            }];
        }
        const discountFactor = discountable ? Math.min(1, maxDiscount / discountable) : 1;
        const result = Object.entries(discountablePerTax).reduce((lst, entry) => {
            if (!entry[1]) return lst;
            const taxIds = entry[0] === "" ? [] : entry[0].split(",").map((str) => parseInt(str));
            lst.push({
                product: discountProduct,
                price: -(entry[1] * discountFactor),
                quantity_applied: args["quantity"],
                quantity: 1,
                program_id: reward.program_id.id,
                reward_prod_id: reward.program_id.trigger_product_ids[0],
                reward_type: "discount",
                percent_discount: (reward.discount_mode === "percent") ? roundedEffectivePercent : reward.discount,
                reward_id: reward.id,
                reward_product_id: reward.program_id.trigger_product_ids[0],
                is_reward_line: true,
                reward_with_code: reward.program_id.trigger,
                coupon_id: coupon_id,
                points_cost: 0,
                reward_identifier_code: "WD-" + rewardCode, // marca weekday
                tax_ids: taxIds,
                merge: false,
                is_selected: args["is_selected"] || false,
                is_selectionable: args["is_selectionable"] || false,

                name: label,
                full_product_name: label,
            });
            return lst;
        }, []);
        if (result.length) {
            result[0]["points_cost"] = pointCost;
        }

        return result;
    },

    _getDiscountableOnSpecific(reward) {
        const applicableProducts = reward.all_discount_product_ids;
        const linesToDiscount = [];
        const discountLinesPerReward = {};
        const orderLines = this.get_orderlines();
        const remainingAmountPerLine = {};
        for (const line of orderLines) {
            if (!line.get_quantity() || !line.price || line.is_reward_line) {
                continue;
            }

            let value_of_line_total = line.get_price_with_tax()
//            let value_of_line_total = line.get_price_with_tax_custom().price_with_tax
            let limit_for_order = line.get_price_with_tax()

            if (reward.limit_for_order !== 0 && (applicableProducts.has(line.get_product().id) ||
                (line.reward_product_id && applicableProducts.has(line.reward_product_id)))) {

                if (reward.program_id.trigger === "with_code") {
                    if (reward?.program_id?.applies_by_boxes) {
                        limit_for_order = line.get_all_prices(reward?.quantity).priceWithTax
                    } else {
                        limit_for_order = line.get_all_prices(1).priceWithTax
                    }
                }


                if (limit_for_order >= value_of_line_total) {
                    if (reward.quantity) {
                        remainingAmountPerLine[line.cid] = line.get_all_prices(reward.quantity).priceWithTax
                    } else {
                        remainingAmountPerLine[line.cid] = line.get_price_with_tax();
                    }

                } else {
                    remainingAmountPerLine[line.cid] = limit_for_order
                }
            }

            if (
                applicableProducts.has(line.get_product().id) ||
                (line.reward_product_id && applicableProducts.has(line.reward_product_id))
            ) {
                linesToDiscount.push(line);
            } else if (line.reward_id) {
                const lineReward = this.pos.reward_by_id[line.reward_id];
                if (lineReward.id === reward.id) {
                    linesToDiscount.push(line);
                }
                if (!discountLinesPerReward[line.reward_identifier_code]) {
                    discountLinesPerReward[line.reward_identifier_code] = [];
                }
                discountLinesPerReward[line.reward_identifier_code].push(line);
            }
        }

        let cheapestLine = false;
        for (const lines of Object.values(discountLinesPerReward)) {
            const lineReward = this.pos.reward_by_id[lines[0].reward_id];
            if (lineReward.reward_type !== "discount") {
                continue;
            }
            let discountedLines = orderLines;
            if (lineReward.discount_applicability === "cheapest") {
                cheapestLine = cheapestLine || this._getCheapestLine();
                discountedLines = [cheapestLine];
            } else if (lineReward.discount_applicability === "specific") {
                discountedLines = this._getSpecificDiscountableLines(lineReward);
            }
            if (!discountedLines.length) {
                continue;
            }
            const commonLines = linesToDiscount.filter((line) => discountedLines.includes(line));
            if (lineReward.discount_mode === "percent") {
                const discount = lineReward.discount / 100;
                for (const line of discountedLines) {
                    if (line.reward_id) {
                        continue;
                    }
                    if (lineReward.discount_applicability === "cheapest") {
                        // remainingAmountPerLine[line.cid] *= 1 - discount / line.get_quantity();
                        remainingAmountPerLine[line.cid] *= 1 - discount / 2;
                    } else {
                        remainingAmountPerLine[line.cid] *= 1 - discount;
                    }
                }
            } else {
                const nonCommonLines = discountedLines.filter(
                    (line) => !linesToDiscount.includes(line)
                );
                const discountedAmounts = lines.reduce((map, line) => {
                    map[line.get_taxes().map((t) => t.id)];
                    return map;
                }, {});
                const process = (line) => {
                    const key = line.get_taxes().map((t) => t.id);
                    if (!discountedAmounts[key] || line.reward_id) {
                        return;
                    }
                    const remaining = remainingAmountPerLine[line.cid];
                    const consumed = Math.min(remaining, discountedAmounts[key]);
                    discountedAmounts[key] -= consumed;
                    remainingAmountPerLine[line.cid] -= consumed;
                };
                nonCommonLines.forEach(process);
                commonLines.forEach(process);
            }
        }

        let discountable = 0;
        const discountablePerTax = {};

        for (const line of linesToDiscount) {
            discountable += remainingAmountPerLine[line.cid];
            const taxKey = line.get_taxes().map((t) => t.id);
            if (!discountablePerTax[taxKey]) {
                discountablePerTax[taxKey] = 0;
            }
            discountablePerTax[taxKey] +=
                line.get_base_price() *
                (remainingAmountPerLine[line.cid] / line.get_price_with_tax());
        }

        return {discountable, discountablePerTax};
    },

    _applyReward(reward, coupon_id, args) {
        if (!this.partner) return;
        if (this._getRealCouponPoints(coupon_id) < reward.required_points) {
            return _t("There are not enough points on the coupon to claim this reward.");
        }

        if (reward && reward.is_global_discount) {
            const globalDiscountLines = this._getGlobalDiscountLines();
            if (globalDiscountLines.length) {
                const rewardId = globalDiscountLines[0].reward_id;
                if (
                    rewardId != reward.id &&
                    this.pos.reward_by_id[rewardId].discount >= reward.discount
                ) {
                    return _t("A better global discount is already applied.");
                } else if (rewardId != reward.id) {
                    for (const line of globalDiscountLines) {
                        this.orderlines.remove(line);
                    }
                }
            }
        }

        args = args || {};

        const rewardLines = this._getRewardLineValues({
            reward: reward,
            coupon_id: coupon_id,
            product: args["product"] || null,
            price: args["price"] || null,
            quantity: args["quantity"] || null,
            cost: args["cost"] || null,
            is_selected: args["is_selected"] || false,
            is_selectionable: args["is_selectionable"] || false,
        });

        if (!Array.isArray(rewardLines)) {
            return rewardLines;
        }

        if (!rewardLines.length) {
            return _t("The reward could not be applied.");
        }

        this.sincro_cupon();

        // Procesar rewardLines
        for (const rewardLine of rewardLines || []) {

            // Las que NO son descuento, se agregan normalmente
            if (rewardLine.reward_type !== 'discount') {
                this.orderlines.add(this._createLineFromVals(rewardLine));

                if (rewardLine.coupon_id) {
                    const coupon = this.cupon_by_id[rewardLine.coupon_id];
                    if (coupon && coupon.code) {
                        this.mark_coupon_as_used(coupon.code, true);
                    }
                }
                continue;
            }

            if (reward.discount_applicability == "order") {
                if (rewardLine.coupon_id) {

                    const coupon = this.cupon_by_id[rewardLine.coupon_id];
                    if (coupon && coupon.code) {
                        this.mark_coupon_as_used(coupon.code, true);
                    }
                }
                continue;
            }

            // Procesar descuentos
            const quantityToApply = args["quantity"] || rewardLine.quantity_applied || 1;
            const productIds = reward.all_discount_product_ids || [rewardLine.reward_product_id];

            // Obtener líneas elegibles SIN descuento aplicado
            const eligibleLines = this.get_orderlines().filter(line =>
                !line.is_reward_line &&
                productIds.has(line.product.id) &&
                (!line.coupon_id) &&
                line.get_quantity() >= quantityToApply
            ).sort((a, b) => {
                const diffA = a.get_quantity() - quantityToApply;
                const diffB = b.get_quantity() - quantityToApply;
                return diffA - diffB;
            });

            if (!eligibleLines.length) {
                console.warn('No eligible lines found for discount reward');
                continue;
            }

            let remainingQty = quantityToApply;

            // Aplicar el descuento dividiendo líneas si es necesario
            for (const line of eligibleLines) {
                if (remainingQty <= 0) break;

                const lineQty = line.get_quantity();
                const qtyToDiscount = Math.min(remainingQty, lineQty);

                if (qtyToDiscount < lineQty) {

                    // Dividir la línea: reducir cantidad de línea original
                    line.set_quantity(lineQty - qtyToDiscount);

                    // Crear nueva línea con descuento aplicado
                    const newLine = {
                        product: line.product,
                        price: line.get_unit_price(),
                        quantity: qtyToDiscount,
                        is_selectionable: args["is_selectionable"] || false,
                        program_id: reward.program_id.id,
                        coupon_id: coupon_id,
                        reward_id: reward.id,
                        is_selected: args["is_selected"] || false,
                        tracking: "none",
                        merge: false,
                        tax_ids: line.product.taxes_id,
                        create: true,
                        discount: rewardLine.percent_discount || reward.discount,
                    };

                    const discountedLine = this._createLineFromVals(newLine);
                    discountedLine.reward_id = reward.id;
                    discountedLine.coupon_id = coupon_id;
                    discountedLine.is_selectionable = args["is_selectionable"] || false;
                    discountedLine.is_selected = args["is_selected"] || false;
                    discountedLine.program_id = reward.program_id.id;
                    discountedLine.set_discount(rewardLine.percent_discount || reward.discount);

                    this.orderlines.add(discountedLine);

                } else {
                    // Aplicar descuento a toda la línea
                    line.reward_id = reward.id;
                    line.coupon_id = coupon_id;
                    line.is_selectionable = args["is_selectionable"] || false;
                    line.is_selected = args["is_selected"] || false;
                    line.program_id = reward.program_id.id;
                    line.set_discount(rewardLine.percent_discount || reward.discount);
                }

                remainingQty -= qtyToDiscount;
            }

            // Marcar cupón como usado
            if (rewardLine.coupon_id) {
                const coupon = this.cupon_by_id[rewardLine.coupon_id];
                if (coupon && coupon.code) {
                    this.mark_coupon_as_used(coupon.code, true);
                }
            }
        }


        if (reward.discount_applicability == "order") {
            if (reward.reward_type == 'discount') {
                applyOrderDiscount(this, reward, coupon_id);
            }
        }

        return true;
    },


    async mergeAssociatedNormalLines(product) {
        if (!product || !product.id) return;

        const myProductId = product.id;
        const orderLines = this.get_orderlines();
        const linesToMerge = [];  // Líneas normales del mismo producto
        let baseLine = null;
        let totalQty = 0;

        for (const l of orderLines) {
//            if (l.program_id) continue;  // Solo líneas normales
            const prod = l.get_product && l.get_product();
            if (!prod || prod.id !== myProductId) continue;  // Mismo producto
            if (l.get_quantity() <= 0) continue;  // Cantidad positiva

            if (!baseLine) {
                baseLine = l;
            } else {
                linesToMerge.push(l);
            }
            totalQty += l.get_quantity();
        }

        if (linesToMerge.length === 0 || !baseLine) return;  // Nada que unificar

        for (const l of linesToMerge) {
            this.orderlines.remove(l);
        }

        // Consolidar en la base
        baseLine.set_quantity(totalQty);
    },


    clear_all_discounts() {
        const orderLines = this._get_normal_lines();

        for (const line of orderLines) {
            if (!line.sale_order_line_id) {
                line.cupon_alter = null;
                line.coupon_id = null;
                line.set_discount(0);
                line.is_selectionable = false;
                line.reward_id = null
                line.is_selected = false
            }
        }
    },

    async mark_coupon_as_used(codeCoupon) {
        if (!codeCoupon) {
            return;
        }

        try {
            await this.env.services.orm.call(
                'loyalty.card',
                'mark_coupon_as_used',
                [codeCoupon]
            );
        } catch (error) {
            console.error(`Error al marcar el cupón como usado (${codeCoupon}):`, error);
        }
    },

    async validate_order_for_cupon() {

        if (this.partner === undefined || !this.partner) {
            await this.env.services.popup.add(OkeyPopup, {
                title: _t("Orden no válida"),
                body: _t("Se requiere un cliente para aplicar el cupon."),
            });
            return false;
        }

        return true;
    },

    _canGenerateRewards(couponProgram, orderTotalWithTax, orderTotalWithoutTax) {
        for (const rule of couponProgram.rules) {
            const amountToCompare =
                rule.minimum_amount_tax_mode == "incl" ? orderTotalWithTax : orderTotalWithoutTax;

            if (rule.minimum_amount > amountToCompare) {
                this.pos.env.services.notification.add(
                    `Monto insuficiente: se requiere un mínimo de ${rule.minimum_amount} para aplicar esta promoción`, {
                        type: 'warning',
                        sticky: false
                    }
                );
                return false;
            }

            // Verificar cantidad mínima de productos
            const nItems = this._computeNItems(rule);
            if (rule.minimum_qty > nItems) {
                this.pos.env.services.notification.add(
                    `Cantidad insuficiente: se necesitan al menos ${rule.minimum_qty} productos para aplicar esta promoción (actualmente: ${nItems})`, {
                        type: 'warning',
                        sticky: false
                    }
                );
                return false;
            }
        }

        return true;
    },

    async _activateCode(code) {
        const validate = await this.validate_order_for_cupon()

        if (!validate) {
            return true;
        }
        this.sincro_cupon()

        const rule = this.pos.rules.find((rule) => {
            return rule.mode === "with_code" && (rule.promo_barcode === code || rule.code === code);
        });
        let claimableRewards = null;
        let coupon = null;
        if (rule) {
            if (
                rule.program_id.date_from &&
                this.date_order < rule.program_id.date_from.startOf("day")
            ) {
                return _t("That promo code program is not yet valid.");
            }
            if (rule.program_id.date_to && this.date_order > rule.program_id.date_to.endOf("day")) {
                return _t("That promo code program is expired.");
            }
            const program_pricelists = rule.program_id.pricelist_ids;
            if (
                program_pricelists.length > 0 &&
                (!this.pricelist || !program_pricelists.includes(this.pricelist.id))
            ) {
                return _t("That promo code program requires a specific pricelist.");
            }
            if (this.codeActivatedProgramRules.includes(rule.id)) {
                return _t("That promo code program has already been activated.");
            }
            this.codeActivatedProgramRules.push(rule.id);
            await this._updateLoyaltyPrograms();
            claimableRewards = this.getClaimableRewards(false, rule.program_id.id);
        } else {
            if (this.codeActivatedCoupons.find((coupon) => coupon.code === code)) {
                return _t("That coupon code has already been scanned and activated.");
            }
            const customerId = this.get_partner() ? this.get_partner().id : false;
            const {successful, payload} = await this.env.services.orm.call(
                "pos.config",
                "use_coupon_code",
                [
                    [this.pos.config.id],
                    code,
                    this.date_order,
                    customerId,
                    this.pricelist ? this.pricelist.id : false,
                ]
            );
            if (successful) {
                // Allow rejecting a gift card that is not yet paid.
                const program = this.pos.program_by_id[payload.program_id];
                if (program && program.program_type === "gift_card" && !payload.has_source_order) {
                    const {confirmed} = await this.env.services.popup.add(ConfirmPopup, {
                        title: _t("Unpaid gift card"),
                        body: _t(
                            "This gift card is not linked to any order. Do you really want to apply its reward?"
                        ),
                    });
                    if (!confirmed) {
                        return _t("Unpaid gift card rejected.");
                    }
                }
                coupon = new PosLoyaltyCard(
                    code,
                    payload.coupon_id,
                    payload.program_id,
                    payload.partner_id,
                    payload.points,
                    payload.expiration_date
                );
                this.pos.couponCache[coupon.id] = coupon;
                this.codeActivatedCoupons.push(coupon);
                await this._updateLoyaltyPrograms();
                claimableRewards = this.getClaimableRewardsCustom(coupon.id);

                this.recreate_discount_lines()

            } else {
                return payload.error_message;
            }
        }
//        if (claimableRewards && claimableRewards.length === 1) {
//            if (
//                claimableRewards[0].reward.reward_type !== "product" ||
//                !claimableRewards[0].reward.multi_product
//            ) {
////                this._applyReward(claimableRewards[0].reward, claimableRewards[0].coupon_id);
////                this._updateRewards();
//            }
//        }
        if (!rule && this.orderlines.length === 0 && coupon) {
            return _t(
                "Gift Card: %s\nBalance: %s",
                code,
                this.env.utils.formatCurrency(coupon.balance)
            );
        }
        return true;
    },

    sincro_cupon() {
        for (const cupon of this.codeActivatedCoupons) {
            this.cupon_by_id[cupon.id] = cupon;
        }
    },

});

function _newRandomRewardCode() {
    return (Math.random() + 1).toString(36).substring(3);
}

function computeFreeQuantity(numberItems, n, m) {
    const factor = Math.trunc(numberItems / (n + m));
    const free = factor * m;
    const charged = numberItems - free;
    // adjust the calculated free quantities
    const x = (factor + 1) * n;
    const y = x + (factor + 1) * m;
    const adjustment = x <= charged && charged < y ? charged - x : 0;
    return Math.floor(free + adjustment);
}

function sortRewards(potentialRewards, selectedRewardIds) {

    const selectedRewardsSet = new Set(selectedRewardIds);

    // Crear un Map con los datos pre-calculados para cada reward
    const rewardDataMap = new Map(
        potentialRewards.map(item => {
            const rewardId = item.reward.id;

            return [
                rewardId,
                {
                    item: item,
                    isMandatory: item.program?.mandatory_promotion || false,
                    isSelected: selectedRewardsSet.has(rewardId),
                    isMain: item.reward?.is_main || false,
                    isCouponOrder: item.reward?.program_id?.program_type === "coupons" &&
                        item.reward?.discount_applicability === "order"
                }
            ];
        })
    );

    return potentialRewards.sort((a, b) => {
        const dataA = rewardDataMap.get(a.reward.id);
        const dataB = rewardDataMap.get(b.reward.id);

        // 0. Primero: enviar al final los coupons con discount_applicability = "order"
        if (dataA.isCouponOrder !== dataB.isCouponOrder) {
            return dataA.isCouponOrder ? 1 : -1;
        }

        // 1. Segundo: programas mandatory_promotion
        if (dataA.isMandatory !== dataB.isMandatory) {
            return dataA.isMandatory ? -1 : 1;
        }

        // 2. Tercero: rewards seleccionadas
        if (dataA.isSelected !== dataB.isSelected) {
            return dataA.isSelected ? -1 : 1;
        }

        // 3. Cuarto: rewards principales (is_main)
        if (dataA.isMain !== dataB.isMain) {
            return dataA.isMain ? -1 : 1;
        }

        return 0;
    });
}

function distributePointsWithPrograms(totalPoints, potentialRewards, list_rewards_selected, orderlines) {
    // Validaciones
    if (!Array.isArray(potentialRewards) || typeof totalPoints !== 'number' || totalPoints < 0) {
        return {distribution: {}, remainingPoints: totalPoints};
    }

    // Inicializar distribución
    let distribution = {};
    for (let reward of potentialRewards) {
        if (reward?.id && typeof reward.required_points === 'number') {
            distribution[reward.id] = 0;
        }
    }

    let remainingPoints = totalPoints;

    // PASO 1: Asignar recompensas gratuitas (siempre 1 de cada una)

    // Filtrar solo recompensas de pago
    const paidRewards = potentialRewards.filter(reward => reward.required_points > 0);

    // Convertir list_rewards_selected a array de IDs
    const selectedIds = Array.isArray(list_rewards_selected) ? list_rewards_selected : [];

    // PASO 2: MÁXIMA PRIORIDAD - Programas activados con código (with_code)
    const codeActivatedRewards = paidRewards.filter(reward =>
        reward.program_id?.trigger === "with_code"
    );

    for (let reward of codeActivatedRewards) {

        const maxQuantity = Math.floor(remainingPoints / reward.required_points);
        let total_reward;

        if (reward?.program_id?.applies_by_boxes) {
            let maxBoxes = reward?.program_id?.max_boxes_limit || 0; // 0 = sin límite
            let calculatedBoxes;

            const product = orderlines.find(
                line => line.product.id === reward?.program_id?.trigger_product_ids[0]
            );

            if (remainingPoints % product?.product?.uom_po_factor_inv === 0) {
                calculatedBoxes = Math.floor(remainingPoints);
            } else {
                calculatedBoxes = Math.floor(remainingPoints / product?.product?.uom_po_factor_inv);
            }

            if (maxBoxes > 0) {
                calculatedBoxes = Math.min(calculatedBoxes, maxBoxes);
            }

            total_reward = calculatedBoxes * product?.product?.uom_po_factor_inv;

        }


        if (total_reward > 0) {
            distribution[reward.id] = total_reward;
            remainingPoints -= total_reward * reward.required_points;
        }
    }

    if (remainingPoints !== 0) {
        const freeRewards = potentialRewards.filter(reward => reward.required_points === 0);
        for (let reward of freeRewards) {
            distribution[reward.id] = 1;
        }
    }


    // PASO 3: SEGUNDA PRIORIDAD - Recompensas seleccionadas
    const selectedRewards = paidRewards.filter(reward =>
        selectedIds.includes(reward.id) &&
        reward.program_id?.trigger !== "with_code"
    );

    for (let reward of selectedRewards) {
        const maxQuantity = Math.floor(remainingPoints / reward.required_points);
        if (maxQuantity > 0) {
            distribution[reward.id] = maxQuantity;
            remainingPoints -= maxQuantity * reward.required_points;
        }
    }

    // PASO 4: TERCERA PRIORIDAD - Recompensas principales (is_main = true)
    const mainRewards = paidRewards.filter(reward =>
        reward.is_main &&
        !selectedIds.includes(reward.id) &&
        reward.program_id?.trigger !== "with_code"
    );

    for (let reward of mainRewards) {

        let maxQuantity = Math.floor(remainingPoints / reward.required_points);

        if (reward?.program_id?.applies_by_boxes && reward.is_main) {

            let maxBoxes = reward?.program_id?.max_boxes_limit || 0;

            const product = orderlines.find(
                line => line.product.id === reward?.program_id?.trigger_product_ids[0]
            );

            if (maxBoxes > 0) {
                maxQuantity = Math.min(maxQuantity, maxBoxes);
            }
        }

        if (maxQuantity > 0) {
            distribution[reward.id] = maxQuantity;
            remainingPoints -= maxQuantity * reward.required_points;
        }
    }

    // PASO 5: CUARTA PRIORIDAD - Distribución equitativa (round-robin)
    const regularRewards = paidRewards.filter(reward =>
        !reward.is_main &&
        !selectedIds.includes(reward.id) &&
        reward.program_id?.trigger !== "with_code"
    );

    if (regularRewards.length > 0) {
        // Ordenar por required_points ascendente
        const sortedRegularRewards = [...regularRewards].sort((a, b) =>
            a.required_points - b.required_points
        );

        // Round-robin optimizado
        let anyAssigned = true;
        while (anyAssigned && remainingPoints > 0) {
            anyAssigned = false;

            for (let reward of sortedRegularRewards) {
                if (remainingPoints >= reward.required_points) {
                    // Calcular cuántas podemos asignar en esta ronda
                    // Para mantener equidad, asignamos de a 1 por ronda
                    distribution[reward.id] = (distribution[reward.id] || 0) + 1;
                    remainingPoints -= reward.required_points;
                    anyAssigned = true;
                }
            }
        }
    }

    return {
        distribution,
        remainingPoints
    };
}


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


function applyOrderDiscount(order, reward, coupon_id) {

    // Verificar que el descuento aplica a toda la orden
    if (reward.discount_applicability !== "order") {
        return;
    }

    const extraPercent = parseFloat(reward.discount) || 0.0;

    // Si el descuento es 0 o negativo, no hacer nada
    if (extraPercent <= 0) {
        return;
    }

    // Obtener líneas válidas (excluir líneas de recompensa)
    const validLines = order.get_orderlines().filter(line => {
        return !line.is_reward_line &&
            !line.is_global_discount &&
            line.get_product();
    });

    // Aplicar descuento a cada línea
    validLines.forEach(line => {
        // Obtener descuento base actual
        const baseDiscount = parseFloat(line.get_discount()) || 0.0;

        // Obtener modo de combinación del producto (por defecto 'sequence')
        const product = line.get_product();
        const combineMode = product.discount_combine_mode || 'sequence';

        let finalDiscount;

        if (combineMode === 'add') {
            // Modo aditivo: suma directa
            finalDiscount = baseDiscount + extraPercent;
        } else {
            // Modo secuencial (por defecto): aplica sobre el precio ya descontado
            // Formula: base + extra - (base × extra / 100)
            finalDiscount = baseDiscount + extraPercent - (baseDiscount * extraPercent / 100.0);
            console.log("finalDiscount baseDiscount", baseDiscount)
            console.log("finalDiscount extraPercent", extraPercent)
        }

        // Asegurar que esté entre 0 y 100
        finalDiscount = Math.max(0.0, Math.min(100.0, finalDiscount));


        // Redondear a 3 decimales
        finalDiscount = Math.round(finalDiscount * 1000) / 1000;

        // Guardar información adicional en la línea
        line.additional_original_discount = baseDiscount;
        line.program_id = reward.program_id?.id || null;
        line.cupon_alter = coupon_id;

        line.set_discount(finalDiscount);
    });
}

