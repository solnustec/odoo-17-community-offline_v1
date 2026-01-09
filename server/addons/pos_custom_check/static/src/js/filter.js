/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {ProductsWidget} from "@point_of_sale/app/screens/product_screen/product_list/product_list";
import {onMounted, useState} from "@odoo/owl";

// Aplicar un parche al componente ProductsWidget con sintaxis OWL2
patch(ProductsWidget.prototype, {
    setup() {
        super.setup(...arguments); // OWL2: usa super.setup() en lugar de this._super()

        // Estado reactivo para filtros de marca y laboratorio
        this.filterState = useState({
            brands: [],
            laboratories: [],
            filteredProducts: null,
        });

        onMounted(() => {
            const posInstance = this.pos;
            if (!posInstance) {
                console.error("No se pudo acceder a la instancia del POS durante el montaje.");
            }
        });
    },

    async onBrandClick() {
        try {
            const brands = await this.env.services.orm.searchRead(
                "product.brand",
                [],
                ["id", "name"]
            );
            this.filterState.brands = brands;
        } catch (error) {
            console.error("Error al cargar las marcas:", error);
        }
    },

    async onLaboratoryClick() {
        try {
            const laboratories = await this.env.services.orm.searchRead(
                "product.laboratory",
                [],
                ["id", "name"]
            );
            this.filterState.laboratories = laboratories;
        } catch (error) {
            console.error("Error al cargar los laboratorios:", error);
        }
    },

    async onLaboratoryChange(event) {
        const selectedLaboratoryId = event.target.value;

        if (!selectedLaboratoryId) {
            this.filterState.filteredProducts = null;
        } else {
            await this.filterProducts([["laboratory_id", "=", parseInt(selectedLaboratoryId)]]);
        }
    },

    async onBrandChange(event) {
        const selectedBrandId = event.target.value;

        if (!selectedBrandId) {
            this.filterState.filteredProducts = null;
        } else {
            await this.filterProducts([["brand_id", "=", parseInt(selectedBrandId)]]);
        }
    },

    async filterProducts(domain) {
        try {
            const posInstance = this.pos;
            const products = await this.env.services.orm.searchRead("product.product", domain, ["id"]);
            const productIds = products.map((product) => product.id);
            const allProducts = Object.values(posInstance.db.product_by_id);
            this.filterState.filteredProducts = allProducts.filter((product) =>
                productIds.includes(product.id)
            );
            if (this.filterState.filteredProducts.length === 0) {
                window.alert("No hay productos que coincidan con esta búsqueda.");
            }
        } catch (error) {
            console.error("Error al filtrar productos:", error);
        }
    },

    // Nota: productsToDisplay está definido en pos_search_bar/patch_product_list.js
    // Este getter se integra con el sistema de filtrado
    getFilteredProductsByBrandLab() {
        return this.filterState?.filteredProducts || null;
    },
});
