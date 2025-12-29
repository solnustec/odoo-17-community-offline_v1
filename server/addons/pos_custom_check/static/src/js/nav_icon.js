/** @odoo-module **/

import {Component, useState} from "@odoo/owl";
import {Navbar} from "@point_of_sale/app/navbar/navbar";

export class NavSelect extends Component {
    static template = "custom_navbar_select.NavSelect";

    async setup() {
        super.setup();
        this.state = useState({
            brands: [], // Lista de marcas
            laboratories: [], // Lista de laboratorios
            products: [], // Lista de productos filtradosa
        });
    }

    async loadBrands() {
        try {
            const brands = await this.env.services.orm.searchRead(
                "product.brand",
                [],
                ["id", "name"]
            );
            this.state.brands = brands; // Actualiza la lista de marcas
        } catch (error) {
            console.error("Error al cargar las marcas:", error);
        }
    }

    async loadLaboratories() {
        try {
            const laboratories = await this.env.services.orm.searchRead(
                "product.laboratory",
                [],
                ["id", "name"]
            );
            this.state.laboratories = laboratories; // Actualiza la lista de laboratorios
        } catch (error) {
            console.error("Error al cargar los laboratorios:", error);
        }
    }

    async loadProductsByBrand(brandId) {
        try {
            const products = await this.env.services.orm.searchRead(
                "product.template",
                [["brand_id", "=", parseInt(brandId)]], // Filtro por marca
                ["id", "name"]
            );
            console.log(`Productos filtrados por marca (ID: ${brandId}):`, products);
            this.state.products = products; // Actualiza la lista de productos
        } catch (error) {
            console.error("Error al cargar productos por marca:", error);
        }
    }

    async loadProductsByLaboratory(laboratoryId) {
        try {
            const products = await this.env.services.orm.searchRead(
                "product.template",
                [["laboratory_id", "=", parseInt(laboratoryId)]], // Filtro por laboratorio
                ["id", "name"]
            );
            console.log(
                `Productos filtrados por laboratorio (ID: ${laboratoryId}):`,
                products
            );
            this.state.products = products; // Actualiza la lista de productos
        } catch (error) {
            console.error("Error al cargar productos por laboratorio:", error);
        }
    }

    async handleBrandSelection(event) {
        const selectedBrandId = event.target.value;
        console.log("Marca seleccionada:", selectedBrandId);
        await this.loadProductsByBrand(selectedBrandId);
    }

    async handleLaboratorySelection(event) {
        const selectedLaboratoryId = event.target.value;
        console.log("Laboratorio seleccionado:", selectedLaboratoryId);
        await this.loadProductsByLaboratory(selectedLaboratoryId);
    }
}

// Agregar NavSelect como componente del Navbar
Navbar.components = {...Navbar.components, NavSelect};
