//** @odoo-module */

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { RecordSelectorReadonly } from "@stock_transfer_in_pos/js/record_selector_extend";

// ============================================
// Componente Principal del Modal
// ============================================
export class TransferModal extends Component {
    static template = "TransferModal";
    static components = { RecordSelectorReadonly };


    static props = {
        zIndex: { type: Number, optional: true },
    }

    setup() {
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.pos = usePos();

        this.state = useState({
            activeTab: 'sent',
            sentTransfers: [],
            receivedTransfers: [],
            pendingProducts: [],
            // Paginación
            sentPage: 0,
            receivedPage: 0,
            pendingProductsPage: 0,
            sentHasMore: true,
            receivedHasMore: true,
            pendingProductsHasMore: true,
            isLoadingSent: false,
            isLoadingReceived: false,
            isLoadingPendingProducts: false,
            selectedWO: false,

            // Configuración de transferencias automáticas
            filterAutoTransfers: false,

            // filtros
            product_id: false,
            filterDateFrom: null,
            filterDateTo: null,

            // Filtros para transferencias enviadas
            filterDestinationId: false,
            filterSentState: '',
            filterSentDateFrom: null,
            filterSentDateTo: null,

            // Filtros para recibidas
            filterReceivedOriginId: false,
            filterReceivedState: '',
            filterReceivedDateFrom: null,
            filterReceivedDateTo: null,
        });

        this.LIMIT = 20;

        // Referencias para los contenedores de scroll
        this.sentScrollRef = useRef("sentScrollRef");
        this.receivedScrollRef = useRef("receivedScrollRef");
        this.pendingProductsScrollRef = useRef("pendingProductsScrollRef");

        onWillStart(async () => {
            this.state.selectedWO = await this.orm.call(
                'stock.picking',
                'get_warehouse_from_config',
                [[this.pos.pos_session.config_id[0]]],
                {}
            );

            // Obtener configuración de transferencias automáticas
            const transferConfig = await this.orm.call(
                'stock.picking',
                'get_transfer_config',
                [[this.pos.pos_session.config_id[0]]],
                {}
            );
            this.state.filterAutoTransfers = transferConfig.filter_auto_transfers || false;

            await this.loadTransfers('sent');
            await this.loadTransfers('received');
            await this.loadPendingProducts();
        });

        onMounted(() => {
            this.setupScrollListeners();
        });

        onWillUnmount(() => {
            this.removeScrollListeners();
        });
    }

