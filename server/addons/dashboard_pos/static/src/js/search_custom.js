/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class CustomFilter extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.nameService = useService("name");
    }

    async onFilterChange(filterType, value) {
        // Lógica para manejar cambios en los filtros
        const domain = this.buildDomain(filterType, value);
        const results = await this.rpc.query({
            model: "pos.order", // Cambia al modelo que necesites
            method: "search_read",
            args: [domain],
            kwargs: {
                fields: ["name"],
            },
        });
        this.props.onFilterChange(results); // Enviar resultados al componente padre
    }

    buildDomain(filterType, value) {
        // Construir el dominio según el tipo de filtro
        switch (filterType) {
            case "text":
                return [["name", "ilike", value]];
            default:
                return [];
        }
    }
}

CustomFilter.template = "dashboard_pos.PosDashboard";