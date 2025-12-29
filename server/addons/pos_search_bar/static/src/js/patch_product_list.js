/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {ProductsWidget} from "@point_of_sale/app/screens/product_screen/product_list/product_list";
import {_t} from "@web/core/l10n/translation";
import OfflineErrorPopup from "@point_of_sale/app/errors/popups/offline_error_popup";
import {ConnectionAbortedError, ConnectionLostError,} from "@web/core/network/rpc_service";
import {onMounted, onWillUnmount, useState} from "@odoo/owl";

import {filterProductsClientSide, parseSearchInput,} from "../utils/product_search_utils";

/** --- OWL2 Patch --- **/

patch(ProductsWidget.prototype, {
    setup() {
        super.setup(...arguments);

        // Estado reactivo para forzar re-render cuando cambie el stock
        this.stockState = useState({ lastUpdate: 0 });

        // Handler para evento de actualización de stock
        this._onStockUpdated = (event) => {
            console.log("📦 ProductsWidget recibió evento pos-stock-updated:", event.detail);
            // Incrementar el contador para forzar re-render
            this.stockState.lastUpdate = Date.now();
            // Forzar actualización de la lista
            this.render();
        };

        onMounted(() => {
            // Escuchar eventos de actualización de stock
            document.addEventListener('pos-stock-updated', this._onStockUpdated);
            console.log("✅ ProductsWidget escuchando eventos pos-stock-updated");
        });

        onWillUnmount(() => {
            // Limpiar el listener al desmontar
            document.removeEventListener('pos-stock-updated', this._onStockUpdated);
        });
    },


    async loadProductFromDB() {
        this.state.isLoading = true;
        const {searchProductWord} = this.pos;

        if (!searchProductWord) {
            this.state.isLoading = false;
            return;
        }

        const cleanedProductWord = searchProductWord.replace(/;product_tmpl_id:\d+$/, '');

        // Detectar si es solo nimeros para el codigo de baras
        const isLikelyBarcode = /^\d+$/.test(cleanedProductWord.trim());
        let domain;
        if (isLikelyBarcode) {
            domain = [
                "&",
                "&",
                ["available_in_pos", "=", true],
                ["sale_ok", "=", true],
                ["detailed_type", "=", "product"],
                "|",
                "|",
                "|",
                ["barcode", "=", cleanedProductWord],
                ["barcode", "ilike", cleanedProductWord],
                ["default_code", "ilike", cleanedProductWord],
                ["multi_barcode_ids.product_multi_barcode", "ilike", cleanedProductWord],
            ];
        } else {
            const terms = cleanedProductWord.trim().split(/\s+/).filter(Boolean);
            const nameClauses = terms.map(t => ["name", "ilike", `%${t}%`]);
            const nameAndPrefix = new Array(Math.max(0, nameClauses.length - 1)).fill("&");
            const nameBlock = [...nameAndPrefix, ...nameClauses];

            const otherClauses = [
                ["default_code", "ilike", cleanedProductWord],
                ["barcode", "ilike", cleanedProductWord],
            ];

            const totalOrItems = 1 + otherClauses.length;
            const orPrefix = new Array(Math.max(0, totalOrItems - 1)).fill("|");

            domain = [
                "&",
                "&",
                ["available_in_pos", "=", true],
                ["sale_ok", "=", true],
                ["detailed_type", "=", "product"],
                ...orPrefix,
                ...nameBlock,
                ...otherClauses,
            ];
        }

        try {
            const limit = 20;
            const ProductIds = await this.orm.call(
                "product.product",
                "search",
                [domain],
                {
                    offset: this.state.currentOffset,
                    limit: limit,
                }
            );

            if (ProductIds.length) {
                await this.pos._addProducts(ProductIds, false);
            }

            this.updateProductList();
            this.state.isLoading = false;
            return ProductIds;

        } catch (error) {
            this.state.isLoading = false;

            if (error instanceof ConnectionLostError || error instanceof ConnectionAbortedError) {
                return this.popup.add(OfflineErrorPopup, {
                    title: _t("Network Error"),
                    body: _t(
                        "Product is not loaded. Tried loading the product from the server but there is a network error."
                    ),
                });
            } else {
                throw error;
            }
        }
    },

    // get productsToDisplay() {
    //     if (!this.pos || !this.pos.db) {
    //         return [];
    //     }
    //
    //     const terms = parseSearchInput(this.pos.searchProductWord || "");
    //     const allProducts = Object.values(this.pos.db.product_by_id || {});
    //
    //     const tipProductId = this.pos.config?.tip_product_id;
    //     const filtered = terms.length
    //         ? filterProductsClientSide(allProducts, terms, tipProductId ? [tipProductId] : [])
    //         : allProducts.filter((p) => !tipProductId || p.id !== tipProductId);
    //     filtered.filter(product => product.type === "product" && product.lst_price > 0)
    //     return filtered.slice().sort((a, b) => {
    //         const av = Number(a.pos_stock_available) || 0;
    //         const bv = Number(b.pos_stock_available) || 0;
    //         return bv - av;
    //     });
    // },
    get productsToDisplay() {
        if (!this.pos || !this.pos.db) {
            return [];
        }

        const terms = parseSearchInput(this.pos.searchProductWord || "");
        const allProducts = Object.values(this.pos.db.product_by_id || {});
        const tipProductId = this.pos.config?.tip_product_id;

        let list = terms.length
            ? filterProductsClientSide(allProducts, terms, tipProductId ? [tipProductId] : [])
            : allProducts;

        // Filtrar tipo, precio y tip product en una sola pasada
        list = list.filter(p => {
            // TODO: actualmente se revisa que tenga mas de una categoria cargada aqui.
            // Esto validacion sirve para cargar los productos con costo 0 pero que se muestren en el punto de venta
            const inSpecialCategory = Array.isArray(p.pos_categ_ids) && p.pos_categ_ids.length > 0;

            // Si está en la categoría especial -  mostrarlo SIEMPRE
            if (inSpecialCategory) {
                return true;
            }

            // Regla normal: tipo product y precio > 0
            return (
                (!tipProductId || p.id !== tipProductId) &&
                p.type === "product" &&
                p.lst_price > 0
            );

        })

        // Precomputar stock numérico para evitar conversiones repetidas durante el sort
        const withStock = list.map(p => ({product: p, stock: Number(p.pos_stock_available) || 0}));

        withStock.sort((a, b) => b.stock - a.stock);

        return withStock.map(item => item.product);
    },
    async onSearchInputKeyUp(event) {
        if (event.key === 'Enter') {
            await this.onPressEnterKey();
        }
    },


    async onPressEnterKey() {
        const {searchProductWord} = this.pos;
        if (!searchProductWord) {
            return;
        }
        if (this.state.previousSearchWord !== searchProductWord) {
            this.pos.db.product_by_id = {};
            this.state.currentOffset = 0;
        }
        const result = await this.loadProductFromDB();
        const cleanedProductWord = searchProductWord.replace(/;product_tmpl_id:\d+$/, '');
        if (result.length > 0) {
            this.notification.add(
                _t('%s product(s) found for "%s".', result.length, cleanedProductWord),
                3000
            );
        } else {
            this.notification.add(_t('No more product found for "%s".', cleanedProductWord), 3000);
        }
        if (this.state.previousSearchWord === searchProductWord) {
            this.state.currentOffset += result.length;
        } else {
            this.state.previousSearchWord = searchProductWord;
            this.state.currentOffset = result.length;
        }
    },

    updateProductList() {
        this.render();
    },
});