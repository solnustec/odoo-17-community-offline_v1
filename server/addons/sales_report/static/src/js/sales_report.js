/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onPatched, onWillStart, onWillUnmount, useState, onRendered, onMounted} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {ProductDetailsModal} from "./product_details_modal";
import {RecordSelector} from "@web/core/record_selectors/record_selector";
import {GoogleSheetModal} from "./google_sheet_modal";

const actionRegistry = registry.category("actions");
const _inMemoryCache = {};

export class SalesReport extends Component {
    static components = {ProductDetailsModal, RecordSelector, GoogleSheetModal};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.user = useService("user");
        this.notification = useService("notification");
        this.state = useState({
            isSorted: false,
            isSortedReab: false,
            range_active: false,
            sortColumn: null,
            sortDirection: null, // 'asc', 'desc', or null
            is_promotion_user: false,
            is_purchase_admin: false,
            isfilterWarehouse: false,
            isSortedWarehouse: false,
            offset: 0,
            product_code: "",
            extra_long_codes: "",
            short_codes: "",
            loading: false,
            error: {
                status: false,
                message: "",
            },
            product_query: "",
            // modo de busca: 'product' (por defecto) ou 'laboratory'
            search_mode: 'product',
            product_sales_priority: [],
            lastPurchasesByProduct: [],
            selectedBrand: false,
            selectedLaboratory: false,
            products: [],
            base_products_filtered: [],
            products_filtered: [],
            product_warehouse_summary: [],
            product_totals: {},
            laboratory_id: null,
            brand_id: null,
            brands: [],
            laboratories: [],
            // Filtro global por bodega
            selectedWarehouse: false,
            selected_global_warehouse_id: null,
            warehouseOptions: [],
            // Estado para búsqueda global por producto con paginación
            product_global_search_active: false,
            products_limit: 50,
            products_next_offset: 0,
            products_has_more: false,
            products_loading_more: false,
            labs_has_more: false,
            labs_next_offset: 0,
            labs_limit: 80,
            labs_loading_more: false,
            warehouses: [],
            warehouse_id: null,
            warehouse_query: "",
            //     anteriores
            lastPurchaseOrders: [],
            // Filtro de periodo para órdenes de compra: 'day', 'month', 'year'
            purchaseOrderPeriodFilter: 'day',
            selectedProductDetails: {},
            showProductModal: false,
            selected_warehouse_id: null,
            cart: [],
            selected_provider_id: null,
            selected_product_id: null,
            selected_laboratory_id: null,
            selected_brand_id: null,
            selected_laboratory_row_id: null,
            query: null,
            // Modo edición de orden de compra
            isEditingOrder: false,
            // Cache para imágenes de productos cargadas
            productImagesCache: new Map(),
            // Tooltip de imagen
            imageTooltip: null,
            hoverTimeout: null,
            cartProductData: {
                product: null,
                quantity: 1,
                discount: 16.66,
                total: 0,
                price_unit: null,
                price_box: null,
                freeProductQuantity: 0,
            },
            modalOpen: false,
            showCartModal: false,
            cartModalMinimized: false,
            isOpenGoogleModal: false,
            googleSheetData: {},
            // Modal de warning para múltiples marcas
            showMultiBrandWarning: false,
            cartBrands: [],
            selectedBrandsToRemove: [],
            // Datos de ventas del día actual
            today_sales_summary: [],
            today_sales_loading: false,
            today_sales_has_more: false,
            today_sales_next_offset: 0,
            today_sales_total_count: 0,
            today_sales_date_from: null,
            today_sales_date_to: null,
        });
        this.closeModal = () => {
            this.state.modalOpen = false;
        };
        this.closeCartModal = () => {
            this.state.showCartModal = false;
        };
        this.openModal = async (product_id) => {
            this.state.selected_product_id = product_id
            this.state.selectedProductDetails = this.state.products_filtered.find(
                (p) => p.product_id === product_id
            );
            this.state.modalOpen = true;
            this.state.lastPurchases = await this.orm.call('product.product', 'get_complete_purchase_history', [product_id, 5, 0]);
            this.state.purchaseHistoryOffset = 5;
            this.state.hasMorePurchases = true;
            this.state.selected_product_id = product_id;
            await this.selectProduct(product_id);
        };

        onWillStart(async () => {
            // Cargar carrito desde localStorage al inicializar
            this.loadCartFromStorage();
            await this.get_brands();
            await this.get_laboratories();
            await this.get_warehouses();

            await this.google_spreadsheet_api_init();
            this.state.is_promotion_user = await userInGroupByName(this.orm, this.user, 'Promociones Admin', 'Punto de venta');
            this.state.is_purchase_admin = await userInGroupByName(this.orm, this.user, 'Administrador', 'Compra');

        });
        onMounted(async () => {
            await this.loadTodaySalesSummary(100, 0);
            await this.fetchLastPurchaseOrders();
        });
        onPatched(async () => {
            //     aqui va el coneteino  de scroll para cargar mas datos;
            await this.setupScrollListener();

        });


        onWillUnmount(() => {

            // Limpar listener de scroll ao destruir o componente
            if (this.scrollListener) {
                const container = this.__owl__.refs.container;
                if (container) {
                    container.removeEventListener('scroll', this.scrollListener);
                }
                this.scrollListener = null;
            }
        });
        this.end_date = new Date().toISOString().split("T")[0];
        this.start_date = new Date(new Date().setMonth(new Date().getMonth() - 1)).toISOString().split("T")[0];
        this.onProductUpdated = (payload) => {
            /*
            * funcion para actualizar el descuento del producto en el reporte
            * */
            const idNum = Number(payload.product_id);
            if (Number.isNaN(idNum)) return;
            this.state.products_filtered = this.state.products_filtered.map(p =>
                Number(p.product_id) === idNum
                    ? {...p, discount: payload.effective_discount_percentage ?? payload.discount_percentage}
                    : p
            );
            this.state.modalOpen = false;
        };

        async function userInGroupByName(orm, user, groupName, category_id) {
            const groups = await orm.call('res.groups', 'search_read', [
                [['name', '=', groupName], ['category_id', '=', category_id]],
                ['users']
            ]);
            if (!groups || !groups.length) return false;
            const users = groups[0].users || [];
            return users.includes(user.userId);
        }