    async loadTransfers(type) {
        let isLoadingKey, pageKey, hasMoreKey, transfersKey, domain;

        switch(type) {
            case 'sent':
                isLoadingKey = 'isLoadingSent';
                pageKey = 'sentPage';
                hasMoreKey = 'sentHasMore';
                transfersKey = 'sentTransfers';

                // Dominio base para enviadas
                domain = [["location_id.warehouse_id", "=", this.state.selectedWO]];

                // Filtrar transferencias automáticas si está configurado
                if (this.state.filterAutoTransfers) {
                    domain.push(['is_auto_replenishment', '=', false]);
                }

                // APLICAR FILTROS PARA ENVIADAS
                if (this.state.filterDestinationId) {
                    domain.push(['location_dest_id.warehouse_id', '=', this.state.filterDestinationId]);
                }

                if (this.state.filterSentState) {
                    domain.push(['state', '=', this.state.filterSentState]);
                }

                if (this.state.filterSentDateFrom) {
                    domain.push(['date', '>=', this.state.filterSentDateFrom + ' 00:00:00']);
                }

                if (this.state.filterSentDateTo) {
                    domain.push(['date', '<=', this.state.filterSentDateTo + ' 23:59:59']);
                }
                break;

            case 'received':
                isLoadingKey = 'isLoadingReceived';
                pageKey = 'receivedPage';
                hasMoreKey = 'receivedHasMore';
                transfersKey = 'receivedTransfers';

                // Dominio base para recibidas
                domain = [["location_dest_id.warehouse_id", "=", this.state.selectedWO]];

                // Filtrar transferencias automáticas si está configurado
                if (this.state.filterAutoTransfers) {
                    domain.push(['is_auto_replenishment', '=', false]);
                }

                // APLICAR FILTROS PARA RECIBIDAS (si los tienes)
                if (this.state.filterReceivedOriginId) {
                    domain.push(['location_id.warehouse_id', '=', this.state.filterReceivedOriginId]);
                }

                if (this.state.filterReceivedState) {
                    domain.push(['state', '=', this.state.filterReceivedState]);
                }
                if (this.state.filterReceivedDateFrom) {
                    domain.push(['date', '>=', this.state.filterReceivedDateFrom + ' 00:00:00']);
                }

                if (this.state.filterReceivedDateTo) {
                    domain.push(['date', '<=', this.state.filterReceivedDateTo + ' 23:59:59']);
                }
                break;

            default:
                return;
        }

        if (this.state[isLoadingKey] || !this.state[hasMoreKey]) {
            return;
        }

        this.state[isLoadingKey] = true;

        try {
            const offset = this.state[pageKey] * this.LIMIT;

            // 1. Obtén las transferencias básicas
            const transfers = await this.orm.searchRead(
                "stock.picking",
                [
                    ...domain,
                    ['picking_type_id.code', '=', 'internal']
                ],
                ["name", "date", "location_id", "location_dest_id", "user_id", "state", "type_transfer"],
                {
                    limit: this.LIMIT,
                    offset: offset,
                    order: "date desc, id desc"
                }
            );

            // 2. Extrae todos los IDs únicos de ubicaciones
            const locationIds = new Set();
            transfers.forEach(t => {
                if (t.location_id && t.location_id[0]) locationIds.add(t.location_id[0]);
                if (t.location_dest_id && t.location_dest_id[0]) locationIds.add(t.location_dest_id[0]);
            });

            // 3. Si hay ubicaciones, obtén sus warehouses
            let locationWarehouseMap = {};
            if (locationIds.size > 0) {
                const locations = await this.orm.searchRead(
                    "stock.location",
                    [['id', 'in', Array.from(locationIds)]],
                    ["id", "warehouse_id"]
                );

                locations.forEach(loc => {
                    locationWarehouseMap[loc.id] = loc.warehouse_id ? loc.warehouse_id[1] : 'Sin almacén';
                });
            }

            // 4. Enriquece los transfers con la info del warehouse
            const enrichedTransfers = transfers.map(transfer => ({
                ...transfer,
                origin_warehouse: transfer.location_id ?
                    locationWarehouseMap[transfer.location_id[0]] : undefined,
                destination_warehouse: transfer.location_dest_id ?
                    locationWarehouseMap[transfer.location_dest_id[0]] : undefined
            }));

            if (transfers.length < this.LIMIT) {
                this.state[hasMoreKey] = false;
            }

            const formattedTransfers = this.formatTransfers(enrichedTransfers);

            this.state[transfersKey].push(...formattedTransfers);

            this.state[pageKey]++;
        } catch (error) {
            console.error(`Error loading ${type} transfers:`, error);
        } finally {
            this.state[isLoadingKey] = false;
        }
    }


