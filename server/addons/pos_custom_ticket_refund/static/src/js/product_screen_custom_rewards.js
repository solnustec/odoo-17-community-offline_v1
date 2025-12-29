/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";

import {_t} from "@web/core/l10n/translation";
import {SelectionCustomPopup} from "@pos_custom_check/popups/selection_popup";
import {useService} from "@web/core/utils/hooks";

patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        this.pos.rewardButtonComponent = this;
        this.rpc = useService("rpc");
    },


    options_for_reward(rewards, program_id) {
        return rewards.filter(reward => {
            return reward.reward?.program_id?.id === program_id && !(reward.reward?.program_id?.mandatory_promotion);
        });
    },


    delete_lines_reward(reward) {
        const newProgramId = reward?.reward?.program_id?.id;
        const newRewardId = reward?.reward?.id; // Este es el ID que se guarda

        if (!newProgramId || !newRewardId) {
            console.warn('Invalid reward structure:', reward);
            return false;
        }

        const order = this.pos.get_order();
        const selectedRewards = order.list_rewards_selected;

        // Eliminar IDs de recompensas del mismo programa
        for (let i = selectedRewards.length - 1; i >= 0; i--) {
            const rewardId = selectedRewards[i]; // Este es el ID
            const rewardData = this.pos.reward_by_id[rewardId];

            if (rewardData?.program_id?.id === newProgramId) {
                selectedRewards.splice(i, 1);
            }
        }

        // Añadir el ID de la nueva recompensa
        selectedRewards.push(newRewardId);

        return true;
    },

    async _applyReward(reward, coupon_id, potentialQty) {
        const order = this.pos.get_order();
        order.disabledRewards.delete(reward.id);

        const args = {};
        if (reward.reward_type === "product" && reward.multi_product) {
            const productsList = reward.reward_product_ids.map((product_id) => ({
                id: product_id,
                label: this.pos.db.get_product_by_id(product_id).display_name,
                item: product_id,
            }));
            const {confirmed, payload: selectedProduct} = await this.popup.add(SelectionCustomPopup, {
                title: _t("Please select a product for this reward"),
                list: productsList,
            });
            if (!confirmed) {
                return false;
            }
            args["product"] = selectedProduct;
        }

        args["is_selected"] = true;

//        const result = order._applyReward(reward, coupon_id, args);
//        if (result !== true) {
//            // Returned an error
//            this.notification.add(result);
//        }
        order._updateRewards();
        return ;

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

    _getPotentialRewards() {
        const order = this.pos.get_order();
        // Claimable rewards excluding those from eWallet programs.
        // eWallet rewards are handled in the eWalletButton.
        let rewards = [];
        if (order) {
            const claimableRewards = order.getClaimableRewards();
            rewards = claimableRewards.filter(
                ({reward}) => reward.program_id.program_type !== "ewallet"
            );
        }
        const discountRewards = rewards.filter(({reward}) => reward.reward_type == "discount");
        const freeProductRewards = rewards.filter(({reward}) => reward.reward_type == "product");
        const potentialFreeProductRewards = this.pos.getPotentialFreeProductRewards();
        return discountRewards.concat(
            this._mergeFreeProductRewards(freeProductRewards, potentialFreeProductRewards)
        );
    },
    async remove_coupon(line) {
        const code_activated_coupons_index = this.pos.selectedOrder.codeActivatedCoupons.findIndex(coupon => coupon.id === line.coupon_id);
        const coupons = [...this.pos.selectedOrder.codeActivatedCoupons];
        const coupon = coupons.filter(coupon => coupon.id === line.coupon_id);
        const coupon_code = coupon[0].code
        if (code_activated_coupons_index !== -1) {
            this.pos.selectedOrder.codeActivatedCoupons.splice(code_activated_coupons_index, 1); // Elimina el objeto en la posición index
        }
        this.currentOrder.removeOrderline(line)
        const response  = await this.orm.call(
            'loyalty.card',
            'mark_coupon_as_used',
            [coupon_code, true]
        );

        this.pos.get_order()._updateRewards()
    },

    async get_selectionable_reward(line) {

        if (!this.pos.get_order().partner) return;

        //funcion para borrar otras promociones del programa
        await this.pos.get_order()._resetProgramsSelectionable(line);
        await new Promise(resolve => setTimeout(resolve, 250));

        const rewards = this._getPotentialRewards();

        console.log('_getPotentialRewards', rewards)

        //filtro para mostrar solo promociones de la linea seleccionada y de todo
        const rewards_filter = this.options_for_reward(rewards, line.program_id)

        console.log('rewards_filter', rewards_filter)

        //muestra popup de promociones disponibles

        if (rewards_filter && rewards_filter.length >= 1) {
            const rewardsList = rewards_filter.map((reward) => ({
                id: reward.reward?.id,
                label: reward.reward?.description,
                description: reward.reward?.program_id?.name,
                item: reward,
            }));
            const {confirmed, payload: selectedReward} = await this.popup.add(SelectionCustomPopup, {
                title: _t("Por favor seleccione una recompensa para %(name)s", {name: this.get_name_product_trigger(line)}),
                list: rewardsList,
            });

            if (confirmed) {
                await this.delete_lines_reward(selectedReward);
                return this._applyReward(
                    selectedReward.reward,
                    selectedReward.coupon_id,
                    selectedReward.potentialQty
                );
            }
        }
        return false;
    },

    get_name_product_trigger(line) {
        if (!line) {
            return "";
        }

        const id_to_search = line.reward_product_id;
        const product = this.pos.db.get_product_by_id(id_to_search);
        if (product) {
            return product.display_name || "";
        }
        return "";
    }
})