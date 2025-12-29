/** @odoo-module **/

import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

patch(PartnerListScreen.prototype, {
    setup() {
        super.setup();
        this.state.isLoadingSearch = false;
        this.popup = this.env.services.popup;
        this.ui = useService("ui");

        onMounted(() => {
            const inputEl = this.searchWordInputRef?.el;
            if (inputEl) {
                this._onEnter = this._checkEnterKey.bind(this);
                inputEl.addEventListener("keydown", this._onEnter);
            }
        });

        onWillUnmount(() => {
            const inputEl = this.searchWordInputRef?.el;
            if (inputEl && this._onEnter) {
                inputEl.removeEventListener("keydown", this._onEnter);
            }
        });
    },

    async _onPressEnterKey() {
        if (this.state.isLoadingSearch || !this.state.query) return;
        this.state.isLoadingSearch = true;
        this.ui.block();

        try {
            const start = Date.now();
            const result = await this.searchPartner();
            const elapsed = Date.now() - start;
            if (elapsed < 150) await new Promise((res) => setTimeout(res, 150 - elapsed));

            if (!result?.length) {
                const { confirmed } = await this.popup.add(ConfirmPopup, {
                    title: _t("Sin resultados"),
                    body: _t("No se encontraron clientes que coincidan con tu búsqueda."),
                    confirmText: _t("Crear Cliente"),
                    cancelText: _t("Cancelar"),
                });

                if (confirmed) {
                    const createButton = document.querySelector('.new-customer');
                    if (createButton) {
                        createButton.click();
                    }
                }
            }

        } catch (error) {
            console.error("🔴 Error durante la búsqueda:", error);
        } finally {
            this.state.isLoadingSearch = false;
            this.ui.unblock();
        }
    },

    _checkEnterKey(e) {
        if (e.key === "Enter") this._onPressEnterKey();
    },

    async getNewPartners() {
        const limit = 30;
        const query = (this.state.query || "").trim();

        if (!query || query.length < 3) return [];

        let domain = [["type", "=", "contact"]];
        try {
            if (/^[0-9]+$/.test(query)) {
                domain.push(["vat", "ilike", query + "%"]);
            } else {
                const words = query.split(/\s+/);
                words.forEach((w) => domain.push(["name", "ilike", w + "%"]));
            }

            const res = await this.orm.silent.call(
                "pos.session",
                "get_pos_ui_res_partner_by_params",
                [
                    [odoo.pos_session_id],
                    {
                        domain,
                        limit,
                        offset: this.state.currentOffset || 0,
                        order: "name ASC",
                    },
                ]
            );
            return res || [];
        } catch (error) {
            console.error("Error en búsqueda:", error);
            return [];
        }
    },
});
