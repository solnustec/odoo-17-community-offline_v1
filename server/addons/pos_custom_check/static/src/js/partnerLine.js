/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {reactive, onWillStart} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {PartnerLine} from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {Order} from "@point_of_sale/app/store/models";
import {Orderline} from "@point_of_sale/app/store/models";
const {formatFloat} = require("@web/core/utils/numbers");

patch(PartnerLine.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.institutions = reactive({
            options: [],
            selected: "",  // Usar string vacío para consistencia con el option value=""
        });

        // Limpiar datos de institución al inicializar
        this.clearInstitutionData();
        this.loadInstitutions = this.loadInstitutions.bind(this);
        this.getAvailableAmount = this.getAvailableAmount.bind(this);
        this.onInstitutionChange = this.onInstitutionChange.bind(this);
        this.onSelectClick = this.onSelectClick.bind(this);

        onWillStart(async () => {
            await this.loadInstitutions();
        });
    },

    /**
     * Limpia todos los datos de institución del localStorage
     */
    clearInstitutionData() {
        localStorage.removeItem("credito");
        localStorage.removeItem("percentageInstitution");
        localStorage.removeItem("institutionId");
        localStorage.removeItem("institution_id_selected");
        localStorage.removeItem("result_institution_client");
        this.institutions.selected = "";
    },

    _getLoyaltyPointsRepr(loyaltyCard) {
        const program = this.pos.program_by_id[loyaltyCard.program_id];
        if (program && program.program_type === "ewallet") {
            return `${program.name}: ${this.env.utils.formatCurrency(loyaltyCard.balance)}`;
        }
        const balanceRepr = formatFloat(loyaltyCard.balance, {
            digits: [69, 2]
        });
        if (program?.portal_visible) {
            return `${balanceRepr} ${program.portal_point_name}`;
        }
        return ("%s Points", balanceRepr);
    },

    async loadInstitutions() {
        try {
            const result = await this.orm.read(
                "res.partner",
                [this.props.partner.id],
                ["institution_ids", "name"]
            );

            if (result && result.length > 0 && result[0].institution_ids.length > 0) {
                const institutions = await this.orm.read(
                    "institution.client",
                    result[0].institution_ids,
                    ["institution_id", "available_amount"]
                );

                const enrichedInstitutions = await Promise.all(
                    institutions.map(async (client) => {
                        const institutionDetails = await this.orm.read(
                            "institution",
                            [client.institution_id[0]],
                            ["type_credit_institution"]
                        );
                        return {
                            ...client,
                            type_credit_institution:
                                institutionDetails.length > 0
                                    ? institutionDetails[0].type_credit_institution
                                    : null,
                        };
                    })
                );

                const discountInstitutions = enrichedInstitutions.filter(
                    (inst) => inst.type_credit_institution === "discount"
                );

                this.institutions.options = discountInstitutions.map((inst) => ({
                    id: inst.institution_id[0],
                    name: inst.institution_id[1],
                    amount: inst.available_amount,
                }));
            } else {
                this.institutions.options = [];
            }

            // Usar string vacío para consistencia con el option value=""
            this.institutions.selected = "";
        } catch (error) {
            console.error("Error cargando instituciones:", error);
            this.institutions.options = [];
            this.institutions.selected = "";
        }

        this.render();
    },

    async loadInstitutionDetails(institutionId) {
        try {
            if (!institutionId || institutionId <= 0) {
                this.clearInstitutionData();
                return;
            }

            const institutionDetails = await this.orm.read(
                "institution",
                [institutionId],
                ["additional_discount_percentage", "id_institutions", "name"]
            );

            if (institutionDetails && institutionDetails.length > 0) {
                const percentageInstitution = institutionDetails[0];
                const idInstitutions = percentageInstitution.id_institutions;

                // Validar que id_institutions sea válido (no vacío, no solo ceros)
                if (!idInstitutions || idInstitutions === "000000000000" || parseInt(idInstitutions, 10) === 0) {
                    console.warn("Institution id_institutions is invalid:", idInstitutions);
                    this.clearInstitutionData();
                    return;
                }

                localStorage.setItem("percentageInstitution", JSON.stringify(percentageInstitution));
                localStorage.setItem("institutionId", JSON.stringify(idInstitutions));

                const porcentaje = percentageInstitution.additional_discount_percentage / 100;

                if (porcentaje > 0) {
                    this.applyDiscountToOrder(porcentaje);
                } else {
                    console.log("No discount applied.");
                }
            } else {
                this.clearInstitutionData();
            }
        } catch (error) {
            console.error("Error loading institution details:", error);
            this.clearInstitutionData();
        }
    },

    async getAvailableAmount(institutionId) {
        try {
            const result = await this.orm.searchRead(
                "institution.client",
                [
                    ["partner_id", "=", this.props.partner.id],
                    ["institution_id", "=", institutionId],
                ],
                ["available_amount"]
            );
            localStorage.setItem("result_institution_client", JSON.stringify(result));
            if (result && result.length > 0) {
                const availableAmount = result[0].available_amount;
                localStorage.setItem("credito", availableAmount)
                localStorage.setItem("institution_id_selected", institutionId)
                return availableAmount;
            } else {
                return null;
            }
        } catch (error) {
            console.error("Error al obtener el monto disponible:", error);
            return null;
        }
    },

    applyDiscountToOrder(porcentaje) {
        const currentOrder = this.pos.get_order();
        setTimeout(() => {
            currentOrder.orderlines.forEach(line => {
                // Solo si aún no lo habíamos guardado
//                if (!line.original_price) {
//                    line.original_price = line.get_unit_price();  // <- nuevo
//                }
                const discountedPrice = line.original_price * (1 - porcentaje);
                line.set_unit_price(discountedPrice);
            });
        }, 2000);
    },


    get_total_amount_order() {
        const order = this.pos.get_order()
        return order.get_total_with_tax() + order.get_rounding_applied();
    },

    onInstitutionChange(event) {
        event.stopPropagation();
        event.preventDefault();

        const value = event.target.value;
        // Validar que el valor sea un número válido y mayor a 0
        const parsedValue = value ? parseInt(value, 10) : null;
        const selectedId = (parsedValue && parsedValue > 0) ? parsedValue : "";
        this.institutions.selected = selectedId;

        if (selectedId) {
            this.loadInstitutionDetails(selectedId);
            this.getAvailableAmount(selectedId);
            if (this.pos.btnInstitution) {
                this.pos.btnInstitution.showButton();
            }
        } else {
            // Limpiar datos de institución cuando se deselecciona
            this.clearInstitutionData();
        }
    },

    onSelectClick(event) {
        event.stopPropagation();
        event.preventDefault();
    },
});

//patch(Order.prototype, {
//    add_product(product, options) {
////        const btn_inst = this.pos?.DeleteOrderLines;
////        if (btn_inst) btn_inst.reset_prices();
//        const res = super.add_product(...arguments);
//        return res;
//    }
//});


//patch(Orderline.prototype, {
//
//    setup() {
//        super.setup(...arguments);
//        this.original_price = this.get_unit_price();
//    },
//
//    set_quantity(quantity, keep_price = false) {
//        const res = super.set_quantity(...arguments);
//        return res;
//    }
//});
