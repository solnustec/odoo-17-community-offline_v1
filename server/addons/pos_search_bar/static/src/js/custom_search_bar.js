/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { _t } from "@web/core/l10n/translation";

// Guardamos referencias a los métodos originales
const originalGetSearchFields = TicketScreen.prototype._getSearchFields;
const originalComputeSyncedOrdersDomain = TicketScreen.prototype._computeSyncedOrdersDomain;

// 1) Extendemos _getSearchFields para incluir búsqueda por cajero
TicketScreen.prototype._getSearchFields = function () {
  const fields = originalGetSearchFields.apply(this, arguments) || {};
  fields.CASHIER = {
    repr: (order) => (order?.cashier?.name ?? ""),
    displayName: _t("Cashier"),
    modelField: "user_id.name",
  };
  return fields;
};

// 2) Ajustamos el dominio de búsqueda en servidor para el campo 'CASHIER'
TicketScreen.prototype._computeSyncedOrdersDomain = function () {
  const details = this._state?.ui?.searchDetails || {};
  if (details.fieldName === "CASHIER") {
    const term = (details.searchTerm || "").trim();
    if (!term) {
      return [];
    }
    return [["user_id.name", "ilike", `%${term}%`]];
  }
  return originalComputeSyncedOrdersDomain.apply(this, arguments) || [];
};