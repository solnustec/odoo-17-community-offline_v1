/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {PartnerLine} from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import {useService} from "@web/core/utils/hooks";
import {PopupGetApi} from "./popup";
import {Order} from "@point_of_sale/app/store/models";

patch(PartnerLine.prototype, {
    setup() {
        this.popup = useService("popup");
        this.notification = useService("notification");
        super.setup();
        this.isFetchingToken = false;
        this.accessToken = null;
        this.contractData = null;
        this.isLoading = false;
        localStorage.removeItem("result_institution_client")
        localStorage.removeItem("percentageInstitution")
        localStorage.removeItem("institutionId")
        localStorage.removeItem("institution_id_selected")
        const originalOnClick = this.props.onClickPartner;
        this.props.onClickPartner = async (partner) => {
            const get_institutions = await this.orm.call(
                "institution.client",
                "get_institutions_by_partner",
                [partner.id]
            );
            if (get_institutions.length > 0) {
                localStorage.setItem("result_institution_client", JSON.stringify(get_institutions))
            } else {
                localStorage.removeItem("result_institution_client")
            }

            if (this.props.partner !== this.props.selectedPartner) {
                this.isLoading = true;
                this.notification.add("Cargando datos, por favor espere...", {
                    type: "info",
                });

                if (!this.isFetchingToken && !this.accessToken) {
                    this.isFetchingToken = true;
                    this.accessToken = await this.fetchAccessToken();
                    this.isFetchingToken = false;
                }

                const contractInfo = await this.fetchContractInfo(partner.vat, this.accessToken);

                this.isLoading = false;

                if (contractInfo?.dato?.length > 0) {
                    this.contractData = contractInfo.dato;
                    this.popup.add(PopupGetApi, {contractData: this.contractData});
                }
            }

            if (originalOnClick) {
                originalOnClick(partner);
            }
        };
        this.reset_prices()
    },

    reset_prices() {
        this.pos.get_order().orderlines.forEach((line) => {
            line.set_unit_price(line.price_original);
        });
        this.pos.get_order()._updateRewards();
    },

    async fetchAccessToken() {
        try {
            const response = await fetch("/api/get_token", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({}),
            });

            if (!response.ok) throw new Error(`Error: ${response.status} - ${response.statusText}`);
            const data = await response.json();

            return data?.result?.access_token || null;
        } catch (error) {
            console.error("Error al obtener el token:", error);
            return null;
        }
    },

    async fetchContractInfo(cedula, token) {
        try {
            const url = `https://proassisapp.com/proassislife/servicios/cuxibamba/obtenerContratoCoberturaV2/${cedula}`;
            const response = await fetch(url, {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
            });

            if (!response.ok) throw new Error(`Error: ${response.status} - ${response.statusText}`);
            const data = await response.json();
            console.log(data)
            return data;
        } catch (error) {
            console.error("Error al obtener la información del contrato:", error);
            return null;
        }
    },
});

patch(Order.prototype, {
    set_total(newTotal) {
        const currentTotal = this.get_total_with_tax();

        if (currentTotal <= 0) {
            console.error("El total actual no puede ser 0 o negativo.");
            return;
        }
        const factor = newTotal / currentTotal;

        if (this.orderlines && this.orderlines.length > 0) {
            this.orderlines.forEach((line) => {
                line.set_unit_price(line.price_original)
            });

        } else {
            console.error("No hay líneas en la orden para ajustar.");
        }
    },
});