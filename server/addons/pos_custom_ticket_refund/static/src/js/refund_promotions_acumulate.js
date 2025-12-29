/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { PosLoyaltyCard } from "@pos_loyalty/overrides/models/loyalty";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

patch(PaymentScreen.prototype, {
    //@override
    async validateOrder(isForceValidate) {
        const pointChanges = {};
        const newCodes = [];
        for (const pe of Object.values(this.currentOrder.couponPointChanges)) {
            if (pe.coupon_id > 0) {
                pointChanges[pe.coupon_id] = pe.points;
            } else if (pe.barcode && !pe.giftCardId) {
                // New coupon with a specific code, validate that it does not exist
                newCodes.push(pe.barcode);
            }
        }
        for (const line of this.currentOrder._get_reward_lines()) {
            if (line.coupon_id < 1) {
                continue;
            }
            if (!pointChanges[line.coupon_id]) {
                pointChanges[line.coupon_id] = -line.points_cost;
            } else {
                pointChanges[line.coupon_id] -= line.points_cost;
            }
        }
        if (!(await this._isOrderValid(isForceValidate))) {
            return;
        }
        // No need to do an rpc if no existing coupon is being used.
        if (Object.keys(pointChanges || {}).length > 0 || newCodes.length) {
            try {
                const { successful, payload } = await this.orm.call(
                    "pos.order",
                    "validate_coupon_programs",
                    [[], pointChanges, newCodes]
                );
                // Payload may contain the points of the concerned coupons to be updated in case of error. (So that rewards can be corrected)
                const { couponCache } = this.pos;
                if (payload && payload.updated_points) {
                    for (const pointChange of Object.entries(payload.updated_points)) {
                        if (couponCache[pointChange[0]]) {
                            couponCache[pointChange[0]].balance = pointChange[1];
                        }
                    }
                }
                if (payload && payload.removed_coupons) {
                    for (const couponId of payload.removed_coupons) {
                        if (couponCache[couponId]) {
                            delete couponCache[couponId];
                        }
                    }
                    this.currentOrder.codeActivatedCoupons =
                        this.currentOrder.codeActivatedCoupons.filter(
                            (coupon) => !payload.removed_coupons.includes(coupon.id)
                        );
                }
                if (!successful) {
                    this.popup.add(ErrorPopup, {
                        title: _t("Error validating rewards"),
                        body: payload.message,
                    });
                    return;
                }
            } catch {
                // Do nothing with error, while this validation step is nice for error messages
                // it should not be blocking.
            }
        }
        await super.validateOrder(...arguments);
        await this.refund_points_for_promotions()

    },
    /**
     * @override
     */
    async _postPushOrderResolve(order, server_ids) {
        // Compile data for our function
        const { program_by_id, reward_by_id, couponCache } = this.pos;
        const rewardLines = order._get_reward_lines();
        const partner = order.get_partner();

        let couponData = Object.values(order.couponPointChanges || {}).reduce((agg, pe) => {
            // Validar que pe y program_id existan antes de continuar
            if (!pe || !pe.program_id) {
                console.warn('POS Loyalty: Skipping invalid couponPointChange entry:', pe);
                return agg;
            }

            const program = program_by_id[pe.program_id];

            // Validar que el programa exista en el caché
            if (!program) {
                console.warn('POS Loyalty: Program not found in cache, program_id:', pe.program_id);
                return agg;
            }

            agg[pe.coupon_id] = Object.assign({}, pe, {
                points: pe.points,
            });

            // Usar optional chaining para evitar error si is_nominative es undefined
            if (program?.is_nominative && partner) {
                agg[pe.coupon_id].partner_id = partner.id;
            }
            return agg;
        }, {});
        for (const line of rewardLines) {
            const reward = reward_by_id[line.reward_id];
            if (!reward || !reward.program_id) {
                continue;
            }

            // Validar que el programa exista en el caché antes de crear el couponData
            const rewardProgram = program_by_id[reward.program_id.id];
            if (!rewardProgram) {
                continue;
            }

            if (!couponData[line.coupon_id]) {
                couponData[line.coupon_id] = {
                    points: 0,
                    program_id: reward.program_id.id,
                    coupon_id: line.coupon_id,
                    barcode: false,
                };
            }
            if (!couponData[line.coupon_id].line_codes) {
                couponData[line.coupon_id].line_codes = [];
            }
            if (!couponData[line.coupon_id].line_codes.includes(line.reward_identifier_code)) {
                !couponData[line.coupon_id].line_codes.push(line.reward_identifier_code);
            }
            couponData[line.coupon_id].points -= line.points_cost;
        }
        // We actually do not care about coupons for 'current' programs that did not claim any reward, they will be lost if not validated
        couponData = Object.fromEntries(
            Object.entries(couponData).filter(([key, value]) => {
                const program = program_by_id[value.program_id];
                // Validar que el programa exista antes de acceder a applies_on
                if (!program) {
                    return false;
                }
                if (program.applies_on === "current") {
                    return value.line_codes && value.line_codes.length;
                }
                return true;
            })
        );
        if (Object.keys(couponData || []).length > 0) {
            const payload = await this.orm.call("pos.order", "confirm_coupon_programs", [
                server_ids,
                couponData,
                true
            ]);

            if (payload.coupon_updates) {
                for (const couponUpdate of payload.coupon_updates) {
                    let dbCoupon = couponCache[couponUpdate.old_id];
                    if (dbCoupon) {
                        dbCoupon.id = couponUpdate.id;
                        dbCoupon.balance = couponUpdate.points;
                        dbCoupon.code = couponUpdate.code;
                    } else {
                        dbCoupon = new PosLoyaltyCard(
                            couponUpdate.code,
                            couponUpdate.id,
                            couponUpdate.program_id,
                            couponUpdate.partner_id,
                            couponUpdate.points
                        );
                    }
                    delete couponCache[couponUpdate.old_id];
                    couponCache[couponUpdate.id] = dbCoupon;
                }
            }
            // Update the usage count since it is checked based on local data
            if (payload.program_updates) {
                for (const programUpdate of payload.program_updates) {
                    const program = program_by_id[programUpdate.program_id];
                    if (program) {
                        program.total_order_count = programUpdate.usages;
                    }
                }
            }
            if (payload.coupon_report) {
                for (const [actionId, active_ids] of Object.entries(payload.coupon_report)) {
                    await this.report.doAction(actionId, active_ids);
                }
                order.has_pdf_gift_card = Object.keys(payload.coupon_report).length > 0;
            }
            order.new_coupon_info = payload.new_coupon_info;
        }

        // Limpiar couponPointChanges de programas inválidos antes de llamar al super
        // para evitar el error "Cannot read properties of undefined (reading 'is_nominative')"
        // en el código original de pos_loyalty
        if (order.couponPointChanges) {
            const validCouponPointChanges = {};
            let removedCount = 0;
            for (const [key, pe] of Object.entries(order.couponPointChanges)) {
                // Verificar que pe existe, tiene program_id, y el programa existe en el cache
                // También verificar que el programa tenga is_nominative definido (no undefined)
                const program = pe?.program_id ? program_by_id[pe.program_id] : null;
                if (pe && pe.program_id && program && typeof program.is_nominative !== 'undefined') {
                    validCouponPointChanges[key] = pe;
                } else {
                    removedCount++;
                    console.warn('POS Loyalty: Filtering out invalid couponPointChange before super call:', {
                        key,
                        program_id: pe?.program_id,
                        programExists: !!program,
                        is_nominative_defined: program ? typeof program.is_nominative !== 'undefined' : false
                    });
                }
            }
            if (removedCount > 0) {
                console.warn(`POS Loyalty: Removed ${removedCount} invalid couponPointChanges before super call`);
            }
            order.couponPointChanges = validCouponPointChanges;
        }

        // Envolver el super en try-catch para capturar errores residuales
        // y evitar que el error rompa la transacción completa
        try {
            return await super._postPushOrderResolve(order, server_ids);
        } catch (error) {
            // Si el error es específicamente sobre is_nominative, lo manejamos silenciosamente
            // ya que los datos ya fueron procesados correctamente arriba
            if (error?.message?.includes('is_nominative')) {
                console.warn('POS Loyalty: Error accessing is_nominative in super, handled gracefully:', error.message);
                return;
            }
            // Re-lanzar otros errores
            throw error;
        }
    },


    restrict_in_refund(order){
        const orderlines = order.get_orderlines();
        if (!orderlines || orderlines.length === 0) {
            return false;
        }
        return !!orderlines[0].refunded_orderline_id;
    },


    async refund_points_for_promotions() {
        const order = this.currentOrder;
        if (this.restrict_in_refund(order)) {
            const normal_lines = order._get_normal_lines();
            const reward_lines = order._get_reward_lines_custom();

            let products_quantities = {};
            normal_lines.forEach(line => {
                const productId = line.product.id;
                const quantity = Math.abs(line.quantity);
                if (!products_quantities[productId]) {
                    products_quantities[productId] = { quantity: 0, type: 'normal' };
                }
                products_quantities[productId].quantity += quantity;
            });

            reward_lines.forEach(line => {
                const productId = line.original_id_reward || line.product.id;
                const quantity = Math.abs(line.quantity);
                if (!products_quantities[productId]) {
                    products_quantities[productId] = { quantity: 0, type: 'reward' };
                }
                products_quantities[productId].quantity += quantity;
            });

            const partner_id = order.partner.id || false;
            if (!partner_id) {
                return;
            }
            try {
                const dataToSend = JSON.stringify(products_quantities);
                await this.orm.call("pos.order", "refund_promotion_coupon_programs", [
                    partner_id,
                    dataToSend
                ]);
            } catch (error) {
                console.error("Error al llamar refund_promotion_coupon_programs:", error);
            }
        }
    }

});