    async loadPendingProducts() {
        if (this.state.isLoadingPendingProducts || !this.state.pendingProductsHasMore) {
            return;
        }

        this.state.isLoadingPendingProducts = true;

        try {
            const offset = this.state.pendingProductsPage * this.LIMIT;

            // Construir dominio base
            const domain = [
                ["location_dest_id.warehouse_id", "=", this.state.selectedWO],
                ["state", "in", ["draft", "waiting", "confirmed", "assigned"]],
                ['picking_type_id.code', '=', 'internal']
            ];

            // Filtrar transferencias automáticas si está configurado
            if (this.state.filterAutoTransfers) {
                domain.push(['is_auto_replenishment', '=', false]);
            }

            // Agregar filtro de fecha si existe
            if (this.state.filterDateFrom) {
                domain.push(['date', '>=', this.state.filterDateFrom + ' 00:00:00']);
            }

            if (this.state.filterDateTo) {
                domain.push(['date', '<=', this.state.filterDateTo + ' 23:59:59']);
            }

            // 1. Consultar transferencias pendientes
            const pendingTransfers = await this.orm.searchRead(
                "stock.picking",
                domain,
                ["id", "name", "date", "location_id", "location_dest_id", "user_id", "state", "type_transfer"],
                {
                    limit: this.LIMIT,
                    offset: offset,
                    order: "date desc, id desc"
                }
            );

            if (pendingTransfers.length < this.LIMIT) {
                this.state.pendingProductsHasMore = false;
            }

            // 2. Extrae todos los IDs únicos de ubicaciones
            const locationIds = new Set();
            pendingTransfers.forEach(t => {
                if (t.location_id && t.location_id[0]) locationIds.add(t.location_id[0]);
                if (t.location_dest_id && t.location_dest_id[0]) locationIds.add(t.location_dest_id[0]);
            });

            // 3. Si hay ubicaciones, obtén sus warehouses
            let locationWarehouseMap = {};
            if (locationIds.size > 0) {
                const locations = await this.orm.searchRead(
                    "stock.location",
                    [['id', 'in', Array.from(locationIds)]],
                    ["id", "warehouse_id"]
                );

                locations.forEach(loc => {
                    locationWarehouseMap[loc.id] = loc.warehouse_id ? loc.warehouse_id[1] : 'Sin almacén';
                });
            }

            // 4. Enriquece los transfers con la info del warehouse
            const enrichedTransfers = pendingTransfers.map(transfer => ({
                ...transfer,
                origin_warehouse: transfer.location_id ?
                    locationWarehouseMap[transfer.location_id[0]] : undefined,
                destination_warehouse: transfer.location_dest_id ?
                    locationWarehouseMap[transfer.location_dest_id[0]] : undefined
            }));

            // 5. Para cada transferencia, buscar sus productos
            for (const transfer of enrichedTransfers) {
                // Construir dominio para productos con filtro opcional
                const productDomain = [['picking_id', '=', transfer.id]];

                // FILTRO DE PRODUCTO aplicado aquí
                if (this.state.product_id) {
                    productDomain.push(['product_id', '=', this.state.product_id]);
                }

                const products = await this.orm.searchRead(
                    "stock.move",
                    productDomain,
                    ["id", "product_id", "product_qty", "quantity", "product_uom", "state"],
                    {}
                );

                // Solo agregar si hay productos (importante cuando filtras)
                if (products.length > 0) {
                    const formattedProducts = products.map(product => ({
                        id: product.id,
                        transfer_id: transfer.id,
                        transfer_obj: transfer,
                        transfer_name: transfer.name,
                        transfer_date: transfer.date || transfer.scheduled_date,
                        product_id: product.product_id[0],
                        product_name: product.product_id[1],
                        quantity_expected: product.product_qty,
                        quantity_done: product.quantity,
                        location_origin: transfer.origin_warehouse,
                        location_dest: transfer.destination_warehouse,
                        state: transfer.state,
                        uom: product.product_uom ? product.product_uom[1] : 'Unidades'
                    }));

                    this.state.pendingProducts.push(...formattedProducts);
                }
            }

            this.state.pendingProductsPage++;
        } catch (error) {
            console.error("Error loading pending products:", error);
        } finally {
            this.state.isLoadingPendingProducts = false;
        }
    }

    async loadTransferProducts(transferId) {
        try {
            const moves = await this.orm.searchRead(
                "stock.move",
                [["picking_id", "=", transferId]],
                ["product_id", "product_qty", "quantity", "product_uom"]
            );
            return moves;
        } catch (error) {
            console.error("Error loading transfer products:", error);
            return [];
        }
    }

    formatTransfers(transfers) {
        return transfers.map(transfer => ({
            id: transfer.id,
            name: transfer.name,
            type_transfer: transfer.type_transfer == 1 ? "Express" : "Normal",
            date: transfer.date || transfer.scheduled_date,
            origin: transfer.origin_warehouse,
            destination: transfer.destination_warehouse,
            origin_location: transfer.location_id[1],
            destination_location: transfer.location_dest_id[1],
            responsible: transfer.user_id ? transfer.user_id[1] : "Sin asignar",
            state: transfer.state,
        }));
    }

