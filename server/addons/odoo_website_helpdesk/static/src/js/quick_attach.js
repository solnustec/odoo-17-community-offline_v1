/** @odoo-module **/
import { registry } from "@web/core/registry";
import { FieldOne2Many } from "web.relational_fields";

FieldOne2Many.include({
    /**
     * Cuando el usuario hace clic en “Añadir” de attachment_ids,
     * si aún no existe ID, primero guardamos el ticket.
     */
    async _onAddRecord(ev) {
        // Sólo interceptamos el campo attachment_ids
        if (this.name === 'attachment_ids' && !this.record.id) {
            // trigger_up('save_record') invoca el guardado del registro
            await this.trigger_up('save_record');
        }
        return this._super(...arguments);
    },
});
