/** @odoo-module **/
import {patch} from "@web/core/utils/patch";
import {useState, onWillStart, useRef} from "@odoo/owl";
import {ProductInfoPopup} from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";

patch(ProductInfoPopup.prototype, {
    setup() {
        super.setup();

        this.state = useState({
            searchQuery: "",
            selectedCity: "",
            cities: [],
            warehouses: [],
            filteredWarehouses: [],
            loading: false,
        });

        this.inputRef = useRef("searchWarehouse");

        // Cargar ciudades y almacenes antes de renderizar
        onWillStart(async () => {
            await this.getCities();
            const warehouses = await this._fetchWarehouses(); // sin ciudad
            this.state.warehouses = warehouses;
            this._applyFilters();
        });
    },

    async _fetchWarehouses(city = "") {
        try {
            this.state.loading = true;
            const productId = this.props.product.id;
            const cityQuery = city ? `&city=${encodeURIComponent(city)}` : "";
            const url = `/pos/warehouses?product_id=${productId}${cityQuery}`;

            const resp = await fetch(url, { method: "GET", headers: { "Content-Type": "application/json" } });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);

            const data = await resp.json();
            if (data.status !== "success") throw new Error(data.message || "Error desconocido");

            // NO filtramos por available_quantity, para mostrar también ceros
            const rows = (data.warehouses || []).map((w) => ({
                id: w.id,
                name: w.warehouse_name || "Sin nombre",
                available_quantity: Number(w.available_quantity ?? 0),
                city: (w.city || "").trim(),
            }));
            return rows;
        } catch (error) {
            console.error("Error al obtener almacenes:", error);
            return [];
        } finally {
            this.state.loading = false;
        }
    },

    async getCities() {
        try {
            const response = await fetch(`/api/warehouses/cities`, {
                method: "GET",
                headers: { "Content-Type": "application/json" },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            const data = await response.json();
            if (data.status !== "ok") throw new Error(data.message || "Error desconocido");

            this.state.cities = (data.results || [])
                .filter((c) => c && c.name)
                .map((c) => ({ value: c.name, label: c.name }))
                .sort((a, b) => a.label.localeCompare(b.label));
        } catch (error) {
            console.error("Error al obtener ciudades:", error);
            this.state.cities = [];
        }
    },

    filterWarehouses(event) {
        this.state.searchQuery = (event?.target?.value || "").toLowerCase();
        this._applyFilters();
    },

    async onCityChange(ev) {
        this.state.selectedCity = ev.target.value || "";
        const warehouses = await this._fetchWarehouses(this.state.selectedCity);
        this.state.warehouses = warehouses;
        this._applyFilters();
    },

    _applyFilters() {
        const q = (this.state.searchQuery || "").toLowerCase();
        const city = (this.state.selectedCity || "").toLowerCase();

        this.state.filteredWarehouses = this.state.warehouses.filter((w) => {
            const name = (w.name || "").toLowerCase();
            const qtyStr = String(w.available_quantity ?? "");
            const wCity = (w.city || "").toLowerCase();

            const matchText = !q || name.includes(q) || qtyStr.includes(q);
            const matchCity = !city || wCity === city;
            return matchText && matchCity;
        });
    },
});