    async reloadTransfers(type) {
        const config = {
            'sent': {
                transfers: 'sentTransfers',
                page: 'sentPage',
                hasMore: 'sentHasMore'
            },
            'received': {
                transfers: 'receivedTransfers',
                page: 'receivedPage',
                hasMore: 'receivedHasMore'
            },
            'pendingProducts': {
                transfers: 'pendingProducts',
                page: 'pendingProductsPage',
                hasMore: 'pendingProductsHasMore'
            }
        };

        const { transfers, page, hasMore } = config[type];
        this.state[transfers] = [];
        this.state[page] = 0;
        this.state[hasMore] = true;

        if (type === 'pendingProducts') {
            await this.loadPendingProducts();
        } else {
            await this.loadTransfers(type);
        }
    }

    setupScrollListeners() {
        // Configurar event listeners para scroll
        if (this.sentScrollRef.el) {
            this.sentScrollRef.el.addEventListener('scroll', this.onScrollSent.bind(this));
        }
        if (this.receivedScrollRef.el) {
            this.receivedScrollRef.el.addEventListener('scroll', this.onScrollReceived.bind(this));
        }
        if (this.pendingProductsScrollRef.el) {
            this.pendingProductsScrollRef.el.addEventListener('scroll', this.onScrollPendingProducts.bind(this));
        }
    }

    removeScrollListeners() {
        // Remover event listeners al desmontar
        if (this.sentScrollRef.el) {
            this.sentScrollRef.el.removeEventListener('scroll', this.onScrollSent.bind(this));
        }
        if (this.receivedScrollRef.el) {
            this.receivedScrollRef.el.removeEventListener('scroll', this.onScrollReceived.bind(this));
        }
        if (this.pendingProductsScrollRef.el) {
            this.pendingProductsScrollRef.el.removeEventListener('scroll', this.onScrollPendingProducts.bind(this));
        }
    }

    // Scroll para transferencias enviadas
    onScrollSent(event) {
        const container = event.target;
        const { scrollTop, scrollHeight, clientHeight } = container;

        // Cargar más cuando esté cerca del final (80% del scroll)
        if (scrollHeight - scrollTop - clientHeight < 100 &&
            !this.state.isLoadingSent &&
            this.state.sentHasMore) {
            this.loadTransfers('sent');
        }
    }

    // Scroll para transferencias recibidas
    onScrollReceived(event) {
        const container = event.target;
        const { scrollTop, scrollHeight, clientHeight } = container;

        // Cargar más cuando esté cerca del final (80% del scroll)
        if (scrollHeight - scrollTop - clientHeight < 100 &&
            !this.state.isLoadingReceived &&
            this.state.receivedHasMore) {
            this.loadTransfers('received');
        }
    }

    // Scroll para productos pendientes
    onScrollPendingProducts(event) {
        const container = event.target;
        const { scrollTop, scrollHeight, clientHeight } = container;

        // Cargar más cuando esté cerca del final (80% del scroll)
        if (scrollHeight - scrollTop - clientHeight < 100 &&
            !this.state.isLoadingPendingProducts &&
            this.state.pendingProductsHasMore) {
            this.loadPendingProducts();
        }
    }


    async switchTab(tab) {
        this.state.activeTab = tab;

        // Esperar a que el DOM se actualice con la nueva pestaña
        await new Promise(resolve => setTimeout(resolve, 100));
        this.setupScrollListeners();
    }