        this.handleGoogleModalClose = async () => {
            this.state.googleSheetData = {}
            this.state.isOpenGoogleModal = false;
        }

    }

    async google_spreadsheet_api_init() {
        this.state.google_spreadsheet_url = await this.orm.call("product.warehouse.sale.summary", "get_google_spreadsheet_api_key", []);
    }

    /**
     * Carga el resumen de ventas para un rango de fechas
     * @param {number} limit - Límite de registros a cargar (default: 50)
     * @param {number} offset - Offset para paginación (default: 0)
     * @param {string|null} dateFrom - Fecha inicio (YYYY-MM-DD) o null para hoy
     * @param {string|null} dateTo - Fecha fin (YYYY-MM-DD) o null para hoy
     */
    async loadTodaySalesSummary(limit = 100, offset = 0, dateFrom = null, dateTo = null) {
        try {
            this.state.today_sales_loading = true;
            const result = await this.orm.call(
                "product.warehouse.sale.summary",
                "get_today_sales_summary",
                [limit, offset, dateFrom, dateTo],
                // { limit: limit }
            );


            if (offset === 0) {
                // Primera carga - reemplazar datos
                // this.state.base_products_filtered = result.records || [];
                this.state.products_filtered = result.records || [];
                this.calculate_totals()
            } else {
                // Cargar más - agregar a datos existentes
                this.state.products_filtered = [
                    ...this.state.products_filtered,
                    ...(result.records || [])
                ];
                this.calculate_totals()

            }


            this.state.today_sales_has_more = result.has_more || false;
            // this.state.today_sales_next_offset = result.next_offset || 0;
            // this.state.today_sales_total_count = result.total_count || 0;
            // this.state.today_sales_date_from = result.date_from || null;
            // this.state.today_sales_date_to = result.date_to || null;
            this.state.today_sales_date = result.date || null;
            // this.state.loading = false;
            setTimeout(() => this.setupScrollListener(), 100);
            // this.state.today_sales_loading = false;
        } catch (error) {
            // this.state.loading = false;
            this.state.today_sales_has_more = false
            this.notification.add(
                "Error al cargar el resumen de ventas del día" + error,
                {type: "danger"}
            );
        }
    }

    /**
     * Cargar más registros de ventas
     */
    async loadMoreTodaySales(start_date = null, end_date = null) {

        if (this.state.today_sales_has_more) {
            this.state.offset += 100;
            await this.loadTodaySalesSummary(100, this.state.offset, start_date, end_date);
            this.calculate_totals()
        }

    }

    async sendToSpreedSheet() {

        const product_data = await this.state.products_filtered.find(
            (p) => p.product_id === this.state.selected_product_id
        );
        this.state.total_sold_warehouse = await this.state.warehouses.find(w =>
            w.warehouse_name.toLowerCase().includes('bodega matilde')
        ).boxes;
        this.state.googleSheetData = {
            "product_name": product_data.product_name,
            "product_sales": product_data.boxes,
            "stock": this.state.total_sold_warehouse,
            "uom_po_id": product_data.uom_po_id,
        }
        this.state.isOpenGoogleModal = true
    }


    async onUpdateSelectedLaboratory(selectedWO) {
        this.state.selectedLaboratory = selectedWO;
        this.state.brand_id = false;
         // this.state.state.selectedWarehouse = null;
        this.state.isfilterWarehouse = false
        this.state.isSortedWarehouse = false
        this.state.isSorted = false
        this.state.isSortedReab = false
        const laboratory_name = selectedWO;
        const selectedLaboratory = this.state.laboratories.find(opt => opt.id === laboratory_name);
        this.state.range_active =false
        this.state.today_sales_loading = false
        if (selectedLaboratory) {
            this.state.laboratory_id = selectedLaboratory.id;
            this.state.warehouses = [];
            // this.state.products_filtered = this.state.products.filter(
            //     product => product.laboratory_id === this.state.laboratory_id
            // );
            await this.get_products(this.state.laboratory_id, this.state.brand_id);
        } else {
            this.state.laboratory_id = false;
            this.state.warehouses = [];
            this.state.products_filtered = [];

            await this.loadTodaySalesSummary(100, 0);
        }
        this.state.selectedBrand = false;

    }

    async onUpdateSelectedBrand(selectedWO) {
        this.state.laboratory_id = false
        // this.state.state.selectedWarehouse = null;
        this.state.isfilterWarehouse = false
        this.state.isSortedWarehouse = false
        this.state.isSorted = false
        this.state.isSortedReab = false
        const brand_name = selectedWO;
        const selectedBrand = this.state.brands.find(opt => opt.id === brand_name)
        this.state.range_active =false
        this.state.today_sales_loading = false
        if (selectedBrand) {
            this.state.warehouses = []
            this.state.brand_id = selectedBrand.id
            await this.get_products(this.state.laboratory_id, this.state.brand_id);
            // this.state.products_filtered = this.state.products.filter(product => product.brand_id === this.state.brand_id)
        } else {
            this.state.brand_id = false;
            this.state.warehouses = [];
            this.state.products_filtered = [];
            await this.loadTodaySalesSummary(100, 0);
        }
        this.state.selectedLaboratory = false;
        this.state.selectedBrand = selectedWO
    }


    async getSalesInformation() {
        if (!this.state.laboratory_id && !this.state.brand_id) {

            this.state.range_active = true
            await this.loadTodaySalesSummary(100, 0, this.start_date,
                this.end_date,)
        } else {

            await this.get_products(this.state.laboratory_id, this.state.brand_id);
        }


        // Si hay un producto seleccionado, refrescar la tabla de bodegas con las nuevas fechas
        if (this.state.selected_product_id) {
            this.state.loading_warehouses = true;
            this.state.warehouses = await this.orm.call(
                "product.warehouse.sale.summary",
                "get_stock_by_warehouse",
                [this.state.selected_product_id, this.start_date, this.end_date]
            );
            this.state.warehouses_base = [...this.state.warehouses];
            await this.calculate_warehouse_totals();
            this.state.loading_warehouses = false;
        }
    }


    async get_warehouseId(warehouse) {

        this.state.products_filtered = [];

        // await this.loadTodaySalesSummary(20, 0);
        if (this.state.selected_warehouse_id === warehouse.warehouse_id) {
            // Deselecciona
            this.state.selected_warehouse_id = null
            this.state.products_filtered = [...this.state.base_products_filtered]
            this.calculate_totals()
        } else {
            // Selecciona y realiza consulta
            this.state.selected_warehouse_id = warehouse.warehouse_id;
            this.state.products_filtered = await this.orm.call("product.warehouse.sale.summary", "get_total_sales_by_warehouse", [this.start_date,
                this.end_date, this.state.selected_warehouse_id, this.state.selected_product_id,]);
            this.calculate_totals()
        }
    }

    async getPendingProducts() {
        //fucnion para obtener los productos que tienen prioridad de venta
        // se debe enviar el parametro sales_priority = true y laboratory_id o brand_id en undefined
        await this.get_products(undefined, undefined, true);
        this.state.brand_id = null;
        this.state.laboratory_id = null;
        this.state.selectedBrand = false;
        this.state.selectedLaboratory = false;
    }

    removeCart(product) {
        this.state.cart = this.state.cart.filter(item => item.id !== product.id);
        // Guardar carrito en localStorage después de remover item
        this.saveCartToStorage();
    }

    setCartQuantity(item, event) {
        const qty = parseInt(event.target.value, 10);
        if (!isNaN(qty) && qty > 0) {
            item.quantity = qty;
        } else {
            item.quantity = 1;
        }
        // Guardar carrito en localStorage después de actualizar cantidad
        this.saveCartToStorage();
    }

    async addCart(product) {
        const existingItem = this.state.cart.find(item => item.id === product.id);
        if (existingItem) {
            existingItem.quantity = (existingItem.quantity || 1) + 1;
        } else {
            this.state.cart.push({...product, quantity: 1});
        }
        // Guardar carrito en localStorage después de agregar item
        this.saveCartToStorage();
    }

    //fucnion para cambiar el estaod de los productos no diponibles por el proveedor
    async onProductNotAvailableForSupplier(product_id) {
        // Primero actualizar el estado local ANTES de llamar al backend
        const productIndex = this.state.products_filtered.findIndex(p => p.product_id === product_id);
        const baseProductIndex = this.state.base_products_filtered.findIndex(p => p.product_id === product_id);

        let newState;
        if (productIndex !== -1) {
            newState = !this.state.products_filtered[productIndex].product_sales_priority;
            this.state.products_filtered[productIndex].product_sales_priority = newState;
        }

        if (baseProductIndex !== -1) {
            this.state.base_products_filtered[baseProductIndex].product_sales_priority = newState;
        }

        // Luego llamar al backend
        await this.orm.call("product.product", "toggle_sales_priority", [product_id]);
    }


    loadMorePurchaseHistory = async () => {


        if (!this.state.hasMorePurchases || !this.state.selected_product_id) {
            return;
        }

        try {
            const newPurchases = await this.orm.call('product.product', 'get_complete_purchase_history', [
                this.state.selected_product_id,
                5,
                this.state.purchaseHistoryOffset
            ]);


            if (newPurchases.length > 0) {
                this.state.lastPurchases = [...this.state.lastPurchases, ...newPurchases];
                this.state.purchaseHistoryOffset += 5;

            } else {
                this.state.hasMorePurchases = false;

            }
        } catch (error) {
            console.error('Error loading more purchase history:', error);
        }
    }

    async get_products(laboratory_id, brand_id, sales_priority = false) {
        this.state.today_sales_has_more = false
        this.state.offset = 0
        try {
            this.state.loading = true
            this.state.products_filtered = await this.orm.call(
                "product.warehouse.sale.summary",
                "get_total_sales_summary",
                [
                    this.start_date,
                    this.end_date,
                    laboratory_id,
                    brand_id,
                    sales_priority,
                    null, // product_query
                    null, // limit
                    0,    // offset
                    this.state.selected_global_warehouse_id || null, // warehouse_id
                ]
            );
            this.state.base_products_filtered = [...this.state.products_filtered];
            this.state.selected_warehouse_id = null
            // Resetear estado de ordenamiento
            this.state.sortColumn = null;
            this.state.sortDirection = null;
            this.state.isSorted = false;
            this.state.isSortedReab = false;
            this.calculate_totals()
            this.state.loading = false;

        } catch (error) {
            this.state.loading = false;
            this.state.error.status = true;
            this.state.error.message = `Error al cargar las ventas, contacte con el administrador`;
        }
    }


    //funcion que calculta los totalesde la columnas de las ventas y promcoiones

    calculate_totals() {
        const products = this.state.products_filtered || [];
        // eslint-disable-next-line no-console
        // eslint-disable-next-line no-console

        //filter products that have quantity_sold greater than 0
        const products_total_discount = products.filter(product => product.discount > 0);
        const products_quantity_sold = products.filter(product => product.quantity_sold > 0);

        // const products_total_utility = products.filter(product => product.quantity_sold !== 0);
        // Calcular todos los totales primero
        const totals = {
            quantity_sold: products.reduce((sum, p) => sum + (p.quantity_sold || 0), 0),
            boxes: products.reduce((sum, p) => sum + (p.boxes || 0), 0),
            units: products.reduce((sum, p) => sum + (p.units || 0), 0),
            stock_total: products_quantity_sold.reduce((sum, p) => sum + (p.stock_total || 0), 0),
            amount_total: products.reduce((sum, p) => sum + (p.amount_total || 0), 0),
            total_cost: products.reduce((sum, p) => sum + (p.total_cost || 0), 0),
            avg_standar_price_old: products.reduce((sum, p) => sum + (p.avg_standar_price_old || 0), 0),
            standar_price_old: products.reduce((sum, p) => sum + (p.standar_price_old || 0), 0),
            discount: products.reduce((sum, p) => sum + (p.discount || 0), 0) / products_total_discount.length || 0,
            // utility: products.reduce((sum, p) => sum + (p.utility || 0), 0) /  products.length || 0,
        };

        // Agregar cálculos que dependen de los totales
        totals.utilidad_bruta = totals.amount_total - totals.total_cost;
        if (totals.total_cost === 0 || totals.amount_total === 0) {
            totals.utility = 0; // Evitar división por cero
        } else {
            totals.utility = (totals.utilidad_bruta * 100) / totals.total_cost;
        }

        // eslint-disable-next-line no-console
        this.state.product_totals = totals;
    }

    //toals warehouses data
    async calculate_warehouse_totals() {
        let warehouses = this.state.warehouses || [];
        // warehouses = warehouses.filter(warehouse_id => warehouse_id.warehouse_id !== 573);
        this.state.warehouses_totals = {
            total_sold: warehouses.filter(p => (p.total_sold || 0) > 0).reduce((sum, p) => sum + (p.total_sold || 0), 0),
            boxes: warehouses.filter(p => (p.boxes || 0) > 0).reduce((sum, p) => sum + (p.boxes || 0), 0),
            units: warehouses.filter(p => (p.units || 0) > 0).reduce((sum, p) => sum + (p.units || 0), 0),
            stock: warehouses.filter(p => (p.stock || 0) > 0).reduce((sum, p) => sum + (p.stock || 0), 0),
            // total_sold: warehouses.reduce((sum, p) => sum + (p.total_sold || 0), 0),
            // boxes: warehouses.reduce((sum, p) => sum + (p.boxes || 0), 0),
            // units: warehouses.reduce((sum, p) => sum + (p.units || 0), 0),
            // stock: warehouses.reduce((sum, p) => sum + (p.stock || 0), 0),
        };

    }


    //buscador de producto
    onSearchInputProd(ev) {
        const query = (this.state.product_query || '').toLowerCase();
        if (this.state.search_mode === 'laboratory') {
            // nova busca ao servidor com filtro
            this.get_laboratory_sales();
            return;
        }
        // Búsqueda global paginada en modo producto
        if (this.searchDebounceTimer) {
            clearTimeout(this.searchDebounceTimer);
        }
        this.searchDebounceTimer = setTimeout(async () => {
            const q = (this.state.product_query || '').trim();
            // Activar búsqueda en servidor solo con 2+ caracteres
            if (q && q.length >= 2) {
                this.state.product_global_search_active = true;
                await this.fetch_products_by_query(true);
                // preparar scroll
                setTimeout(() => this.setupScrollListener(), 100);
            } else {
                // sin query: volver a datos base actuales (o recargar por filtros)
                this.state.product_global_search_active = false;
                if (!q) {
                    this.state.products_filtered = [...this.state.base_products_filtered];
                    this.render();
                }
            }
        }, 300);
    }

    // alterar modo de busca
    async onSearchModeChange(ev) {
        this.state.search_mode = ev.target.value;
        // limpar query quando mudar de modo
        this.state.product_query = "";
        this.state.products_filtered = []
        this.state.products = []
        this.state.offset = 0
        if (this.state.search_mode === 'laboratory') {
            // Limpiar filtros dependientes para evitar inconsistencias
            this.state.brand_id = null;
            this.state.laboratory_id = null;
            this.state.selectedBrand = false;
            this.state.selectedLaboratory = false;
            this.state.selectedWarehouse = false;
            this.state.selected_global_warehouse_id = null;
            this.state.selected_warehouse_id = null;
            this.state.warehouses = [];
            this.state.isfilterWarehouse = false;
            this.state.isSortedWarehouse = false;
            this.state.isSorted = false;
            this.state.isSortedReab = false;
            this.state.selected_product_id = null;
            this.state.selected_laboratory_row_id = null;
            this.state.labs_has_more = false;
            this.state.labs_next_offset = 0;
            await this.get_laboratory_sales();

        } else if (this.state.search_mode === 'product') {
            // Remover listener de scroll quando sair do modo laboratório
            if (this.scrollListener) {
                const container = this.__owl__.refs.container;
                if (container) {
                    container.removeEventListener('scroll', this.scrollListener);
                }
                this.scrollListener = null;
            }
            // Solo recargar productos si hay filtros activos (laboratorio o marca)
            // Si no hay filtros, limpiar la lista para evitar cargar todos los productos
            if (this.state.laboratory_id || this.state.brand_id) {
                await this.get_products(this.state.laboratory_id, this.state.brand_id);
            } else if (!this.state.laboratory_id && !this.state.brand_id) {
                await this.loadTodaySalesSummary(100, 0)
            } else {
                // Sin filtros activos: limpiar lista en lugar de cargar todos los productos
                this.state.products_filtered = [];
                this.state.base_products_filtered = [];
                this.state.product_global_search_active = false;
                this.state.product_query = "";
                this.calculate_totals();
            }
        }
    }

    // Método para cambiar modo de búsqueda desde botones
    setSearchMode(mode) {
        if (this.state.search_mode === mode) return;
        this.onSearchModeChange({target: {value: mode}});
    }

    async get_laboratory_sales() {
        try {
            this.state.loading = true;
            this.state.labs_next_offset = 0;
            const resp = await this.orm.call('product.warehouse.sale.summary', 'get_total_sales_by_laboratory', [
                this.start_date,
                this.end_date,
                this.state.labs_limit,
                0,
                this.state.product_query || null,
            ]);

            if (resp && typeof resp === 'object' && resp.records) {
                this.state.products_filtered = resp.records;
                this.state.base_products_filtered = [...resp.records];
                this.state.labs_has_more = resp.has_more;
                this.state.labs_next_offset = resp.next_offset;
                this.calculate_totals();
            } else {

                this.state.products_filtered = [];
                this.state.base_products_filtered = [];
                this.state.labs_has_more = false;
                this.state.labs_next_offset = 0;

            }

            this.state.loading = false;

            // Configurar scroll listener após carregar os dados
            setTimeout(() => this.setupScrollListener(), 100);
        } catch (e) {
            this.state.loading = false;
            this.showError(`Error al cargar ventas por laboratorio: ${e.message || e}`);
        }
    }

    async fetch_products_by_query(reset = false) {
        try {
            if (reset) {
                this.state.products_next_offset = 0;
                this.state.products_has_more = false;
                this.state.products_loading_more = false;
                this.state.products_filtered = [];
            }
            this.state.loading = true;
            const limit = this.state.products_limit || 50;
            const offset = this.state.products_next_offset || 0;
            // Usar llamada optimizada que acepta query, limit y offset en backend
            const records = await this.orm.call('product.warehouse.sale.summary', 'get_total_sales_summary', [
                this.start_date,
                this.end_date,
                this.state.laboratory_id || null,
                this.state.brand_id || null,
                false,
                this.state.product_query || null,
                limit,
                offset,
                this.state.selected_global_warehouse_id || null,
            ]);
            if (reset) {
                this.state.products_filtered = records;
            } else {
                this.state.products_filtered = [...(this.state.products_filtered || []), ...records];
            }
            this.state.base_products_filtered = [...this.state.products_filtered];

            // Si es una búsqueda inicial (reset) y retorna exactamente 1 producto, seleccionar automáticamente la marca
            // if (reset && records.length === 1) {
            //     await this.autoSelectBrandFromProduct(records[0]);
            // }

            // Inferir paginación: si retornó 'limit' elementos, probablemente hay más
            this.state.products_has_more = Array.isArray(records) && records.length === limit;
            this.state.products_next_offset = this.state.products_has_more ? (offset + limit) : offset;
            this.calculate_totals();
            this.state.loading = false;
            this.render();
        } catch (e) {
            this.state.loading = false;
            this.showError(`Error en búsqueda: ${e.message || e}`);
        }
    }

    async load_more_products_by_query() {
        if (!this.state.product_global_search_active || this.state.products_loading_more || !this.state.products_has_more) return;
        this.state.products_loading_more = true;
        try {
            await this.fetch_products_by_query(false);
        } finally {
            this.state.products_loading_more = false;
        }
    }

    async load_more_labs() {
        if (!this.state.labs_has_more || this.state.labs_loading_more) return;
        this.state.labs_loading_more = true;
        try {
            const resp = await this.orm.call('product.warehouse.sale.summary', 'get_total_sales_by_laboratory', [
                this.start_date,
                this.end_date,
                this.state.labs_limit,
                this.state.labs_next_offset,
                this.state.product_query || null,
            ]);

            if (resp && typeof resp === 'object' && resp.records) {
                this.state.products_filtered = [...this.state.products_filtered, ...resp.records];
                this.state.base_products_filtered = [...this.state.products_filtered];
                this.state.labs_has_more = resp.has_more;
                this.state.labs_next_offset = resp.next_offset;
                this.calculate_totals();
            } else {
                this.showError('Erro no formato da resposta do servidor');
            }
        } catch (e) {
            this.showError(`Erro ao cargar más laboratórios: ${e.message || e}`);
        }
        this.state.labs_loading_more = false;
    }

    async setupScrollListener() {
        const container = this.__owl__.refs.container;
        if (!container) return;
        if (this.scrollListener) {
            container.removeEventListener('scroll', this.scrollListener);
        }

        let scrollTimeout;

        this.scrollListener = (e) => {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                const element = e.target;
                const threshold = 200;

                const nearBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - threshold;
                if (!nearBottom) return;

                if (this.state.search_mode === 'laboratory') {
                    if (this.state.labs_has_more && !this.state.labs_loading_more) {
                        this.load_more_labs();
                    }
                } else if (this.state.search_mode === 'product') {
                    if (this.state.product_global_search_active && this.state.products_has_more && !this.state.products_loading_more) {
                        this.load_more_products_by_query();
                    }
                }


                if (!this.state.laboratory_id && !this.state.brand_id && this.state.search_mode === 'product' && this.state.range_active) {

                    this.loadMoreTodaySales(this.start_date, this.end_date);
                }
                if (!this.state.laboratory_id && !this.state.brand_id && this.state.search_mode === 'product' && !this.state.range_active) {

                    this.loadMoreTodaySales();
                }

            }, 100); // debounce de 100ms
        };

        container.addEventListener('scroll', this.scrollListener, {passive: true});
    }

    async selectLaboratory(laboratory_id) {
        if (this.state.search_mode !== 'laboratory') return;
        if (this.state.selected_laboratory_row_id === laboratory_id) {
            // toggle off
            this.state.selected_laboratory_row_id = null;
            this.state.warehouses = [];
            return;
        }
        this.state.selected_laboratory_row_id = laboratory_id;
        this.state.warehouses = [];
        this.state.loading_warehouses = true;
        try {
            this.state.warehouses = await this.orm.call('product.warehouse.sale.summary', 'get_stock_by_warehouse_laboratory', [laboratory_id, this.start_date, this.end_date]);
            this.state.warehouses_base = [...this.state.warehouses];
            await this.calculate_warehouse_totals();
        } catch (e) {
            this.showError('Erro ao carregar bodegas do laboratório');
        }
        this.state.loading_warehouses = false;
    }

    async get_laboratories() {
        try {
            const labs = await this.orm.call(
                "product.laboratory",
                "search_read",
                [
                    [],
                    ["id", "name"]
                ], {order: "name ASC"}
            );
            // Ordenar alfabéticamente por nombre (case insensitive)
            this.state.laboratories = labs.sort((a, b) =>
                (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
            );
        } catch (error) {
            console.error("Error al cargar los laboratorios:", error);
        }
    }

    // obtener todas las bodegas para el filtro global
    async get_warehouses() {

        try {
            const key = "warehouses";
            const maxAge = 10 * 60 * 1000; // 10 min
            const cached = _inMemoryCache[key];
            if (cached && (Date.now() - cached.ts < maxAge)) {
                this.state.warehouseOptions = cached.data;
                return;
            }

            const data = await this.orm.call(
                "stock.warehouse",
                "search_read",
                [[], ["id", "name"]],
                {order: "name ASC"}
            );

            this.state.warehouseOptions = data;
            _inMemoryCache[key] = {data, ts: Date.now()};

        } catch (error) {
            this.state.warehouseOptions = []
        }
    }

    // obtener todas las marcas
    async get_brands() {
        try {
            const brands = await this.orm.call(
                "product.brand",
                "search_read",
                [
                    [],
                    ["id", "name"]
                ], {order: "name ASC"}
            );
            // Ordenar alfabéticamente por nombre (case insensitive)
            this.state.brands = brands.sort((a, b) =>
                (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
            );
        } catch (error) {
            console.error("Error al cargar las marcas:", error);
        }
    }

    // /**
    //  * FRONTEND OPTIMIZATION: Improved selectProduct function for better UX
    //  * 
    //  * ORIGINAL PROBLEM:
    //  * - No error handling, if query failed user didn't know what happened
    //  * - Loading state wasn't handled correctly in all cases
    //  * - No cleanup of previous data before loading new data
    //  * 
    //  * IMPLEMENTED IMPROVEMENTS:
    //  * - Robust error handling with try-catch
    //  * - Improved and consistent loading state
    //  * - Previous data cleanup for better UX
    //  * - Error notifications for the user
    //  */
    // async selectProduct(productId) {
    //     if (this.state.search_mode === 'laboratory') return; // não selecionar em modo laboratório
    //     if (productId === this.state.selected_product_id) return;

    //     // OPTIMIZATION 1: Clean previous data and show loading immediately
    //     // BEFORE: Previous data remained until new data arrived
    //     // NOW: Clean immediately for better visual feedback
    //     this.state.warehouses = []
    //     this.state.loading_warehouses = true

    //     if (this.state.selected_product_id !== productId || this.state.selected_product_id === null) {
    //         this.state.selected_product_id = productId;
    //         this.state.product_code = this.state.products_filtered.find(
    //             (p) => p.product_id === productId
    //         ).product_code;

    //         try {
    //             // OPTIMIZATION 2: Optimized backend call with error handling
    //             // BEFORE: No error handling, if query failed user didn't know what happened
    //             // NOW: Robust try-catch with error notifications
    //             this.state.warehouses = await this.orm.call(
    //                 "product.warehouse.sale.summary", 
    //                 "get_stock_by_warehouse", 
    //                 [this.state.selected_product_id, this.start_date, this.end_date]
    //             );
    //             this.state.warehouses_base = [...this.state.warehouses];
    //             this.state.warehouse_query = "";
    //             await this.calculate_warehouse_totals();
    //         } catch (error) {
    //             // OPTIMIZATION 3: Error handling with logging and user notification
    //             // BEFORE: Silent errors, user didn't know if something failed
    //             // NOW: Console log for debugging + visible notification to user
    //             console.error('Error loading warehouse data:', error);
    //             this.notification.add("Error al cargar datos de bodegas", {type: 'danger'});
    //         } finally {
    //             // OPTIMIZATION 4: Loading state guaranteed with finally
    //             // BEFORE: If there was an error, loading could stay active
    //             // NOW: finally guarantees that loading always deactivates
    //             this.state.loading_warehouses = false;
    //         }
    //     }

    //     this.state.isfilterWarehouse = false
    //     this.state.isSortedWarehouse = false
    // }
    async getMultibarcode(product_id) {
            await this.orm.call(
                "product.warehouse.sale.summary",
                "get_multibarcode_info",
                [product_id, this.state.product_code]
            ).then((result) => {
                this.state.extra_long_codes = (result?.long_codes || []).join(' | ');
                this.state.short_codes = (result?.short_codes || []).join(' | ');
                this.state.showMultibarcodeModal = true;
            }).catch((error) => {
                this.showError(`Error al cargar los códigos de barras: ${error.message || error}`);
            });
    }

    //obtener el detalle de ventas del producto por almacen
    async selectProduct(productId) {
        if (this.state.search_mode === 'laboratory') return; // não selecionar em modo laboratório
        if (productId === this.state.selected_product_id) return;
        this.state.warehouses = []
        this.state.loading_warehouses = true

        if (this.state.selected_product_id !== productId || this.state.selected_product_id === null) {
            this.state.selected_product_id = productId;
            const selectedProduct = this.state.products_filtered.find(
                (p) => p.product_id === productId
            );

            this.state.product_code = selectedProduct.product_code;
            
            /**
             * CARGAR CÓDIGOS DE BARRAS ALTERNATIVOS AUTOMÁTICAMENTE
             *
             * El backend retorna {long_codes: [], short_codes: []}
             * - long_codes: códigos con más de 6 dígitos (EAN-13, EAN-8, etc.)
             * - short_codes: códigos con 6 dígitos o menos (códigos internos)
             *
             * Visualización:
             * - product_code (principal) + extra_long_codes: con icono fa-barcode
             * - short_codes: con icono fa-coins
             */
            try {
                const multibarcodeResult = await this.orm.call(
                    "product.warehouse.sale.summary",
                    "get_multibarcode_info",
                    [productId, this.state.product_code]
                );
                this.state.extra_long_codes = (multibarcodeResult?.long_codes || []).join(' | ');
                this.state.short_codes = (multibarcodeResult?.short_codes || []).join(' | ');
            } catch (error) {
                this.state.extra_long_codes = '';
                this.state.short_codes = '';
            }
            
            this.state.warehouses = await this.orm.call("product.warehouse.sale.summary", "get_stock_by_warehouse", [this.state.selected_product_id, this.start_date, this.end_date])
            this.state.warehouses_base = [...this.state.warehouses];
            this.state.warehouse_query = "";
            await this.calculate_warehouse_totals()
            this.state.loading_warehouses = false
        }

        this.state.isfilterWarehouse = false
        this.state.isSortedWarehouse = false
        this.state.loading_warehouses = false
    }

    // actualizar bodega global seleccionada
    async onUpdateSelectedWarehouse(selectedWO) {
        this.state.selectedWarehouse = selectedWO;
        this.state.today_sales_loading = false
        const selectedWarehouse = this.state.warehouseOptions.find(opt => opt.id === selectedWO);
        if (selectedWarehouse) {
            this.state.selected_global_warehouse_id = selectedWarehouse.id;
        } else {
            this.state.selected_global_warehouse_id = null;
        }
        // Recargar datos si hay marca o laboratorio activo
        if (this.state.laboratory_id || this.state.brand_id) {
            await this.get_products(this.state.laboratory_id, this.state.brand_id);
        }
    }


    //funciones para el fiultrado de la informacion
    async onLaboratoryChange(ev) {
        this.state.brand_id = null;
        this.state.isfilterWarehouse = false
        this.state.isSortedWarehouse = false
        this.state.isSorted = false
        this.state.isSortedReab = false
        const laboratory_name = ev.target.value;
        const selectedLaboratory = this.state.laboratories.find(opt => opt.name === laboratory_name);
        if (selectedLaboratory) {
            this.state.laboratory_id = selectedLaboratory.id;
            this.state.warehouses = [];
            // this.state.products_filtered = this.state.products.filter(
            //     product => product.laboratory_id === this.state.laboratory_id
            // );
            await this.get_products(this.state.laboratory_id, this.state.brand_id);
        } else {
            this.state.laboratory_id = null;
            this.state.warehouses = [];
            this.state.products_filtered = [];
        }
        this.state.selectedBrand = "";
    }

    async onBrandChange(ev) {
        this.state.laboratory_id = null
        this.state.isfilterWarehouse = false
        this.state.isSortedWarehouse = false
        this.state.isSorted = false
        this.state.isSortedReab = false
        const brand_name = ev.target.value;
        const selectedBrand = this.state.brands.find(opt => opt.name === brand_name)
        if (selectedBrand) {
            this.state.warehouses = []
            this.state.brand_id = selectedBrand.id
            await this.get_products(this.state.laboratory_id, this.state.brand_id);
            // this.state.products_filtered = this.state.products.filter(product => product.brand_id === this.state.brand_id)
        } else {
            this.state.brand_id = null;
            this.state.warehouses = [];
            this.state.products_filtered = [];
        }
        this.state.selectedLaboratory = "";
    }

    // funciones para manejar los cambios de los imputs

    // cambio de fecha en el input inicio
    onStartDateChange(ev) {
        this.start_date = ev.target.value;
    }

    // cambio de fecha en el input hasta
    onEndDateChange(ev) {
        this.end_date = ev.target.value;
    }


//     notificaiones
    showError(message) {
        this.notification.add(message, {type: 'danger'});
    }

    showSucess(message) {
        this.notification.add(message, {type: 'success'})
    }

    showWarning(message) {
        this.notification.add(message, {type: 'warning'})
    }

    closeProductModal() {
        this.state.showProductModal = false;
    }

    // funcion para agregar un nuevio producto
    async addNewProduct() {
        if (!this.state.laboratory_id && !this.state.brand_id) {
            this.showError("Selecciona un Marca o Laboratorio para poder agregar el producto")
            return
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_detailed_type: "product",
                default_supplier_taxes_id: false,
                default_brand_id: this.state.brand_id,
            },

        }, {
            onClose: async () => {
                // Update products of that brand or laboratory
                await this.get_products(this.state.laboratory_id, this.state.brand_id);
            },
        });
    }

    openCartModal = async (product) => {
        let product_id = undefined
        let productFromState = null
        if (typeof product === 'object' && product !== null) {
            product_id = product.product_id
            productFromState = product
        } else {
            product_id = product
            // Buscar el producto en el estado para obtener matilde_qty_to_order
            productFromState = this.state.products_filtered?.find(p => p.product_id === product_id) || null
        }
        // Guardar el producto seleccionado para acceder a su marca en confirmAddToCart
        this.state.selectedProductDetails = productFromState;
        const existingItem = this.state.cart.find(item => item.id === product_id);
        const summary_sales = await this.orm.call('product.warehouse.sale.summary', 'get_product_sales_totals', [product_id, this.start_date, this.end_date]);
        const summary_purchases = await this.orm.call('product.product', 'get_product_received_totals', [product_id, this.start_date, this.end_date]);
        // Get complete purchase history for auto-filling cart fields
        // This fetches all purchase history to extract the most recent purchase data
        // const completePurchaseHistory = await this.orm.call('product.product', 'get_complete_purchase_history', [product_id]);
        // console.log(completePurchaseHistory,'completePurchaseHistory')
        // Get last 4 purchases for the history table display
        // Uses the same reliable data source but with limited records for performance
        const productLastPurchase = await this.orm.call('product.product', 'get_complete_purchase_history', [product_id], {
            limit: 4,
            offset: 0
        });
        const productData = await this.orm.read("product.product", [product_id], [
            "name", "product_tmpl_id", "product_sales_priority"
        ]);
        const productTmplId = productData[0].product_tmpl_id[0];
        const templateData = await this.orm.read("product.template", [productTmplId], [
            "min_stock", "max_stock", "standard_price", "list_price", "tax_string", "avg_standar_price_old",
            "qty_available", "uom_id", "uom_po_id", "taxes_id",
        ]);
        const umo_po_id = await this.orm.read("uom.uom", [templateData[0].uom_po_id[0]], ["name", "factor_inv"]);
        // const provider = await this.orm.call('product.brand', 'search_read', [
        //     [["id", "=", templateData[0].brand_id[0]]],)

        const discount_provider = await this.orm.call("product.supplierinfo", "search_read", [
            [["partner_id", "=", 2], ["product_tmpl_id", "=", productTmplId]],
            ["id", "discount"]
        ]);

        const providerDiscount = discount_provider.length > 0 ? discount_provider[0].discount : 0;

        // Si ya está en el carrito, priorizar los valores que el usuario ya configuró
        // PVF proveniente de la fila del reporte (columna PVF)
        const rowPvf = (productFromState && typeof productFromState.pvf === 'number') ? productFromState.pvf : 0;

        if (existingItem) {
            // Preserve exactly what the user configured previously
            // quantity is the paid quantity; freeProductQuantity is stored separately
            const quantity = typeof existingItem.quantity === 'number' ? existingItem.quantity : 1;
            const discount = typeof existingItem.discount === 'number' ? existingItem.discount : providerDiscount;
            const price_unit = parseFloat(existingItem.price_unit || 0);
            const price_box = parseFloat(existingItem.price_box || 0);
            const totalWithoutDiscount = price_unit * quantity;
            const total = parseFloat((totalWithoutDiscount - (totalWithoutDiscount * (discount / 100))).toFixed(2));

            // Obtener matilde_qty_to_order si está disponible en el producto
            let matildeQtyToOrder = 0;
            if (productFromState && typeof productFromState.matilde_qty_to_order === 'number') {
                matildeQtyToOrder = productFromState.matilde_qty_to_order;
            }

            this.state.cartProductData = {
                product: {...templateData[0], id: product_id, name: productData[0].name},
                quantity: quantity,
                product_sales_priority: productData[0].product_sales_priority,
                discount: discount,
                providerDiscount: providerDiscount,
                price_unit: price_unit.toFixed(2),
                purchase_price: templateData[0].standard_price,
                total: isNaN(existingItem.total) ? total : existingItem.total,
                freeProductQuantity: typeof existingItem.freeProductQuantity === 'number' ? existingItem.freeProductQuantity : 0,
                purchaseUom: existingItem.purchaseUom || templateData[0].uom_po_id[1],
                purchaseUomFactor: umo_po_id[0].factor_inv,
                price_box: price_box.toFixed(2),
                note: existingItem.note || "",
                pvf: typeof existingItem.pvf === 'number' ? existingItem.pvf : rowPvf,
                matilde_qty_to_order: matildeQtyToOrder,
                summary_purchases: summary_purchases || undefined,
                lastPurchase: productLastPurchase || [],
                summary_sales: summary_sales || undefined
            };
        } else {
            // Si no existe en carrito, usar la última compra como referencia inicial
            // Usar los mismos datos que se muestran en el XML del historial
            // Los datos correctos están en productLastPurchase que se asignan a state.cartProductData.lastPurchase
            const lastPurchase = (productLastPurchase && productLastPurchase.length > 0) ? productLastPurchase[0] : null;

            // eslint-disable-next-line no-console

            // Si el backend trae una cantidad recomendada para Bodega Matilde,
            // usarla como cantidad por defecto; si no, se usa la última compra.
            let recommendedQty = 0;
            let matildeQtyToOrder = 0;
            if (productFromState && typeof productFromState.matilde_qty_to_order === 'number') {
                recommendedQty = productFromState.matilde_qty_to_order;
                matildeQtyToOrder = productFromState.matilde_qty_to_order;
            }

            const defaultQuantity = recommendedQty > 0
                ? recommendedQty
                : (lastPurchase ? lastPurchase.paid_quantity : 1);
            const defaultDiscount = lastPurchase ? lastPurchase.discount : providerDiscount;
            const defaultFreeQuantity = lastPurchase ? lastPurchase.free_product_qty : 0;

            // Si hay historial, usar los precios del historial; si no, calcular basándose en PVF
            let defaultPriceUnit, defaultPriceBox;
            if (lastPurchase) {
                // Usar precios del historial
                // eslint-disable-next-line no-console

                defaultPriceUnit = lastPurchase.price_unit;
                defaultPriceBox = lastPurchase.price_box;
            } else {
                // Calcular precios basándose en PVF
                const basePvf = parseFloat(rowPvf || 0);
                const discountAmount = (basePvf * defaultDiscount) / 100;
                defaultPriceUnit = basePvf - discountAmount;
                defaultPriceBox = defaultPriceUnit * parseFloat(umo_po_id[0].factor_inv || 1);


                // eslint-disable-next-line no-console

            }

            const defaultPvf = lastPurchase ? lastPurchase.pvf : rowPvf;

            this.state.cartProductData = {
                product: {...templateData[0], id: product_id, name: productData[0].name},
                quantity: defaultQuantity,
                product_sales_priority: productData[0].product_sales_priority,
                discount: defaultDiscount,
                providerDiscount: providerDiscount,
                price_unit: defaultPriceUnit,
                purchase_price: templateData[0].standard_price,
                total: defaultPriceUnit ? parseFloat((defaultPriceUnit * defaultQuantity * (1 - defaultDiscount / 100)).toFixed(2)) : parseFloat(templateData[0].standard_price.toFixed(2)) || 0,
                freeProductQuantity: defaultFreeQuantity,
                purchaseUom: templateData[0].uom_po_id[1],
                purchaseUomFactor: umo_po_id[0].factor_inv,
                price_box: defaultPriceBox,
                note: "",
                pvf: defaultPvf,
                matilde_qty_to_order: matildeQtyToOrder,
                summary_purchases: summary_purchases || undefined,
                lastPurchase: productLastPurchase || [], // Keep original table format
                summary_sales: summary_sales || undefined
            };
        }

        this.state.showCartModal = true;
        this.state.showProductModal = false;
    }

    // funcionaes del carrito de compras

    // Funciones para manejar localStorage del carrito
    saveCartToStorage() {
        try {
            localStorage.setItem('sales_report_cart', JSON.stringify(this.state.cart));
        } catch (error) {
            console.warn('No se pudo guardar el carrito en localStorage:', error);
        }
    }

    loadCartFromStorage() {
        try {
            const savedCart = localStorage.getItem('sales_report_cart');
            if (savedCart) {
                this.state.cart = JSON.parse(savedCart);
            }
        } catch (error) {
            console.warn('No se pudo cargar el carrito desde localStorage:', error);
        }
    }

    clearCartStorage() {
        try {
            localStorage.removeItem('sales_report_cart');
        } catch (error) {
            console.warn('No se pudo limpiar el carrito del localStorage:', error);
        }
    }

    /**
     * Limpia completamente el carrito reutilizando funciones existentes
     */
    clearAllCart() {
        if (this.state.cart.length === 0) {
            this.notification.add("El carrito ya está vacío.", {type: 'info'});
            return;
        }

        // Reutilizar la función existente para limpiar localStorage
        this.clearCartStorage();

        // Limpiar el estado del carrito
        this.state.cart = [];

        // Mostrar notificación
        this.notification.add("Carrito limpiado correctamente.", {type: 'success'});

        // Forzar re-render
        this.render();
    }

    /**
     * Obtiene las marcas únicas del carrito (versión async para obtener marcas del backend)
     */
    async getUniqueBrandsFromCart() {
        const brands = new Map();

        // Obtener IDs de productos sin marca
        const productIdsWithoutBrand = this.state.cart
            .filter(item => !item.brand)
            .map(item => item.id);

        // Si hay productos sin marca, obtener sus marcas del backend
        if (productIdsWithoutBrand.length > 0) {
            try {
                const productsData = await this.orm.call('product.product', 'search_read', [
                    [['id', 'in', productIdsWithoutBrand]],
                    ['id', 'brand_id']
                ]);
                // Crear mapa de id -> marca
                const brandMap = {};
                for (const prod of productsData) {
                    brandMap[prod.id] = prod.brand_id ? prod.brand_id[1] : 'Sin marca';
                }
                // Actualizar items del carrito con sus marcas
                for (const item of this.state.cart) {
                    if (!item.brand && brandMap[item.id]) {
                        item.brand = brandMap[item.id];
                    }
                }
            } catch (error) {
                console.warn('Error al obtener marcas de productos:', error);
            }
        }

        // Ahora agrupar por marcas
        for (const item of this.state.cart) {
            const brandName = item.brand || 'Sin marca';
            if (!brands.has(brandName)) {
                brands.set(brandName, {
                    name: brandName,
                    count: 0,
                    products: []
                });
            }
            const brandData = brands.get(brandName);
            brandData.count++;
            brandData.products.push(item);
        }
        return Array.from(brands.values());
    }

    /**
     * Valida si hay múltiples marcas en el carrito
     */
    async hasMultipleBrands() {
        const brands = await this.getUniqueBrandsFromCart();
        return brands.length > 1;
    }

    /**
     * Muestra el modal de warning de múltiples marcas
     */
    async showMultiBrandWarningModal() {
        this.state.cartBrands = await this.getUniqueBrandsFromCart();
        this.state.selectedBrandsToRemove = [];
        this.state.showMultiBrandWarning = true;
    }

    /**
     * Cierra el modal de warning de múltiples marcas
     */
    closeMultiBrandWarning() {
        this.state.showMultiBrandWarning = false;
        this.state.selectedBrandsToRemove = [];
    }

    /**
     * Toggle selección de marca para eliminar
     */
    toggleBrandSelection(brandName) {
        const index = this.state.selectedBrandsToRemove.indexOf(brandName);
        if (index > -1) {
            this.state.selectedBrandsToRemove.splice(index, 1);
        } else {
            this.state.selectedBrandsToRemove.push(brandName);
        }
    }

    /**
     * Elimina productos de las marcas seleccionadas
     */
    async removeSelectedBrandProducts() {
        if (this.state.selectedBrandsToRemove.length === 0) {
            this.notification.add("Seleccione al menos una marca para eliminar.", {type: 'warning'});
            return;
        }

        // Filtrar productos que NO estén en las marcas seleccionadas
        this.state.cart = this.state.cart.filter(item => {
            const brandName = item.brand || 'Sin marca';
            return !this.state.selectedBrandsToRemove.includes(brandName);
        });

        // Guardar carrito actualizado
        this.saveCartToStorage();

        // Guardar cantidad antes de cerrar (closeMultiBrandWarning limpia selectedBrandsToRemove)
        const brandsRemovedCount = this.state.selectedBrandsToRemove.length;

        // Cerrar modal
        this.closeMultiBrandWarning();

        this.notification.add(`Productos de ${brandsRemovedCount} marca(s) eliminados.`, {type: 'success'});

        // Si queda solo una marca o ningún producto, continuar con la compra
        if (this.state.cart.length === 0) {
            this.notification.add("El carrito quedó vacío.", {type: 'info'});
            return;
        }

        // Verificar si aún hay múltiples marcas
        if (await this.hasMultipleBrands()) {
            await this.showMultiBrandWarningModal();
        }
    }

    /**
     * Continúa con la compra ignorando el warning de múltiples marcas
     */
    async proceedWithMultiBrandPurchase() {
        this.closeMultiBrandWarning();
        await this._executeCreatePurchaseOrder();
    }

    /**
     * Selecciona automáticamente la marca cuando se encuentra exactamente 1 producto en la búsqueda
     */
    // async autoSelectBrandFromProduct(product) {
    //     try {
    //         // Verificar si el producto tiene brand_id
    //         if (!product.brand_id) {
    //             return;
    //         }

    //         // Buscar la marca en la lista de marcas disponibles
    //         const selectedBrand = this.state.brands.find(brand => brand.id === product.brand_id);
    //         if (!selectedBrand) {
    //             return;
    //         }

    //         // Limpiar laboratorio (como hace onBrandChange)
    //         this.state.laboratory_id = null;
    //         this.state.selectedLaboratory = "";

    //         // Establecer la marca seleccionada
    //         this.state.brand_id = selectedBrand.id;
    //         this.state.selectedBrand = selectedBrand.name;

    //         // Limpiar búsqueda global para mostrar resultados de la marca
    //         this.state.product_global_search_active = false;
    //         this.state.product_query = "";

    //         // Cargar productos de la marca seleccionada
    //         await this.get_products(this.state.laboratory_id, this.state.brand_id);

    //         // Mostrar notificación informativa
    //         this.notification.add(`Marca "${selectedBrand.name}" seleccionada automáticamente.`, {type: 'info'});

    //     } catch (error) {
    //         console.warn('Error al seleccionar marca automáticamente:', error);
    //     }
    // }

    // Función para minimizar/expandir el modal del carrito
    toggleCartModalMinimize() {
        this.state.cartModalMinimized = !this.state.cartModalMinimized;
    }

    async updateCartProductData(field, value) {
        this.state.cartProductData[field] = parseFloat(value) || 0;
        const {product, quantity, discount, freeProductQuantity, providerDiscount} = this.state.cartProductData;

        if (!product) return;
        if (field === 'freeProductQuantity') {
            const totalQuantity = quantity + freeProductQuantity;
            const discountPercentage = totalQuantity > 0 ? (freeProductQuantity / totalQuantity) * 100 : 0;
            this.state.cartProductData.discount = providerDiscount + parseFloat(discountPercentage.toFixed(2));
            // Calcular SIEMPRE sobre PVF
            const basePvf = parseFloat(this.state.cartProductData.pvf || 0);

            const discountAmount = (basePvf * this.state.cartProductData.discount) / 100;
            const unit = basePvf - discountAmount;
            const box = unit * (this.state.cartProductData.purchaseUomFactor || 1);
            this.state.cartProductData.price_unit = unit.toFixed(2); // sin redondeo
            this.state.cartProductData.price_box = box.toFixed(2);   // sin redondeo
            if (this.state.cartProductData.price_unit < 0 || this.state.cartProductData.price_box < 0) {
                this.notification.add('El costo quedó negativo. Revise descuento/cantidad; puede ser un error de tipeo.', {type: 'warning'});
            }
            await this.calculateTotalOrder(quantity, freeProductQuantity)
        }
        if (field === 'quantity') {
            // Si está activa la promo 1+1, gratis debe igualar a cantidad
            if (this.state.cartProductData.promoOneOne) {
                this.state.cartProductData.freeProductQuantity = quantity;
            }
            // Si está activa la promo X+Y, gratis = floor(cantidad / X) * Y
            if (this.state.cartProductData.promoCustomXY) {
                const X = parseFloat(this.state.cartProductData.promoX || 0);
                const Y = parseFloat(this.state.cartProductData.promoY || 0);
                if (X > 0) {
                    const groups = Math.floor(quantity / X);
                    this.state.cartProductData.freeProductQuantity = groups * Y;
                } else {
                    this.state.cartProductData.freeProductQuantity = 0;
                }
            }
            const totalQuantity = quantity + this.state.cartProductData.freeProductQuantity;
            // Si hay producto gratis, aumentar descuento efectivo, si no, mantener el actual
            const discountPercentage = totalQuantity > 0 && this.state.cartProductData.freeProductQuantity > 0 ? (this.state.cartProductData.freeProductQuantity / totalQuantity) * 100 : 0;
            if (discountPercentage > 0) {
                this.state.cartProductData.discount = providerDiscount + parseFloat(discountPercentage.toFixed(2));
            }
            // Recalcular precio unitario/caja basado en PVF y descuento efectivo
            const basePvf = parseFloat(this.state.cartProductData.pvf || 0);
            const discountAmount = (basePvf * this.state.cartProductData.discount) / 100;
            const unit = basePvf - discountAmount;
            const box = unit * (this.state.cartProductData.purchaseUomFactor || 1);
            this.state.cartProductData.price_unit = unit.toFixed(2); // sin redondeo
            this.state.cartProductData.price_box = box.toFixed(2);   // sin redondeo
            if (this.state.cartProductData.price_unit < 0 || this.state.cartProductData.price_box < 0) {
                this.notification.add('El costo quedó negativo. Revise descuento/cantidad; puede ser un error de tipeo.', {type: 'warning'});
            }
            await this.calculateTotalOrder(quantity, freeProductQuantity)

        }
        if (field === 'discount') {

            this.state.cartProductData.freeProductQuantity = 0;
            // Calcular SIEMPRE sobre PVF
            const basePvf = parseFloat(this.state.cartProductData.pvf || 0);

            const discountAmount = (basePvf * this.state.cartProductData.discount) / 100;
            const unit = basePvf - discountAmount;
            const box = unit * (this.state.cartProductData.purchaseUomFactor || 1);
            this.state.cartProductData.price_unit = unit.toFixed(2); // sin redondeo
            this.state.cartProductData.price_box = box.toFixed(2);   // sin redondeo
            if (this.state.cartProductData.price_unit < 0 || this.state.cartProductData.price_box < 0) {
                this.notification.add('El costo quedó negativo. Revise descuento/cantidad; puede ser un error de tipeo.', {type: 'warning'});
            }
            await this.calculateTotalOrder(quantity, freeProductQuantity)

        }
        if (field === 'price_unit') {
            this.state.cartProductData.price_box = (value * this.state.cartProductData.purchaseUomFactor).toFixed(2);
            this.state.cartProductData.pvf = value
            await this.calculateTotalOrder(quantity, freeProductQuantity)
        }
        if (field === 'price_box') {
            this.state.cartProductData.price_unit = (value / this.state.cartProductData.purchaseUomFactor).toFixed(2);
            this.state.cartProductData.pvf = this.state.cartProductData.price_unit
            await this.calculateTotalOrder(quantity, freeProductQuantity)
        }

    }

    async calculateTotalOrder(quantity, freeProductQuantity) {
        const priceBoxForTotal = parseFloat(this.state.cartProductData.price_box || 0);
        const totalQuantity = (quantity || 0);
        const lineTotal = priceBoxForTotal * totalQuantity;
        this.state.cartProductData.total = isNaN(lineTotal.toFixed(2)) ? 0 : lineTotal.toFixed(2); // sin redondeo
    }

    confirmAddToCart() {
        const {
            product,
            quantity,
            freeProductQuantity,
            price_unit,
            price_box,
            discount,
            providerDiscount,
            total,
            pvf,
            product_sales_priority,
            purchaseUom, note,
        } = this.state.cartProductData;
        const existingItem = this.state.cart.find(item => item.id === product.id);
        if (existingItem) {
            // Store paid and free quantities separately to preserve exact user inputs
            existingItem.quantity = quantity;
            existingItem.freeProductQuantity = freeProductQuantity;
            existingItem.discount = discount;
            existingItem.price_unit = price_unit;
            existingItem.providerDiscount = providerDiscount;
            existingItem.total = total;
            existingItem.note = note
            existingItem.pvf = pvf;
            existingItem.price_box = price_box
            existingItem.purchaseUom = purchaseUom;
            existingItem.purchaseUomFactor = this.state.cartProductData.purchaseUomFactor;
        } else {
            // Obtener la marca del producto seleccionado
            const productBrand = this.state.selectedProductDetails?.brand || '';
            this.state.cart.push({
                id: product.id,
                name: product.name,
                brand: productBrand,
                // Store paid and free separately
                quantity: quantity,
                freeProductQuantity: freeProductQuantity,
                product_sales_priority,
                price_box,
                discount: discount,
                providerDiscount: providerDiscount,
                standard_price: product.standard_price,
                price_unit: price_unit,
                total,
                note,
                pvf,
                purchaseUom,
                purchaseUomFactor: this.state.cartProductData.purchaseUomFactor,
            });
        }
        this.state.showCartModal = false;
        // Guardar carrito en localStorage después de agregar/actualizar item
        this.saveCartToStorage();
    }

    async onInputPriceUnit(price_unit) {

        this.state.cartProductData.price_box = (price_unit * this.state.cartProductData.purchaseUomFactor).toFixed(2);
        this.state.cartProductData.pvf = price_unit
    }

    async onInputPriceBox(price_box) {
        this.state.cartProductData.price_unit = (price_box / this.state.cartProductData.purchaseUomFactor).toFixed(2);
        this.state.cartProductData.pvf = this.state.cartProductData.price_unit
    }

    onTogglePromoOneOne(ev) {
        const checked = !!ev.target.checked;
        this.state.cartProductData.promoOneOne = checked;
        if (checked) {
            // 1+1: gratis = cantidad
            const qty = parseFloat(this.state.cartProductData.quantity || 0);
            this.updateCartProductData('freeProductQuantity', qty);
            // Desactivar promo X+Y si estaba activa para evitar conflictos
            this.state.cartProductData.promoCustomXY = false;
        } else {
            // Al desactivar, no tocamos el gratis si el usuario lo cambió manualmente
        }
    }

    onTogglePromoCustomXY(ev) {
        const checked = !!ev.target.checked;
        this.state.cartProductData.promoCustomXY = checked;
        if (checked) {
            // Desactivar 1+1 si estaba activa
            this.state.cartProductData.promoOneOne = false;
            // Asegurar valores por defecto X=2, Y=1 si no existen
            if (!this.state.cartProductData.promoX) this.state.cartProductData.promoX = 2;
            if (this.state.cartProductData.promoY == null) this.state.cartProductData.promoY = 1;
            this.recomputeFreeQtyFromPromoXY();
        }
    }

    onPromoXYChange(field, value) {
        const num = parseFloat(value) || 0;
        this.state.cartProductData[field] = num;
        if (this.state.cartProductData.promoCustomXY) {
            this.recomputeFreeQtyFromPromoXY();
        }
    }

    recomputeFreeQtyFromPromoXY() {
        const qty = parseFloat(this.state.cartProductData.quantity || 0);
        const X = parseFloat(this.state.cartProductData.promoX || 0);
        const Y = parseFloat(this.state.cartProductData.promoY || 0);
        if (X > 0 && qty > 0) {
            const groups = Math.floor(qty / X);
            const free = groups * Y;
            this.updateCartProductData('freeProductQuantity', free);
        } else {
            this.updateCartProductData('freeProductQuantity', 0);
        }
    }


    async createPurchaseOrder() {
        if (!this.state.cart.length) {
            this.showError("¡Tu carrito está vacío!");
            return;
        }

        // Validar si hay múltiples marcas en el carrito
        if (await this.hasMultipleBrands()) {
            await this.showMultiBrandWarningModal();
            return;
        }

        // Si solo hay una marca, proceder directamente
        await this._executeCreatePurchaseOrder();
    }

    async _executeCreatePurchaseOrder() {
        if (this.state.selectedPurchaseOrderId) {
            // console.log("this.state.selectedPurchaseOrderId: ", this.state.selectedPurchaseOrderId)
            try {
                for (const item of this.state.cart) {

                    if (item.product_sales_priority) {
                        await this.onProductNotAvailableForSupplier(item.id)
                    }
                    // Enviar precio base (sin descuento) y el porcentaje de descuento
                    // Calcular el precio original sin descuento para evitar doble descuento
                    const baseUnit = parseFloat(item.pvf || 0);
                    const baseBox = baseUnit * parseFloat(item.purchaseUomFactor || 1);

                    await this.orm.call(
                        "purchase.order.line",
                        "create",
                        [{
                            order_id: this.state.selectedPurchaseOrderId,
                            product_id: item.id,
                            name: item.name,
                            pf: item.pvf,
                            product_qty: (item.quantity || 0) + (item.freeProductQuantity || 0),
                            free_product_qty: item.freeProductQuantity || 0,
                            paid_quantity: item.quantity || 0,
                            price_unit: baseBox,
                            discount: item.discount || 0,
                            product_uom: item.purchaseUom,
                        }]
                    );
                }
                this.state.cart = [];
                // Limpiar localStorage después de crear exitosamente la orden
                this.clearCartStorage();
                this.showSucess('¡Produtos adicionados à ordem de compra existente!');
                await this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: "purchase.order",
                    res_id: this.state.selectedPurchaseOrderId,
                    views: [[false, "form"]],
                    target: "new",
                });
            } catch (error) {
                this.showError("Se produjo un error al agregar productos a la orden de compra.");
            }
            return;
        }
        // Obtener el partner_id del laboratorio si existe
        let laboratoryData = await this.orm.call(
            "product.laboratory",
            "search_read",
            [[["id", "=", this.state.po_brand_id]]],
            {fields: ["id", "partner_id"], limit: 1}
        );
        this.state.selected_provider_id = this.state.po_brand_id

        const picking_type_id = await this.orm.call("stock.picking.type", "search_read", [
            [["warehouse_id", "=", 1], ["sequence_code", "in", ['IN']]],
            ["id"]
        ]);

        // Preparar datos de la orden
        // Si el laboratorio tiene un proveedor asociado, usarlo; sino el usuario lo seleccionará manualmente
        const orderData = {
            picking_type_id: picking_type_id[0].id,
        };

        // Solo agregar partner_id si el laboratorio tiene uno asociado
        if (laboratoryData.length > 0 && laboratoryData[0].partner_id) {
            orderData.partner_id = laboratoryData[0].partner_id[0];
        }

        const orderId = await this.orm.call(
            "purchase.order",
            "create",
            [orderData]
        );
        const order_lines = []
        for (const item of this.state.cart) {
            if (item.product_sales_priority) {
                await this.onProductNotAvailableForSupplier(item.id)
            }

            // const ratio = this.state.uomPoOptions.filter(uom => uom.id === parseInt(item.purchaseUom))[0].ratio
            // Enviar precio base (sin descuento) y el porcentaje de descuento para aplicar una sola vez en backend
            const baseUnit = parseFloat(item.pvf || 0);
            const baseBox = baseUnit * parseFloat(item.purchaseUomFactor || 1);


            order_lines.push({
                order_id: orderId,
                product_id: item.id,
                product_qty: (item.quantity || 0) + (item.freeProductQuantity || 0),
                free_product_qty: item.freeProductQuantity || 0,
                paid_quantity: item.quantity || 0,
                price_unit: baseBox,
                pvf: item.pvf,
                discount: item.discount || 0,
                // product_uom: item.purchaseUom,
            })

            if (item.note !== '') {
                order_lines.push({
                    order_id: orderId,
                    name: 'Nota: ' + item.name + ' | ' + item.note,
                    display_type: 'line_note',
                    sequence: 10,
                    product_qty: 0,
                    price_unit: 0,
                    product_uom: false,
                    product_id: false,
                    discount: 0,
                })
            }
        }
        await this.orm.call(
            "purchase.order.line",
            "create",
            [
                order_lines
            ]
        );

        // Actualizar marcas y laboratorios basándose en los productos de la orden
        await this.orm.call(
            "purchase.order",
            "update_brand_laboratory_from_lines",
            [[orderId]]
        );

        this.state.cart = [];
        // Limpiar localStorage después de crear exitosamente la orden
        this.clearCartStorage();
        this.showSucess('¡Orden de compra creada exitosamente!');
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "new",
        });
        await this.fetchLastPurchaseOrders();
        // } catch (error) {
        //     console.warn("Error al crear orden de compra:", error);
        //     this.showError("Se produjo un error al crear la orden de compra.");
        // }
    }

    async fetchLastPurchaseOrders() {
        try {
            const formatUTCDate = (date) => {
                const year = date.getUTCFullYear();
                let month = date.getUTCMonth() + 1;
                let day = date.getUTCDate();
                month = month < 10 ? "0" + month : month;
                day = day < 10 ? "0" + day : day;
                return `${year}-${month}-${day}`;
            };

            const now = new Date();
            const todayUTC = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
            const tomorrowUTC = new Date(todayUTC);
            tomorrowUTC.setUTCDate(todayUTC.getUTCDate() + 1);

            let startDate;
            const filter = this.state.purchaseOrderPeriodFilter;

            if (filter === 'day') {
                // Compras del día actual
                startDate = new Date(todayUTC);
            } else if (filter === 'month') {
                // Compras del mes actual (desde el primer día del mes)
                startDate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
            } else if (filter === 'year') {
                // Compras del año actual (desde el primer día del año)
                startDate = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
            } else {
                // Fallback: últimos 7 días (comportamiento anterior)
                startDate = new Date(todayUTC);
                startDate.setUTCDate(todayUTC.getUTCDate() - 7);
            }

            const startStr = formatUTCDate(startDate);
            const endStr = formatUTCDate(tomorrowUTC);

            const orders = await this.orm.call(
                "purchase.order",
                "search_read",
                [
                    [
                        ["date_order", ">=", startStr],
                        ["date_order", "<", endStr]
                    ],
                    ["id", "name", "partner_id", "date_order", "amount_total", "state"],
                    0,
                    1000,
                    "date_order desc"
                ]
            );

            this.state.lastPurchaseOrders = orders.map(order => ({
                ...order,
                date_order: this.formatDate(order.date_order)
            }));


        } catch (error) {
            // console.error("Error al obtener las órdenes de compra del día:", error);
            this.showError("Error al obtener las órdenes de compra del período.", error);
        }
    }

    /**
     * Cambia el filtro de periodo para órdenes de compra y recarga la lista
     * @param {string} period - 'day', 'month', o 'year'
     */
    async onPurchaseOrderPeriodChange(period) {
        this.state.purchaseOrderPeriodFilter = period;
        await this.fetchLastPurchaseOrders();
    }

    formatDate(dateStr) {
        if (!dateStr) return '';

        let date;
        if (dateStr.indexOf(' ') > -1) {
            const [datePart, timePart] = dateStr.split(' ');
            const [year, month, day] = datePart.split('-').map(Number);
            const [hour, minute, second] = timePart.split(':').map(Number);
            date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
        } else {
            const [year, month, day] = dateStr.split('-').map(Number);
            date = new Date(Date.UTC(year, month - 1, day));
        }

        const localYear = date.getFullYear();
        const localMonth = String(date.getMonth() + 1).padStart(2, '0');
        const localDay = String(date.getDate()).padStart(2, '0');

        return `${localDay}/${localMonth}/${localYear}`;
    }

    onPurchaseOrderChange(event) {
        const orderId = event.target.value;
        this.state.selectedPurchaseOrderId = orderId ? parseInt(orderId) : null;
    }

    async openPurchaseOrderModal() {
        if (!this.state.selectedPurchaseOrderId) {
            this.showError("Por favor seleccione una orden de compra primero.");
            return;
        }
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "purchase.order",
                res_id: this.state.selectedPurchaseOrderId,
                views: [[false, "form"]],
                target: "new",
            });
        } catch (error) {
            this.showError("Error al abrir la visualización de la orden de compra.");
        }
    }

    /**
     * Abre una orden de compra específica en un modal
     */
    async openPurchaseOrder(order_id) {
        if (!order_id) return;
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Orden de Compra",
                res_model: "purchase.order",
                res_id: order_id,
                views: [[false, "form"]],
                target: "new",
            });
        } catch (error) {
            console.error('Error al abrir Orden de Compra:', error);
            this.notification.add("Error al abrir la Orden de Compra.", {type: 'danger'});
        }
    }

    /**
     * Abre una factura de proveedor específica en un modal
     */
    async openVendorBill(invoice_id) {
        if (!invoice_id) return;
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Factura",
                res_model: "account.move",
                res_id: invoice_id,
                views: [[false, "form"]],
                target: "new",
                context: {default_move_type: 'in_invoice'},
            });
        } catch (error) {
            console.error('Error al abrir Factura:', error);
            this.notification.add("Error al abrir la Factura.", {type: 'danger'});
        }
    }

    // async loadOrderIntoCart() {
    //     if (!this.state.selectedPurchaseOrderId) {
    //         this.showError("Por favor seleccione una orden de compra primero.");
    //         return;
    //     }
    //     try {
    //         const lines = await this.orm.call("purchase.order.line", "search_read", [
    //             [["order_id", "=", this.state.selectedPurchaseOrderId]],
    //             ["id", "product_id", "name", "product_qty", "free_product_qty", "discount", "product_uom", "price_unit", "pvf"],
    //             0, 1000, "id asc"
    //         ]);

    //         // eslint-disable-next-line no-console
    //         console.log('[LoadOrder] Raw lines from DB:', lines);

    //         // Filtrar solo líneas con product_id válido (no false, no null)
    //         const validLines = lines.filter(l => l.product_id && l.product_id !== false && Array.isArray(l.product_id) && l.product_id.length >= 2);

    //         // eslint-disable-next-line no-console
    //         console.log('[LoadOrder] Valid lines (with product_id):', validLines);
    //         const uomIds = l.product_uom[0];

    //         const uoms = await this.orm.call('uom.uom', 'read', [uomIds, ['id', 'factor_inv']]);
    //         const uomMap = new Map(uoms.map(u => [u.id, u.factor_inv]));


    //         const mapped = validLines.map(l => {
    //             const paidQty = (l.product_qty || 0) - (l.free_product_qty || 0);
    //             const freeQty = l.free_product_qty || 0;
    //             const factorInv = uomMap.get(uomIds) || 1;

    //             console.log('[LoadOrder] Product uom:', l.product_uom, l.product_uom.factor_inv);
    //             const priceUnit = parseFloat(l.price_unit / factorInv || 0);
    //             const pvf = parseFloat(l.pvf || 0);

    //             // eslint-disable-next-line no-console
    //             console.log('[LoadOrder] Processing line:', { 
    //                 product_id: l.product_id, 
    //                 product_id_type: typeof l.product_id,
    //                 product_id_length: l.product_id ? l.product_id.length : 'N/A'
    //             });

    //             return {
    //                 id: l.product_id[0], // Ya sabemos que es válido
    //                 name: l.product_id[1], // Ya sabemos que es válido
    //                 quantity: paidQty,
    //                 freeProductQuantity: freeQty,
    //                 discount: parseFloat(l.discount || 0),
    //                 providerDiscount: 0,
    //                 standard_price: 0,
    //                 price_unit: priceUnit,
    //                 price_box: priceUnit * 1, // factor básico, se recalculará
    //                 total: priceUnit * paidQty,
    //                 note: l.name || "",
    //                 pvf: pvf || priceUnit,
    //                 purchaseUom: l.product_uom ? l.product_uom[1] : "",
    //                 purchaseUomFactor: 1,
    //             };
    //         });

    //         const cartById = new Map(this.state.cart.map(it => [it.id, it]));
    //         for (const it of mapped) {
    //             if (!it.id) continue;
    //             const existing = cartById.get(it.id);
    //             if (existing) {
    //                 existing.quantity = it.quantity;
    //                 existing.freeProductQuantity = it.freeProductQuantity;
    //                 existing.discount = it.discount;
    //                 existing.providerDiscount = it.providerDiscount;
    //                 existing.standard_price = it.standard_price;
    //                 existing.price_unit = it.price_unit;
    //                 existing.price_box = it.price_box;
    //                 existing.total = it.total;
    //                 existing.note = it.note;
    //                 existing.pvf = it.pvf;
    //                 existing.purchaseUom = it.purchaseUom;
    //                 existing.purchaseUomFactor = it.purchaseUomFactor;
    //             } else {
    //                 this.state.cart.push(it);
    //             }
    //         }

    //         this.state.cart = [...this.state.cart];
    //         this.state.isEditingOrder = true;
    //         this.saveCartToStorage();
    //         // Mostrar los productos de la orden en la tabla derecha
    //         await this.showOrderProductsInTable(validLines);
    //         this.showSucess("Productos de la orden cargados al carrito para edición.");
    //     } catch (e) {
    //         this.showError("No se pudo cargar la orden seleccionada para edición.");
    //     }
    // }

    async loadOrderIntoCart() {
        if (!this.state.selectedPurchaseOrderId) {
            this.showError("Por favor seleccione una orden de compra primero.");
            return;
        }

        try {
            // Limpiar carrito y localStorage antes de cargar una nueva orden
            this.state.cart = [];
            this.clearCartStorage();

            const lines = await this.orm.call("purchase.order.line", "search_read", [
                [["order_id", "=", this.state.selectedPurchaseOrderId]],
                ["id", "product_id", "name", "product_qty", "free_product_qty", "discount", "product_uom", "price_unit", "pvf"],
                0, 1000, "id asc"
            ]);


            // Filtrar solo líneas válidas
            const validLines = lines.filter(l => l.product_id && Array.isArray(l.product_id) && l.product_id.length >= 2);

            // ✅ 1️⃣ Obtener todos los IDs de unidades de medida (uom)
            const uomIds = [...new Set(validLines.map(l => l.product_uom?.[0]).filter(Boolean))];

            // ✅ 2️⃣ Leer sus factores inversos
            const uoms = await this.orm.call('uom.uom', 'read', [uomIds, ['id', 'factor_inv']]);
            const uomMap = new Map(uoms.map(u => [u.id, u.factor_inv]));

            // ✅ 3️⃣ Mapear las líneas
            const mapped = validLines.map(l => {
                const paidQty = (l.product_qty || 0) - (l.free_product_qty || 0);
                const freeQty = l.free_product_qty || 0;

                const uomId = l.product_uom?.[0];
                const factorInv = uomMap.get(uomId) || 1;

                const priceUnit = parseFloat((l.price_unit / factorInv) || 0);
                const pvf = parseFloat(l.pvf || 0);

                return {
                    id: l.product_id[0],
                    name: l.product_id[1],
                    quantity: paidQty,
                    freeProductQuantity: freeQty,
                    discount: parseFloat(l.discount || 0),
                    providerDiscount: 0,
                    standard_price: 0,
                    price_unit: priceUnit,
                    price_box: l.price_unit,
                    total: l.price_unit * paidQty,
                    note: l.name || "",
                    pvf: pvf || priceUnit,
                    purchaseUom: l.product_uom ? l.product_uom[1] : "",
                    purchaseUomFactor: factorInv,
                };
            });

            // ✅ 4️⃣ Actualizar el carrito
            const cartById = new Map(this.state.cart.map(it => [it.id, it]));
            for (const it of mapped) {
                if (!it.id) continue;
                const existing = cartById.get(it.id);
                if (existing) Object.assign(existing, it);
                else this.state.cart.push(it);
            }

            this.state.cart = [...this.state.cart];
            this.state.isEditingOrder = true;
            this.saveCartToStorage();

            await this.showOrderProductsInTable(validLines);
            this.showSucess("Productos de la orden cargados al carrito para edición.");
        } catch (e) {
            console.error("❌ loadOrderIntoCart error:", e);
            this.showError("No se pudo cargar la orden seleccionada para edición.");
        }
    }


    async saveEditsToOrder() {
        if (!this.state.selectedPurchaseOrderId) {
            this.showError("No hay una orden seleccionada para editar.");
            return;
        }
        try {
            const existingLines = await this.orm.call("purchase.order.line", "search_read", [
                [["order_id", "=", this.state.selectedPurchaseOrderId]],
                ["id", "product_id", "product_qty", "free_product_qty", "discount", "product_uom"],
                0, 1000, "id asc"
            ]);

            const lineByProductId = new Map();
            for (const l of existingLines) {
                const pid = l.product_id && l.product_id[0];
                if (pid) lineByProductId.set(pid, l);
            }

            const seenProductIds = new Set();

            // Filtrar solo items con product_id válido
            const validCartItems = this.state.cart.filter(item => {
                const hasValidProduct = !!item.id && Number.isFinite(parseFloat(item.id));
                if (!hasValidProduct) {
                    // eslint-disable-next-line no-console
                    console.warn('[EditPO] Skip item without valid product_id', {item});
                }
                return hasValidProduct;
            });

            // eslint-disable-next-line no-console
            // eslint-disable-next-line no-console
            // eslint-disable-next-line no-console

            for (const item of validCartItems) {
                const product_qty = (item.quantity || 0) + (item.freeProductQuantity || 0);
                const free_product_qty = item.freeProductQuantity || 0;
                const discount = item.discount || 0;

                const existing = lineByProductId.get(item.id);

                // Si la cantidad total es 0, eliminar si existe; no crear líneas vacías
                if (product_qty <= 0) {
                    if (existing) {
                        // eslint-disable-next-line no-console
                        await this.orm.call("purchase.order.line", "unlink", [[existing.id]]);
                    }
                }

                if (existing) {
                    seenProductIds.add(item.id);
                    const payload = {
                        product_qty,
                        free_product_qty,
                        paid_quantity: item.quantity || 0,
                        discount,
                        name: item.note || existing.name,
                        price_unit: item.price_unit || 0,
                        product_id: item.id,
                    };
                    // eslint-disable-next-line no-console
                    try {
                        await this.orm.call("purchase.order.line", "write", [
                            [existing.id],
                            payload,
                        ]);
                        // eslint-disable-next-line no-console
                    } catch (writeError) {
                        // eslint-disable-next-line no-console
                        console.error('[EditPO] Write failed for line', existing.id, writeError);
                        throw writeError;
                    }
                } else {
                    const payload = {
                        order_id: this.state.selectedPurchaseOrderId,
                        product_id: item.id,
                        name: item.note || item.name,
                        product_qty,
                        free_product_qty,
                        paid_quantity: item.quantity || 0,
                        discount,
                        price_unit: item.price_unit || 0,
                        pvf: item.pvf || 0,
                    };
                    // eslint-disable-next-line no-console
                    try {
                        await this.orm.call("purchase.order.line", "create", [[payload]]);
                        // eslint-disable-next-line no-console
                    } catch (createError) {
                        // eslint-disable-next-line no-console
                        throw createError;
                    }
                }
            }

            // Eliminar líneas que ya no están en el carrito válido
            for (const l of existingLines) {
                const pid = l.product_id && l.product_id[0];
                if (pid && !validCartItems.find(ci => ci.id === pid)) {
                    // eslint-disable-next-line no-console
                    await this.orm.call("purchase.order.line", "unlink", [[l.id]]);
                }
            }

            this.showSucess("Orden actualizada correctamente.");
            this.state.isEditingOrder = false;
            // Limpiar carrito y localStorage después de guardar cambios
            this.state.cart = [];
            this.clearCartStorage();
            await this.fetchLastPurchaseOrders();
            // Resetear selección de orden para permitir guardar al carrito normal
            this.state.selectedPurchaseOrderId = null;
            try {
                const selects = document.querySelectorAll('select.form-select');
                selects.forEach((sel) => {
                    const hasPlaceholder = Array.from(sel.options || []).some(opt => (opt.textContent || '').includes('Seleccione una orden'));
                    if (hasPlaceholder) {
                        sel.value = "";
                    }
                });
            } catch (e) {
            }
            this.render();
        } catch (e) {
            this.showError("No se pudieron guardar los cambios en la orden.");
        }
    }

    cancelOrderEditing() {
        this.state.isEditingOrder = false;
        // Limpiar carrito y localStorage al cancelar edición
        this.state.cart = [];
        this.clearCartStorage();
        // Resetear selección de orden
        this.state.selectedPurchaseOrderId = null;
        try {
            const selects = document.querySelectorAll('select.form-select');
            selects.forEach((sel) => {
                const hasPlaceholder = Array.from(sel.options || []).some(opt => (opt.textContent || '').includes('Seleccione una orden'));
                if (hasPlaceholder) {
                    sel.value = "";
                }
            });
        } catch (e) {
        }
        this.render();
    }

    async showOrderProductsInTable(orderLines) {
        try {
            // Obtener IDs de los productos de la orden
            const productIds = orderLines.map(line => line.product_id[0]);

            if (productIds.length === 0) {
                return;
            }

            // Obtener datos básicos de los productos primero
            const basicProductsData = await this.orm.call(
                "product.product",
                "search_read",
                [
                    [["id", "in", productIds]],
                    ["id", "name", "brand_id", "laboratory_id",
                        "product_sales_priority", "uom_po_id"]
                ]
            );

            // Crear un mapa para obtener el PVF de cada producto desde las líneas de la orden
            const pvfMap = new Map();
            orderLines.forEach(line => {
                if (line.product_id && line.product_id[0] && line.pvf) {
                    pvfMap.set(line.product_id[0], line.pvf);
                }
            });

            // Para cada producto, obtener sus datos de ventas individualmente
            const productsWithSalesData = [];
            for (const product of basicProductsData) {
                try {
                    // Obtener datos de ventas para este producto específico usando product_query con su nombre
                    const salesData = await this.orm.call(
                        "product.warehouse.sale.summary",
                        "get_total_sales_summary",
                        [
                            this.start_date,
                            this.end_date,
                            null, // laboratory_id
                            null, // brand_id
                            false, // sales_priority
                            product.name, // product_query con el nombre específico del producto
                            null, // limit
                            0 // offset
                        ]
                    );

                    if (salesData && salesData.length > 0) {
                        // Buscar el producto específico en los resultados
                        const productSalesData = salesData.find(item => item.product_id === product.id);
                        if (productSalesData) {
                            productSalesData.pvf = pvfMap.get(product.id) || 0;
                            productsWithSalesData.push(productSalesData);
                        } else {
                            // Si no se encuentra, crear con datos básicos
                            const productWithDefaults = {
                                ...product,
                                product_name: product.name,
                                quantity_sold: 0,
                                boxes: 0,
                                units: 0,
                                stock_total: 0,
                                amount_total: 0,
                                total_cost: 0,
                                avg_standar_price_old: 0,
                                standar_price_old: 0,
                                discount: 0,
                                utility: 0,
                                pvf: pvfMap.get(product.id) || 0
                            };
                            productsWithSalesData.push(productWithDefaults);
                        }
                    } else {
                        // Si no hay datos de ventas, crear con datos básicos
                        const productWithDefaults = {
                            ...product,
                            product_name: product.name,
                            quantity_sold: 0,
                            boxes: 0,
                            units: 0,
                            stock_total: 0,
                            amount_total: 0,
                            total_cost: 0,
                            avg_standar_price_old: 0,
                            standar_price_old: 0,
                            discount: 0,
                            utility: 0,
                            pvf: pvfMap.get(product.id) || 0
                        };
                        productsWithSalesData.push(productWithDefaults);
                    }
                } catch (error) {
                    // eslint-disable-next-line no-console
                    // En caso de error, crear producto con datos básicos
                    const productWithDefaults = {
                        ...product,
                        product_name: product.name,
                        quantity_sold: 0,
                        boxes: 0,
                        units: 0,
                        stock_total: 0,
                        amount_total: 0,
                        total_cost: 0,
                        avg_standar_price_old: 0,
                        standar_price_old: 0,
                        discount: 0,
                        utility: 0,
                        pvf: pvfMap.get(product.id) || 0
                    };
                    productsWithSalesData.push(productWithDefaults);
                }
            }

            // eslint-disable-next-line no-console

            this.state.products_filtered = productsWithSalesData;
            this.state.base_products_filtered = productsWithSalesData;

            // Limpiar filtros para mostrar solo los productos de la orden
            this.state.laboratory_id = null;
            this.state.brand_id = null;
            this.state.product_query = "";

            // Calcular totales para los productos de la orden
            this.calculate_totals();

            // eslint-disable-next-line no-console
            // eslint-disable-next-line no-console

            this.showSucess(`Mostrando ${this.state.products_filtered.length} productos de la orden en la tabla.`);

        } catch (error) {
            // eslint-disable-next-line no-console
            this.showError("Error al cargar los productos de la orden en la tabla.");
        }
    }

    //función para ordenar las columnas de la tabla (ascendente, descendente, reset)
    async handleSortRow(key) {
        // Si es la misma columna, rotar: desc -> asc -> reset
        if (this.state.sortColumn === key) {
            if (this.state.sortDirection === 'desc') {
                // Cambiar a ascendente
                this.state.sortDirection = 'asc';
                this.state.products_filtered.sort((a, b) => {
                    const valA = a[key] || 0;
                    const valB = b[key] || 0;
                    if (typeof valA === 'string') {
                        return valA.localeCompare(valB);
                    }
                    return valA - valB;
                });
            } else if (this.state.sortDirection === 'asc') {
                // Reset al orden original
                this.state.products_filtered = [...this.state.base_products_filtered];
                this.state.sortColumn = null;
                this.state.sortDirection = null;
            }
        } else {
            // Nueva columna: ordenar descendente
            this.state.sortColumn = key;
            this.state.sortDirection = 'desc';
            this.state.products_filtered.sort((a, b) => {
                const valA = a[key] || 0;
                const valB = b[key] || 0;
                if (typeof valA === 'string') {
                    return valB.localeCompare(valA);
                }
                return valB - valA;
            });
        }
        // Mantener compatibilidad con estados anteriores
        this.state.isSorted = this.state.sortColumn !== null;
        this.state.isSortedReab = this.state.sortColumn === 'matilde_qty_to_order';
    }

    // Función para ordenar por columna de Reabastecimiento (usa handleSortRow)
    async handleSortReab() {
        await this.handleSortRow('matilde_qty_to_order');
    }

    async sortWarehouseData(key) {
        if ('warehouse_name' === key) {
            this.state.warehouses = [...this.state.warehouses_base]
            this.state.isSortedWarehouse = false;
        }
        if (!this.state.isSortedWarehouse) {
            this.state.warehouses.sort((a, b) => b[key] - a[key]);
            this.state.isSortedWarehouse = true;
        } else {
            this.state.warehouses = [...this.state.warehouses_base]
            this.state.isSortedWarehouse = false;
        }
    }

    // filtrar los stocks con cero de los almacenes
    async warehousesStock(key) {
        if (!this.state.isfilterWarehouse) {
            this.state.isfilterWarehouse = true
            if (key === 'stock_0') {
                this.state.warehouses = this.state.warehouses.filter(warehouse => warehouse.stock === 0);
            }
            if (key === 'stock_1') {
                this.state.warehouses = this.state.warehouses.filter(warehouse => warehouse.stock > 0 && warehouse.stock < 10);
            }
            if (key === 'stock_2') {
                this.state.warehouses = this.state.warehouses.filter(warehouse => warehouse.stock > 10);
            }
        } else {
            this.state.warehouses = [...this.state.warehouses_base]
            this.state.isfilterWarehouse = false
        }

        await this.calculate_warehouse_totals()
    }


    //filtro de almacenes
    async onSearchInputWarehouse(ev) {
        const query = (this.state.warehouse_query || "").toLowerCase();
        if (!query) {
            this.state.warehouses = [...(this.state.warehouses_base || [])];
        } else {
            this.state.warehouses = (this.state.warehouses_base || []).filter((w) =>
                (w.warehouse_name || "").toLowerCase().includes(query)
            );
        }
        await this.calculate_warehouse_totals();
        this.render();
    }

    /**
     * Maneja el hover sobre un producto para mostrar su imagen
     * Implementa carga lazy y cache para optimizar rendimiento
     */
    async onProductHover(event, productId) {
        // Limpiar timeout anterior si existe
        if (this.state.hoverTimeout) {
            clearTimeout(this.state.hoverTimeout);
        }

        // Delay para evitar mostrar tooltip en hovers muy rápidos
        this.state.hoverTimeout = setTimeout(async () => {
            await this.showProductImage(event.target, productId);
        }, 300);
    }

    /**
     * Maneja cuando el mouse sale del producto
     */
    onProductLeave(event) {
        // Limpiar timeout si el mouse sale antes de que se muestre el tooltip
        if (this.state.hoverTimeout) {
            clearTimeout(this.state.hoverTimeout);
            this.state.hoverTimeout = null;
        }

        this.hideProductImage();
    }

    /**
     * Muestra la imagen del producto en un tooltip
     */
    async showProductImage(element, productId) {
        try {
            // Verificar si ya tenemos la imagen en cache
            let imageUrl = this.state.productImagesCache.get(productId);

            if (imageUrl === undefined) {
                // Solo hacer la llamada al backend si no está en cache
                imageUrl = await this.getProductImageUrl(productId);
                this.state.productImagesCache.set(productId, imageUrl);
            }

            // Si no hay imagen disponible, no mostrar tooltip
            if (!imageUrl) {
                return;
            }

            this.positionAndShowTooltip(element, imageUrl);
        } catch (error) {
            console.warn('Error al cargar imagen del producto:', error);
        }
    }

    /**
     * Obtiene la URL de la imagen del producto desde el backend
     * Optimizado para no cargar si el producto no tiene imagen
     */
    async getProductImageUrl(productId) {
        try {
            // Llamada optimizada que solo retorna la URL si existe imagen
            const result = await this.orm.call('product.product', 'get_product_image_url', [productId]);
            return result || null;
        } catch (error) {
            console.warn('Error al obtener URL de imagen del producto:', error);
            return null;
        }
    }

    /**
     * Posiciona y muestra el tooltip con la imagen
     */
    positionAndShowTooltip(element, imageUrl) {
        const tooltip = document.getElementById('product-image-tooltip');
        const tooltipImage = document.getElementById('product-tooltip-image');

        if (!tooltip || !tooltipImage) {
            return;
        }

        // Configurar la imagen
        tooltipImage.src = imageUrl;
        tooltipImage.alt = 'Imagen del producto';

        // Obtener posición del elemento
        const rect = element.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        // Calcular posición óptima para el tooltip
        const tooltipWidth = 100;
        const tooltipHeight = 100;
        const margin = 10;

        let left, top, position;

        // Anclar el tooltip a la FILA completa para que no tape otras celdas
        const rowEl = element.closest('tr');
        const anchorRect = rowEl ? rowEl.getBoundingClientRect() : rect;

        // Intentar posicionar ARRIBA de la fila; si no hay espacio, abajo
        const preferTopTop = anchorRect.top - tooltipHeight - margin;
        const preferBottomTop = anchorRect.bottom + margin;
        if (preferTopTop >= 0) {
            top = preferTopTop;
            position = 'top';
        } else if (preferBottomTop + tooltipHeight <= viewportHeight) {
            top = preferBottomTop;
            position = 'bottom';
        } else {
            // Fallback: mantener dentro de viewport
            top = Math.max(margin, Math.min(anchorRect.top, viewportHeight - tooltipHeight - margin));
            position = 'top';
        }

        // Alinear horizontalmente con el inicio de la fila y mantener dentro del viewport
        left = Math.max(margin, Math.min(anchorRect.left, viewportWidth - tooltipWidth - margin));

        // Aplicar posición y clase
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
        tooltip.className = `product-image-tooltip position-${position}`;

        // Mostrar tooltip
        tooltip.style.display = 'block';
        setTimeout(() => tooltip.classList.add('show'), 10);
    }

    /**
     * Oculta el tooltip de imagen
     */
    hideProductImage() {
        const tooltip = document.getElementById('product-image-tooltip');
        if (tooltip) {
            tooltip.classList.remove('show');
            tooltip.classList.add('none');
        }
    }

    /**
     * Copia al portapapeles: nombre del producto, cantidad vendida y stock de Matilde
     */
    copyCartProductName = async () => {
        try {
            const name = this.state?.cartProductData?.product?.name || '';
            if (!name) {
                this.showWarning('Nombre no disponible');
                return;
            }
            const quantitySold = this.state?.cartProductData?.product?.quantity_sold || 0;
            // Buscar el stock específico de la bodega Matilde
            const matildeWarehouse = this.state?.warehouses?.find(w =>
                w.warehouse_name && w.warehouse_name.toLowerCase().includes('bodega matilde')
            );
            const stockMatilde = matildeWarehouse?.stock || 0;
            const text = `Nombre: "${name}", cantidad vendida: ${quantitySold}, stock Matilde: ${stockMatilde}`;
            await navigator.clipboard.writeText(text);
            this.showSucess('Resumen copiado al portapapeles');
        } catch (e) {
            this.showError('No se pudo copiar el resumen');
        }
    };

    /**
     * Ejecuta el reabastecimiento para la Bodega Matilde usando el mismo
     * método action_replenish que el botón estándar de las reglas de stock.
     * Muestra un cuadro de confirmación antes de ejecutar.
     */
    openMatildeReplenish = async (product) => {
        try {
            if (!product || !product.matilde_orderpoint_id) {
                this.showWarning("No hay una regla de reabastecimiento configurada para Bodega Matilde.");
                return;
            }

            // Mostrar cuadro de confirmación
            const productName = product.product_name || 'este producto';
            const qtyToOrder = product.matilde_qty_to_order || 0;
            const confirmed = confirm(
                `¿Desea ejecutar el reabastecimiento para ${productName}?\n\n` +
                `Cantidad a reabastecer: ${qtyToOrder}\n\n` +
                `Esto generará una orden de compra para Bodega Matilde.`
            );

            if (!confirmed) {
                return; // El usuario canceló
            }

            const orderpointId = product.matilde_orderpoint_id;
            const result = await this.orm.call(
                "stock.warehouse.orderpoint",
                "action_replenish",
                [[orderpointId]]
            );
            // Si devuelve una acción/cliente, la ejecutamos
            if (result) {
                await this.action.doAction(result);
            } else {
                this.showSucess("Reabastecimiento ejecutado para Bodega Matilde.");
            }
        } catch (error) {
            this.showError("No se pudo ejecutar el reabastecimiento para Bodega Matilde.");
        }
    };


