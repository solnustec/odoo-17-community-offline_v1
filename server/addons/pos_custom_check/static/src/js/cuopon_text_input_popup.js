/** @odoo-module **/

import {TextInputPopup} from "@point_of_sale/app/utils/input_popups/text_input_popup";
import {onMounted, useRef, useState} from "@odoo/owl";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";

patch(TextInputPopup.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.state = useState({
            inputValue: "",
            recompensa: "",
            cantidadMinima: 0,
            limite: "",
            couponPromotions: [],
            loading: false,
            error: null,
            codeCoupon: 0,
            // Nuevos campos para la lista de cupones
            availableRewards: [],
            selectedRewardId: null,
            selectedReward: null
        });
        this.orm = useService("orm");

        onMounted(async () => {
            const selectedOrderline = this.pos.get_order()?.get_selected_orderline();
            const productId = selectedOrderline?.product?.id;

            await this.loadAvailableRewards();

            if (productId) {
                await this.fetchCouponPromotions(parseInt(productId));
            }
        });
    },

    /**
     * Cargar cupones filtrados desde reward_by_id del POS
     * Filtros:
     * - program_type === 'coupons'
     * - reward_type === 'discount'
     * - discount_applicability === 'order'
     * - all_discount_product_ids debe estar vacío
     */
    async loadAvailableRewards() {
        const rewards = [];

        try {
            // Acceder a reward_by_id del POS
            const rewardById = this.pos.reward_by_id;

            if (!rewardById) {
                console.warn("reward_by_id no está disponible en el POS");
                return;
            }

            // Iterar sobre reward_by_id
            for (const [rewardId, reward] of Object.entries(rewardById)) {
                // Aplicar filtros
                const isProgramTypeCoupon = reward.program_id?.program_type === 'coupons';
                const isDiscountType = reward.reward_type === 'discount';
                const isOrderApplicability = reward.discount_applicability === 'order';

                // Solo agregar si cumple TODOS los filtros
                if (isProgramTypeCoupon &&
                    isDiscountType &&
                    isOrderApplicability) {

                    rewards.push({
                        id: reward.id,
                        description: reward.description,
                        discount: reward.discount,
                        discount_mode: reward.discount_mode,
                        discount_applicability: reward.discount_applicability,
                        discount_max_amount: reward.discount_max_amount,
                        program_id: {
                            id: reward.program_id.id,
                            name: reward.program_id.name,
                            trigger: reward.program_id.trigger,
                            program_type: reward.program_id.program_type,
                            applies_on: reward.program_id.applies_on
                        },
                        required_points: reward.required_points,
                        is_global_discount: reward.is_global_discount,
                        clear_wallet: reward.clear_wallet,
                        discount_product_ids: reward.discount_product_ids,
                        reward_product_ids: reward.reward_product_ids
                    });

                }
            }

            this.state.availableRewards = rewards;

        } catch (error) {
            console.error("Error al cargar cupones disponibles:", error);
            this.state.error = "Error al cargar cupones: " + error.message;
        }
    },

    /**
     * Manejar la selección de un cupón
     */
    async onRewardSelect(rewardId) {
        this.state.selectedRewardId = rewardId;

        // Encontrar el cupón completo
        const selectedReward = this.state.availableRewards.find(r => r.id === rewardId);
        this.state.selectedReward = selectedReward;

        if (selectedReward) {
            // Actualizar la información en la tabla superior
            this.state.recompensa = selectedReward.description;
            this.state.cantidadMinima = selectedReward.required_points || 0;
            this.state.limite = selectedReward.discount_max_amount
                ? `$${selectedReward.discount_max_amount.toFixed(2)}`
                : "Sin límite";

            const promotions = await this.orm.call(
                'loyalty.program',
                'get_coupon_promotions_by_program',
                [selectedReward.program_id.id]
            );

            if (promotions.error) {
                this.state.error = promotions.error;
            }

            let coupon = '';
            if (promotions?.coupons[0]?.is_auto_apply) {
                coupon = promotions?.coupons[0]?.code;
            }

            this.state.inputValue = coupon;
            this.state.codeCoupon = promotions?.coupons[0]?.code || '';

            this.state.couponPromotions = promotions;
        }
    },

    async fetchCouponPromotions(productId) {
        this.state.loading = true;
        try {
            const promotions = await this.orm.call(
                'loyalty.program',
                'get_coupon_promotions_for_product',
                [productId]
            );

            if (promotions.error) {
                this.state.error = promotions.error;
            }

            let coupon = '';
            if (promotions[0]?.coupons[0]?.is_auto_apply) {
                coupon = promotions[0]?.coupons[0]?.code;
            }

            this.state.inputValue = coupon;
            this.state.codeCoupon = promotions[0]?.coupons[0]?.code || '';

            // Solo actualizar si no hay un cupón seleccionado manualmente
            if (!this.state.selectedReward) {
                this.state.recompensa = promotions[0]?.reward_ids[0]?.description || '';
                this.state.cantidadMinima = promotions[0]?.qty_min || '';
                this.state.limite = promotions[0]?.max_boxes_limit || '';
            }

            // Guardar las promociones
            this.state.couponPromotions = promotions;

        } catch (error) {
            this.state.codeCoupon = "Error al consultar las promociones: " + error.message;
            this.state.error = "Error al consultar las promociones: " + error.message;
        } finally {
            this.state.loading = false;
        }
    },

    /**
     * Obtener el formato de descuento para mostrar
     */
    getDiscountDisplay(reward) {
        if (reward.discount_mode === 'percent') {
            return `${reward.discount}%`;
        } else {
            return `$${reward.discount.toFixed(2)}`;
        }
    },

    /**
     * Obtener el tipo de aplicación del descuento
     */
    getApplicabilityText(reward) {
        if (reward.discount_applicability === 'order') {
            return 'Toda la orden';
        } else if (reward.discount_applicability === 'specific_products') {
            return 'Productos específicos';
        } else {
            return 'Productos más baratos';
        }
    },

    async confirm() {
        // Incluir el cupón seleccionado en el resultado

        // Si necesitas marcar el cupón como usado
        // if (this.state.codeCoupon) {
        //     const result = await this.orm.call(
        //         'loyalty.card',
        //         'mark_coupon_as_used',
        //         [this.state.codeCoupon]
        //     );
        //     console.log("Cupón marcado como usado:", result);
        // }

        super.confirm();
    },
});