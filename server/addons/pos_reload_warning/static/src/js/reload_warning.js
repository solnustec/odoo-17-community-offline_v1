/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._setupReloadWarning();
    },

    /**
     * Configura el manejador de advertencia de recarga de página.
     * Muestra una advertencia cuando el usuario intenta recargar la página
     * (F5, Ctrl+R, o botón de recargar) para prevenir pérdida de datos.
     *
     * No muestra la advertencia cuando se está cerrando la sesión de caja
     * (is_close_total = true) para permitir el flujo normal de cierre.
     */
    _setupReloadWarning() {
        // Guardar referencia al PosStore para usarla en el handler
        const posStore = this;

        this._handleBeforeUnload = (event) => {
            // No mostrar advertencia si estamos en proceso de cierre de caja
            // is_closing_session: se activa cuando el usuario confirma el cierre (cualquier opción)
            // is_close_total: se activa específicamente cuando elige "CERRAR SISTEMA"
            if (posStore.is_closing_session || posStore.is_close_total) {
                return;
            }

            // Mostrar advertencia en el POS
            // El navegador mostrará un mensaje genérico de confirmación
            event.preventDefault();
            // Para compatibilidad con navegadores antiguos
            event.returnValue = '';
            return '';
        };

        window.addEventListener('beforeunload', this._handleBeforeUnload);
    },
});