//     exportar a excel los datos de la tabla de productos
// javascript
// javascript
    async exportProductsToExcel() {
        const products = this.state.products_filtered || [];
        if (!products.length) {
            this.showError("No hay productos para exportar.");
            return;
        }

        const columns = [
            {key: "product_code", label: "Codigo"},
            {key: "brand", label: "Marca"},
            {key: "uom_po_id", label: "Unidad de compra"},
            {key: "laboratory", label: "Laboratorio"},
            {key: "product_name", label: "Nombre del producto"},
            {key: "price_with_taxes", label: "Pvp "},
            {key: "quantity_sold", label: "Cantidad vendida Unidades"},
            {key: "boxes", label: "Cantidad vendida Cajas"},
            {key: "stock_total", label: "Stock total Unidades"},
            {key: "amount_total", label: "Total vendido en $"},
            {key: "total_cost", label: "Costo en $"},
            {key: "discount", label: "Descuento (%)"},
            {key: "percentage_change_average_cost", label: "% Cambio costo promedio"},
            {key: "utility", label: "Utilidad %"},
            {key: "pvf", label: "PVF"},
            {key: "standar_price_old", label: "Ultimo Costo"},
            {key: "avg_standar_price_old", label: "Costo Promedio"},
        ];

        const normalizeValue = (v) => {
            if (v == null) return "";
            if (Array.isArray(v)) return v.length > 1 ? String(v[1]) : String(v[0] ?? "");
            if (typeof v === "object") return JSON.stringify(v);
            return String(v);
        };

        // Generar CSV simple (puedes adaptar para Excel/SheetJS si prefieres .xlsx)
        const escapeCell = (text) => `"${String(text).replace(/"/g, '""')}"`;
        const headerRow = columns.map(col => escapeCell(col.label)).join(",");
        const dataRows = products.map(prod =>
            columns.map(col => escapeCell(normalizeValue(prod[col.key]))).join(",")
        );
        const csvContent = [headerRow, ...dataRows].join("\r\n");

        // Descargar archivo
        const blob = new Blob([csvContent], {type: "text/csv;charset=utf-8;"});
        const filename = `productos_export_${new Date().toISOString().slice(0, 10)}.csv`;
        if (navigator.msSaveBlob) { // IE10+
            navigator.msSaveBlob(blob, filename);
        } else {
            const link = document.createElement("a");
            const url = URL.createObjectURL(blob);
            link.href = url;
            link.setAttribute("download", filename);
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        }
        this.showSucess("Exportado correctamente (CSV).");
    }


}


SalesReport.template = "sales_report.SalesReport";
actionRegistry.add("sales_report", SalesReport);