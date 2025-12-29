/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { useState, useEffect } from "@odoo/owl";

const DateTime = (window.luxon && window.luxon.DateTime) || null;

const _superSetup         = TicketScreen.prototype.setup;
const _superComputeDomain = TicketScreen.prototype._computeSyncedOrdersDomain;
const _superGetFiltered   = TicketScreen.prototype.getFilteredOrderList;
const _superFetchSynced   = TicketScreen.prototype._fetchSyncedOrders;
const _superSetFilter     = TicketScreen.prototype.setFilter || null;

let lastFetchToken = 0;

patch(TicketScreen.prototype, {
    setup(...args) {
        _superSetup.call(this, ...args);
        this.dateRange = useState({ from: "", to: "" });
        this.datePanel = useState({ open: false });
        this.loading   = useState({ visible: false });

        // Para detectar cambios de categoría cuando no hay setFilter()
        this._prevFilter = this._state?.ui?.filter;
        useEffect(
            () => {
                const cur = this._state?.ui?.filter;
                if (cur !== this._prevFilter) {
                    this._onFilterChanged(cur);
                    this._prevFilter = cur;
                }
            },
            () => [this._state?.ui?.filter]
        );
    },

    // --- UI helpers del panel ---
    toggleDatePanel() { this.datePanel.open = !this.datePanel.open; },
    openDatePanel()   { this.datePanel.open = true; },
    closeDatePanel()  { this.datePanel.open = false; },

    // --- Reset del filtro de fecha ---
    _resetDateFilter() {
        this.dateRange.from = "";
        this.dateRange.to   = "";
        this._state.ui.searchDetails = {
            ...(this._state.ui.searchDetails || {}),
            searchTerm: "",
        };
        this.closeDatePanel();
    },

    async _onFilterChanged(newFilter) {
        this._resetDateFilter();
        if (newFilter === "SYNCED") {
            await this._fetchSyncedOrders();
        } else {
            this.render(true);
        }
    },

    // Envoltura de setFilter si existe en tu build
    async setFilter(filter, ...rest) {
        if (_superSetFilter) {
            const res = await _superSetFilter.call(this, filter, ...rest);
            await this._onFilterChanged(filter);
            return res;
        } else {
            // fallback para builds sin setFilter público
            this._state.ui.filter = filter;
            await this._onFilterChanged(filter);
        }
    },

    // ---------- CARGA SINCRONIZADA + LIMPIEZA ----------
    async _fetchSyncedOrders(...args) {
        const myToken = ++lastFetchToken;
        this.loading.visible = true;
        try {
            const res = await _superFetchSynced.call(this, ...args);
            if (myToken !== lastFetchToken) return res;
            this._state.syncedOrders.toShow =
                (this._state.syncedOrders.toShow || []).filter(
                    (o) => o && typeof o.cid !== "undefined"
                );
            return res;
        } finally {
            if (myToken === lastFetchToken) {
                this.loading.visible = false;
            }
        }
    },

    // ---------- APLICAR / LIMPIAR RANGO ----------
    async applyDateRange() {
        if (!(this.dateRange.from && this.dateRange.to)) return;
        this._state.ui.searchDetails = {
            fieldName: "DATE",
            searchTerm: `${this.dateRange.from}..${this.dateRange.to}`,
        };
        if (this._state.ui.filter === "SYNCED") {
            await this._fetchSyncedOrders();
        } else {
            this.render(true);
        }
        this.datePanel.open = false;
    },

    async clearDateRange() {
        this._resetDateFilter();
        if (this._state.ui.filter === "SYNCED") {
            await this._fetchSyncedOrders();
        } else {
            this.render(true);
        }
    },

    // ---------- DOMINIO PARA SYNCED (backend) ----------
    _computeSyncedOrdersDomain(...args) {
        const { fieldName, searchTerm } = this._state.ui.searchDetails || {};
        if (fieldName === "DATE" && searchTerm && searchTerm.includes("..") && DateTime) {
            const [fromIso, toIso] = searchTerm.split("..").map((s) => s.trim());
            const start = DateTime.fromISO(fromIso);
            const end   = DateTime.fromISO(toIso);
            if (start.isValid && end.isValid) {
                const startUTC = start.startOf("day").toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
                const endUTC   = end.endOf("day").toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
                return [
                    ["date_order", ">=", startUTC],
                    ["date_order", "<=", endUTC],
                ];
            }
        }
        return _superComputeDomain ? _superComputeDomain.call(this, ...args) : [];
    },

    // ---------- LISTA FILTRADA (memoria) + LIMPIEZA ----------
    getFilteredOrderList(...args) {
        const base = _superGetFiltered
            ? _superGetFiltered.call(this, ...args)
            : this._getOrderList();

        const safeBase = Array.isArray(base)
            ? base.filter((o) => o && typeof o.cid !== "undefined")
            : [];

        const { fieldName, searchTerm } = this._state.ui.searchDetails || {};
        if (this._state.ui.filter !== "SYNCED" &&
            fieldName === "DATE" &&
            searchTerm?.includes("..") &&
            DateTime
        ) {
            const [fromIso, toIso] = searchTerm.split("..").map((s) => s.trim());
            const start = DateTime.fromISO(fromIso).startOf("day");
            const end   = DateTime.fromISO(toIso).endOf("day");
            if (!start.isValid || !end.isValid) return safeBase;

            return safeBase.filter((order) => {
                const odt = order.date_order instanceof Date
                    ? DateTime.fromJSDate(order.date_order)
                    : DateTime.fromISO(order.date_order);
                if (!odt.isValid) return true;
                return odt >= start && odt <= end;
            });
        }
        return safeBase;
    },
});
