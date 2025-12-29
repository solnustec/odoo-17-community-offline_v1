/** @odoo-module **/

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";
import {PartnerDetailsEdit} from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {PopupGetApi} from "../../../../api_client_proassislife/static/src/js/popup";
import {useService} from "@web/core/utils/hooks";

patch(PartnerDetailsEdit.prototype, {
    setup() {
        super.setup(...arguments);
        this.accessToken = null; // Variable para almacenar el token
        this.contractData = null;
        this.popup = useService("popup");
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
            return data;
        } catch (error) {
            console.error("Error al obtener la información del contrato:", error);
            return null;
        }
    },

    async saveChanges() {
        const processedChanges = {};
        for (const [key, value] of Object.entries(this.changes)) {
            if (this.intFields.includes(key)) {
                processedChanges[key] = parseInt(value) || false;
            } else {
                processedChanges[key] = value;
            }
        }

        if (processedChanges.vat) {
            processedChanges.vat = processedChanges.vat.trim();
        }
        if (processedChanges.email) {
            processedChanges.email = processedChanges.email.trim();
        }
        if (processedChanges.mobile) {
            processedChanges.mobile = processedChanges.mobile.trim();
        }

        if (
            processedChanges.state_id &&
            this.pos.states.find((state) => state.id === processedChanges.state_id)
                .country_id[0] !== processedChanges.country_id
        ) {
            processedChanges.state_id = false;
        }

        // -----------------------------
        //  VALIDACIONES
        // -----------------------------

        // Nombre obligatorio
        if (!this.props.partner.name && !processedChanges.name || processedChanges.name === "") {
            return this.popup.add(ErrorPopup, {
                title: _t("A Customer Name Is Required"),
            });
        }

        // Cédula / identificación obligatoria
        if (!processedChanges.vat || processedChanges.vat === "") {
            return this.popup.add(ErrorPopup, {
                title: "Campo obligatorio",
                body: "La Identificación del cliente es obligatoria",
            });
        }

        // CORREO OBLIGATORIO
        if (!processedChanges.email || processedChanges.email.trim() === "") {
            return this.popup.add(ErrorPopup, {
                title: "Correo obligatorio",
                body: "Debe ingresar una dirección de correo electrónico para continuar.",
            });
        }

        // Validar formato email SOLO si tiene algo
        if (processedChanges.email && processedChanges.email.trim() !== "") {
            const emailRegex = /^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$/;
            if (!emailRegex.test(processedChanges.email)) {
                return this.popup.add(ErrorPopup, {
                    title: "Email Incorrecto",
                    body: _t("Por favor ingrese una dirección de correo válida."),
                });
            }
        }

        // Teléfono
        if (processedChanges.mobile && processedChanges.mobile.trim() !== "") {
            if (processedChanges.mobile.replace(/\D/g, "").length < 10) {
                return this.popup.add(ErrorPopup, {
                    title: "Número de teléfono incorrecto",
                    body: "El numero de teléfono debe tener 10 dígitos.",
                });
            }
        }

        // Validación tipo de identificación
        if (processedChanges.vat && processedChanges.l10n_latam_identification_type_id) {
            const vat = processedChanges.vat.trim();
            const vatLength = vat.length;
            const idType = processedChanges.l10n_latam_identification_type_id;
            const CEDULA = 5;
            const RUC = 4;
            const PASAPORTE = 6;
            const isNumeric = /^\d+$/.test(vat);

            if ((vatLength === 10 || vatLength === 13) && !isNumeric) {
                return this.popup.add(ErrorPopup, {
                    title: "Formato incorrecto",
                    body: "El número de identificación debe contener solo números.",
                });
            }
            if (vatLength === 10 && idType !== CEDULA) {
                return this.popup.add(ErrorPopup, {
                    title: "Tipo de identificación incorrecto",
                    body: "Para 10 dígitos, el tipo de identificación debe ser 'CÉDULA'.",
                });
            } else if (vatLength === 13 && idType !== RUC) {
                return this.popup.add(ErrorPopup, {
                    title: "Tipo de identificación incorrecto",
                    body: "Para 13 dígitos, el tipo de identificación debe ser 'RUC'.",
                });
            } else if (vatLength !== 10 && vatLength !== 13 && ![PASAPORTE].includes(idType)) {
                return this.popup.add(ErrorPopup, {
                    title: "Identificación incorrecta",
                    body: "Seleccione el tipo de identificación adecuado.",
                });
            }
        }

        processedChanges.id = this.props.partner.id || false;

        // -----------------------------
        //  CONSULTA A PROASSISLIFE
        // -----------------------------
        const accessToken = await this.fetchAccessToken();
        if (!accessToken) {
            return this.popup.add(ErrorPopup, {
                title: "Error de autenticación",
                body: "No se pudo obtener el token de acceso.",
            });
        }
        console.log("Token obtenido:", accessToken);
        let data = await this.fetchContractInfo(processedChanges.vat, accessToken);
        if (data?.datos?.length > 0) {
            this.contractData = data.datos;
            this.popup.add(PopupGetApi, {contractData: this.contractData});
        }

        this.props.saveChanges(processedChanges);
    },
});
