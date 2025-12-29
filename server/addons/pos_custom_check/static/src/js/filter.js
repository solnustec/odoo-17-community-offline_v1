/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {ProductsWidget} from "@point_of_sale/app/screens/product_screen/product_list/product_list";

// Aplicar un parche al componente ProductsWidget
patch(ProductsWidget.prototype, {
    mounted() {
        this._super(...arguments); // Llama al método original correctamente
        const posInstance = this.pos;

        if (posInstance) {
            this.filteredProducts = null; // Inicializa la lista de productos filtrados
            this.state = {
                brands: [], // Lista de marcas
                laboratories: [], // Lista de laboratorios
            };
        } else {
            console.error("No se pudo acceder a la instancia del POS durante el montaje.");
        }
    },
    async onBrandClick() {
        try {
            const brands = await this.env.services.orm.searchRead(
                "product.brand",
                [],
                ["id", "name"]
            );
            this.state.brands = brands;
            this.render();
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
            this.state.laboratories = laboratories;
            this.render();
        } catch (error) {
            console.error("Error al cargar los laboratorios:", error);
        }
    },

    async onLaboratoryChange(event) {
        const selectedLaboratoryId = event.target.value;

        if (!selectedLaboratoryId) {
            this.filteredProducts = null;
        } else {
            await this.filterProducts([["laboratory_id", "=", parseInt(selectedLaboratoryId)]]);
        }
        this.render();
    },

    async onBrandChange(event) {
        const selectedBrandId = event.target.value;

        if (!selectedBrandId) {
            this.filteredProducts = null;
        } else {
            await this.filterProducts([["brand_id", "=", parseInt(selectedBrandId)]]);
        }
        this.render();
    },

    async filterProducts(domain) {
        try {
            const posInstance = this.pos;
            this.filteredProducts = [];
            const products = await this.env.services.orm.searchRead("product.product", domain, ["id"]);
            const productIds = products.map((product) => product.id);
            const allProducts = Object.values(posInstance.db.product_by_id);
            this.filteredProducts = allProducts.filter((product) =>
                productIds.includes(product.id)
            );
            this.render();
            if (this.filteredProducts.length === 0) {
                window.alert("No hay productos que coincidan con esta búsqueda.");
            }
        } catch (error) {
            console.error("Error al filtrar productos:", error);
        }
    },

    get productsToDisplay() {
        const posInstance = this.pos;

        // Si hay productos filtrados por marca/laboratorio, tomar esos
        let filteredList = Array.isArray(this.filteredProducts) ? this.filteredProducts : null;

        // Si hay una búsqueda activa (searchProductWord), aplicar el filtro adicional
        if (this.pos.searchProductWord.trim() !== "") {
            const searchWord = this.pos.searchProductWord.trim().toLowerCase();

            // Si hay productos filtrados, buscar dentro de esos
            if (filteredList) {
                filteredList = filteredList.filter((product) =>
                    product.display_name.toLowerCase().includes(searchWord) ||
                    (product.default_code && product.default_code.toLowerCase().includes(searchWord)) ||
                    (product.barcode && product.barcode.includes(searchWord))
                );
            } else {
                // Si no hay productos filtrados, buscar en todos los productos de la categoría seleccionada
                filteredList = posInstance.db.search_product_in_category(this.selectedCategoryId, searchWord);
            }
        }

        // Si no hay búsqueda activa ni filtrado, retornar productos por categoría seleccionada
        if (!filteredList) {
            filteredList = posInstance.db.get_product_by_category(this.selectedCategoryId);
        }

        // Ordenar alfabéticamente antes de retornar
        return filteredList.sort((a, b) => a.display_name.localeCompare(b.display_name));
    },

});