    formatDate(date) {
        if (!date) return "-";
        const d = new Date(date);
        return d.toLocaleDateString('es-ES', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getStatusBadge(state) {
        const badges = {
            'draft': 'bg-secondary',
            'waiting': 'bg-warning',
            'confirmed': 'bg-info',
            'assigned': 'bg-primary',
            'done': 'bg-success',
            'cancel': 'bg-danger',
        };
        return badges[state] || 'bg-secondary';
    }

    getStatusText(state) {
        const texts = {
            'draft': 'Borrador',
            'waiting': 'En espera de otra operación',
            'confirmed': 'En espera',
            'assigned': 'Listo',
            'done': 'Hecho',
            'cancel': 'Cancelado',
        };
        return texts[state] || state;
    }


    // Métodos para la pestaña de productos pendientes
    async viewProductTransfer(product) {
        // Cargar todos los productos de la transferencia para mostrar el detalle completo
        const transferProducts = await this.loadTransferProducts(product.transfer_id);
        const transfer = {
            id: product.transfer_id,
            name: product.transfer_name,
            date: product.transfer_date,
            origin: product.location_origin,
            destination: product.location_dest,
            state: product.state,
            products: transferProducts.map(p => ({
                id: p.id,
                name: p.product_id[1],
                quantity: String(p.product_qty),
                quantity_done: String(p.quantity),
            }))
        };

        await this.popup.add(TransferDetailModal, {
            transfer: transfer,
            editable: false,
            zIndex: 20,
        });
    }

    async validateProduct(product) {
        // Cargar todos los productos de la transferencia para validación
        const transferProducts = await this.loadTransferProducts(product.transfer_id);
        const transfer = {
            id: product.transfer_id,
            name: product.transfer_name,
            date: product.transfer_date,
            origin: product.location_origin,
            destination: product.location_dest,
            state: product.state,
            products: transferProducts.map(p => ({
                id: p.id,
                name: p.product_id[1],
                quantity: String(p.product_qty),
                quantity_done: String(p.quantity),
            }))
        };

        const result = await this.popup.add(TransferValidationModal, {
            transfer: transfer,
        });

        if (result) {
            await this.reloadTransfers('pendingProducts');
            await this.reloadTransfers('received');
        }
    }

    // Métodos existentes para las otras pestañas
    async viewTransfer(transfer) {
        // Cargar productos de la transferencia
        const products = await this.loadTransferProducts(transfer.id);
        const editable = false;

        await this.popup.add(TransferDetailModal, {
            transfer: { ...transfer, products },
            editable,
            zIndex: 10008,
        });
    }

    async editTransfer(transfer) {
        const products = await this.loadTransferProducts(transfer.id);
        const result = await this.popup.add(TransferDetailModal, {
            transfer: { ...transfer, products },
            editable: true,
            zIndex: 10008,
        });

        if (result) {
            await this.reloadTransfers('sent');
        }
    }

    async validateTransfer(transfer) {
        const products = await this.loadTransferProducts(transfer.id);
        const result = await this.popup.add(TransferValidationModal, {
            transfer: { ...transfer, products },
        });

        if (result) {
            await this.reloadTransfers('received');
            await this.reloadTransfers('pendingProducts');
        }
    }

    async rejectTransfer(transfer) {
        const confirmed = await this.popup.add(ConfirmPopup, {
            title: _t("Rechazar Transferencia"),
            body: _t(`¿Está seguro que desea rechazar la transferencia ${transfer.name}?`),
        });

        if (confirmed) {
            try {
                await this.orm.write("stock.picking", [transfer.id], {
                    state: "cancel"
                });
                await this.reloadTransfers(this.state.activeTab);
            } catch (error) {
                console.error("Error rejecting transfer:", error);
            }
        }
    }

    close() {
        this.props.close();
    }

    async applyFiltersAndReload() {
        // Resetear completamente el estado de productos pendientes
        this.state.pendingProducts = [];
        this.state.pendingProductsPage = 0;
        this.state.pendingProductsHasMore = true;

        // Recargar con los filtros aplicados
        await this.loadPendingProducts();
    }

    onUpdateFilterProduct(product_id){
        this.state.product_id = product_id;
        this.applyFiltersAndReload()
    }

    onFilterChangeDateFrom(ev) {
        this.state.filterDateFrom = ev.target.value;
        this.applyFiltersAndReload()
    }

    onFilterChangeDateTo(ev) {
        this.state.filterDateTo = ev.target.value;
        this.applyFiltersAndReload()
    }

    clearFilters() {
        this.state.product_id = false;
        this.state.filterDateFrom = null;
        this.state.filterDateTo = null;

        this.applyFiltersAndReload();
    }

    onUpdateFilterDestination(resId) {
        this.state.filterDestinationId = resId;
    }

    onFilterChangeSentState(ev) {
        this.state.filterSentState = ev.target.value;
    }

    onFilterChangeSentDateFrom(ev) {
        this.state.filterSentDateFrom = ev.target.value;
    }

    onFilterChangeSentDateTo(ev) {
        this.state.filterSentDateTo = ev.target.value;
    }

    get hasSentActiveFilters() {
        return !!(
            this.state.filterDestinationId ||
            this.state.filterSentState ||
            this.state.filterSentDateFrom ||
            this.state.filterSentDateTo
        );
    }

    async clearSentFilters() {

        this.state.filterDestinationId = null;
        this.state.filterSentState = '';
        this.state.filterSentDateFrom = null;
        this.state.filterSentDateTo = null;

        // Resetear estado
        this.state.sentTransfers = [];
        this.state.sentPage = 0;
        this.state.sentHasMore = true;

        // Recargar sin filtros
        await this.loadSentTransfers();
    }

    async clearSentFilters() {

        // Limpiar filtros
        this.state.filterDestinationId = false;
        this.state.filterSentState = '';
        this.state.filterSentDateFrom = null;
        this.state.filterSentDateTo = null;

        // Resetear estado
        this.state.sentTransfers = [];
        this.state.sentPage = 0;
        this.state.sentHasMore = true;

        // Recargar sin filtros
        await this.loadTransfers('sent');
    }

    async applySentFiltersAndReload() {

        // Resetear estado de enviadas
        this.state.sentTransfers = [];
        this.state.sentPage = 0;
        this.state.sentHasMore = true;

        // Recargar con filtros
        await this.loadTransfers('sent');
    }


    onUpdateFilterReceivedOrigin(resId) {
        this.state.filterReceivedOriginId = resId;
    }

    onFilterChangeReceivedState(ev) {
        this.state.filterReceivedState = ev.target.value;
    }

    onFilterChangeReceivedDateFrom(ev) {
        this.state.filterReceivedDateFrom = ev.target.value;
    }

    onFilterChangeReceivedDateTo(ev) {
        this.state.filterReceivedDateTo = ev.target.value;
    }

    get hasReceivedActiveFilters() {
        return !!(
            this.state.filterReceivedOriginId ||
            this.state.filterReceivedState ||
            this.state.filterReceivedDateFrom ||
            this.state.filterReceivedDateTo
        );
    }

    async applyReceivedFiltersAndReload() {

        this.state.receivedTransfers = [];
        this.state.receivedPage = 0;
        this.state.receivedHasMore = true;

        await this.loadTransfers('received');
    }

    async clearReceivedFilters() {
        this.state.filterReceivedOriginId = false;
        this.state.filterReceivedState = '';
        this.state.filterReceivedDateFrom = null;
        this.state.filterReceivedDateTo = null;

        this.state.receivedTransfers = [];
        this.state.receivedPage = 0;
        this.state.receivedHasMore = true;

        await this.loadTransfers('received');
    }




}


// ============================================
// Modal de Detalle de Transferencia
// ============================================
export class TransferDetailModal extends Component {
    static template = "TransferDetailModal";
    static components = { RecordSelectorReadonly };
    static props = {
        transfer: Object,
        editable: { type: Boolean, optional: true },
        close: Function, // Esta es importante
        // Agrega estas props para evitar el error
        id: { type: [String, Number], optional: true },
        zIndex: { type: Number, optional: true },
        cancelKey: { type: String, optional: true },
        confirmKey: { type: String, optional: true },
        id: { type: String, optional: true },
        resolve: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            products: [...this.props.transfer.products],
        });

        this.orm = useService("orm");
    }

