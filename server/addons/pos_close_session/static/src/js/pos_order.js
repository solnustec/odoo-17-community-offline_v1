/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {Order} from "@point_of_sale/app/store/models";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
const { DateTime } = luxon;

patch(Order.prototype, {
    async pay() {
        const posSession = this.pos?.pos_session;
        const startAt = posSession?.start_at;

        if (posSession && startAt) {
            const sessionDate = DateTime
              .fromFormat(startAt, "yyyy-MM-dd HH:mm:ss", { zone: 'utc' })
              .setZone('America/Guayaquil');

            const now = DateTime.now().setZone('America/Guayaquil');
            const sameDate = sessionDate.hasSame(now, 'day');

            if(!sameDate){
                const {confirmed} = await this.env.services.popup.add(ConfirmPopup, {
                    title: "La fecha de la sesión es distinta a la de la orden",
                    body: "Debe cerrar la sesión primero antes de proceder.",
                });

                if (confirmed) {
                    const info = await this.pos.getClosePosInfo();
                    this.env.services.popup.add(ClosePosPopup, { ...info });
                }
            } else {
                return await super.pay(...arguments);
            }

        } else {
            return await super.pay(...arguments);
        }
    },
})