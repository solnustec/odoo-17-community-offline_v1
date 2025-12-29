/** @odoo-module **/
import {Component, useState, onWillStart, onWillUpdateProps, onWillRender} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {PopupHistoriClient} from "./popup_history_client";

export class DeleteOrderLines extends Component {
    static template = "product_parent.OrderLineClearALL";

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.state = useState({
            institutions: [],
            selected: "",  // Usar string vacío para consistencia con el option value=""
            currentPartnerId: null  // Para detectar cambios de partner
        });
        this.pos.DeleteOrderLines = this;

        // Ejecutar al inicio del componente
        onWillStart(() => {
            this.reset_prices();
            this.clearInstitutionData();
            this.loadInstitutions();
        });

        // Actualizar instituciones cuando cambien las props
        onWillUpdateProps(() => {
            this.clearInstitutionData();
            this.loadInstitutions();
        });

        // Detectar cambios de partner en cada render
        onWillRender(() => {
            const order = this.pos.get_order();
            const currentPartnerId = order?.partner?.id || null;

            // Si el partner cambió, recargar instituciones
            if (this.state.currentPartnerId !== currentPartnerId) {
                this.state.currentPartnerId = currentPartnerId;
                this.clearInstitutionData();
                this.loadInstitutions();

                // Forzar actualización visual del select
                this._forceSelectReset();
            }
        });
    }

    /**
     * Fuerza el reset visual del select element
     */
    _forceSelectReset() {
        // Usar setTimeout para asegurar que el DOM se haya actualizado
        setTimeout(() => {
            const selectElement = document.getElementById('inst-select');
            if (selectElement) {
                selectElement.value = "";
            }
        }, 0);
    }

    /**
     * Limpia todos los datos de institución del localStorage y el estado
     */
    clearInstitutionData() {
        localStorage.removeItem("percentageInstitution");
        localStorage.removeItem("institutionId");
        localStorage.removeItem("institution_id_selected");
        this.state.selected = "";
    }

    async onClick() {
        const {confirmed} = await this.popup.add(PopupHistoriClient);
    }

    async veriffy_especial_day_discount() {
        // función para verificar si hay un descuento especial por día
        let today = new Date().getDay(); // 0=Dom,6=Sáb
        today = today === 0 ? 6 : today - 1;

        const promotions = await this.orm.searchRead("promotions_by_day.promotions_by_day", [["weekday", "=", today],], ["discount_percent", "weekday", "active"]);
        if (promotions.length > 0 && promotions[0].active) {
            return true
        }
    }


    async loadInstitutions() {
        try {
            const promotions = await this.veriffy_especial_day_discount();
            if (promotions) {
                // si hay un descuento especial, no cargar instituciones
                this.state.institutions = [];
                this.state.selected = "";
                return;
            }

            const order = this.pos.get_order();
            const partnerId = order?.partner?.id;
            if (!partnerId) {
                this.state.institutions = [];
                this.state.selected = "";
            } else {
                const result = await this.orm.read(
                    "res.partner", [partnerId], ["institution_ids"]
                );
                const institution_ids = result?.[0]?.institution_ids || [];
                if (!institution_ids.length) {
                    this.state.institutions = [];
                    this.state.selected = "";
                } else {
                    const clients = await this.orm.read(
                        "institution.client",
                        institution_ids,
                        ["institution_id", "available_amount"]
                    );
                    const enriched = await Promise.all(
                        clients.map(async (c) => {
                            const [inst] = await this.orm.read(
                                "institution",
                                [c.institution_id[0]],
                                ["type_credit_institution"]
                            );
                            return {
                                id: c.institution_id[0],
                                name: c.institution_id[1],
                                amount: c.available_amount,
                                type: inst.type_credit_institution,
                            };
                        })
                    );
                    this.state.institutions = enriched.filter(i => i.type === "discount");
                }
            }
        } catch (e) {
            console.error("Error cargando instituciones:", e);
            this.state.institutions = [];
        }
        // Asegurar que el select se resetee cuando no hay instituciones
        if (!this.state.institutions.length) {
            this.state.selected = "";
        }
    }

    onInstitutionChange(ev) {
        const value = ev.target.value;
        // Validar que el valor sea un número válido y mayor a 0
        const parsedValue = value ? parseInt(value, 10) : null;
        this.state.selected = (parsedValue && parsedValue > 0) ? parsedValue : "";

        if (this.state.selected) {
            this.loadInstitutionDetails(this.state.selected);
        } else {
            // Limpiar datos de institución cuando se deselecciona
            this.clearInstitutionData();
            this.reset_prices();
        }
    }

    reset_prices() {
        const order = this.pos.get_order();
        if (order) {
            order.orderlines.forEach((line) => {
                if (line.original_price !== undefined) {
                    line.set_unit_price(line.original_price);
                }
            });
//            order._updateRewards();
        }
    }

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
                    this.reset_prices();
                    console.log("No discount applied.");
                }
            } else {
                this.clearInstitutionData();
            }
        } catch (error) {
            console.error("Error loading institution details:", error);
            this.clearInstitutionData();
        }
    }

    applyDiscountToOrder(porcentaje) {
        const currentOrder = this.pos.get_order();
        currentOrder.orderlines.forEach(line => {
            if (!line.original_price) {
                line.original_price = line.get_unit_price();
            }
            const discountedPrice = line.original_price * (1 - porcentaje);
            line.set_unit_price(discountedPrice);
        });
//        currentOrder._updateRewards();
    }

    resetOrderState() {
        this.reset_prices();
        this.clearInstitutionData();
        this.loadInstitutions();
    }
}

// Sobrescribir validateOrder en ProductScreen para restablecer el estado
import {patch} from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    async validateOrder(isForce = false) {
        await super.validateOrder(isForce);
        if (this.pos.DeleteOrderLines) {
            this.pos.DeleteOrderLines.resetOrderState();
        }
    }
});

// Registramos el botón en la pantalla de productos
ProductScreen.addControlButton({
    component: DeleteOrderLines,
    condition: () => true,
});