    formatDate(date) {
        if (!date) return "-";
        const d = new Date(date);
        return d.toLocaleDateString('es-ES', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getStatusBadge(state) {
        const badges = {
            'draft': 'bg-secondary',
            'waiting': 'bg-warning',
            'confirmed': 'bg-info',
            'assigned': 'bg-primary',
            'done': 'bg-success',
            'cancel': 'bg-danger',
        };
        return badges[state] || 'bg-secondary';
    }

    getStatusText(state) {
        const texts = {
            'draft': 'Borrador',
            'waiting': 'En espera de otra operación',
            'confirmed': 'En espera',
            'assigned': 'Listo',
            'done': 'Hecho',
            'cancel': 'Cancelado',
            'waiting_approval': 'Esperando aprobación',
            'rejected': 'Rechazado',
        };
        return texts[state] || state;
    }

    updateQuantity(productId, newQuantity) {
        const product = this.state.products.find(p => p.id === productId);
        if (product) {
            product.quantity = parseFloat(newQuantity) || 0;
        }
    }

    removeProduct(productId) {
        const index = this.state.products.findIndex(p => p.id === productId);
        if (index !== -1) {
            this.state.products.splice(index, 1);
        }
    }

    async save() {
        try {
            // Actualizar cantidades en la base de datos
            for (const product of this.state.products) {
                await this.orm.write("stock.move", [product.id], {
                    product_uom_qty: product.quantity
                });
            }

            this.props.close({ saved: true });
        } catch (error) {
            console.error("Error saving transfer:", error);
        }
    }

    close() {
        this.props.close();
    }
}

// ============================================
// Modal de Validación de Transferencia Recibida
// ============================================
export class TransferValidationModal extends Component {
    static template = "TransferValidationModal";
    static components = { RecordSelectorReadonly };
    static props = {
        transfer: Object,
        close: Function,
    };

    setup() {
        this.state = useState({
            validationProducts: this.props.transfer.products.map(p => ({
                ...p,
                quantity_sent: p.product_qty,
                quantity_received: p.product_qty, // Por defecto, la cantidad esperada
            })),
            notes: "",
        });

        this.orm = useService("orm");
    }

    formatDate(date) {
        if (!date) return "-";
        const d = new Date(date);
        return d.toLocaleDateString('es-ES', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    updateReceivedQuantity(productId, newQuantity) {
        const product = this.state.validationProducts.find(p => p.id === productId);
        if (product) {
            product.quantity_received = parseFloat(newQuantity) || 0;
        }
    }

    getDifferenceClass(product) {
        const diff = product.quantity_received - product.quantity_sent;
        if (diff < 0) return 'table-warning';
        if (diff > 0) return 'table-info';
        return '';
    }

    async validate() {
        try {
            // Actualizar cantidades recibidas
            for (const product of this.state.validationProducts) {
                await this.orm.write("stock.move", [product.id], {
                    quantity: product.quantity_received
                });
            }

            // Validar la transferencia
            const validate_button = await this.orm.call(
                "stock.picking",
                "button_validate",
                [[this.props.transfer.id]]
            );

//            if (validate_button && validate_button.type === "ir.actions.act_window") {
//                const res = await this.env.services.action.doAction(validate_button);
//
//
//            } else {
//                this.env.services.notification.add(
//                    "Transferencia validada correctamente",
//                    { type: "success" }
//                );
//            }

            // Guardar notas si existen
            if (this.state.notes) {
                await this.orm.write("stock.picking", [this.props.transfer.id], {
                    note: this.state.notes
                });
            }

            this.props.close({ validated: true });
        } catch (error) {
            console.error("Error validating transfer:", error);
        }
    }

    async reject() {
        try {
            await this.orm.write("stock.picking", [this.props.transfer.id], {
                state: "cancel",
                note: this.state.notes || "Transferencia rechazada"
            });

            this.props.close({ rejected: true });
        } catch (error) {
            console.error("Error rejecting transfer:", error);
        }
    }

    close() {
        this.props.close();
    }
}