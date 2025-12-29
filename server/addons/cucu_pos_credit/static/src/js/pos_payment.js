/** @odoo-module */

import {PosStore} from "@point_of_sale/app/store/pos_store";
import {patch} from "@web/core/utils/patch";
import {PosDB} from "@point_of_sale/app/store/db";
patch(PosStore.prototype, {
    // @Override
    async _processData(loadedData) {
        await super._processData(...arguments);

        this.account_move = loadedData['account.move'];
        this._loadAccountmove(loadedData['account.move']);

        this.account_journal = loadedData['account.journal'];
        this._loadAccountjournal(loadedData['account.journal']);

        this.poscurrency = loadedData['poscurrency'];


        this.db.invoice_sorted = [];
        this.db.invoice_by_id = {};
        this.db.invoice_line_id = {};
        this.db.invoice_search_string = "";
        this.db.invoice_write_date = null;
    },

    _loadAccountmove(invoices) {
        var self = this;
        self.invoices = invoices;

        self.get_invoices_by_id = [];
        invoices.forEach(function (invoice) {
            self.get_invoices_by_id[invoice.id] = invoice;
        });

    },

    _loadAccountjournal(journals) {
        var self = this;
        self.journals = journals;

    },

    load_new_invoices() {
        var self = this;
        var def = new $.Deferred();
        var fields = _.find(this.models, function (model) {
            return model.model === 'account.move';
        }).fields;
        var domain = [['move_type', '=', 'out_invoice'], ['state', '=', 'posted'], ['payment_state', '!=', 'paid']];

        rpc.query({
            model: 'account.move',
            method: 'search_read',
            args: [domain, fields],
        }, {
            timeout: 3000,
            shadow: true,
        })
            .then(function (products) {
                if (self.db.invoices) {
                    def.resolve();
                } else {
                    def.reject();
                }
            }, function (err, event) {
                event.preventDefault();
                def.reject();
            });
        return def;
    },
});


patch(PosDB.prototype, {
    get_invoices_sorted: function (max_count) {
        max_count = max_count ? Math.min(this.invoice_sorted.length, max_count) : this.invoice_sorted.length;
        var invoice = [];
        for (var i = 0; i < max_count; i++) {
            invoices.push(this.invoice_by_id[this.invoice_sorted[i]]);
        }
        return invoices;
    },

    get_product_write_date: function (products) {
        return this.invoice_write_date || "1970-01-01 00:00:00";
    },
});
