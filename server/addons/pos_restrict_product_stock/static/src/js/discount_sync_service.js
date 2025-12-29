//** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {useState} from "@odoo/owl";

export function setupPOSDiscountSync() {
    patch(ProductScreen.prototype, {
        setup() {
            super.setup();
            // Acceder al bus_service directamente desde env.services (no usar useService)
            this.busService = this.env.services.bus_service;
            this.notification = useService("pos_notification");
            this.orm = useService("orm");

            // Estado reactivo para forzar re-renders
            this.stockUpdateState = useState({ lastUpdate: Date.now() });

            // Escuchar notificaciones de descuento y stock
            if (this.busService) {
                this.busService.addChannel("broadcast");
                this.busService.addEventListener("notification", this.onMessage.bind(this));
                console.log("✅ POS escuchando notificaciones de bus_service (broadcast channel)");
            } else {
                console.warn("⚠️ bus_service no disponible en este contexto");
            }
        },

        onMessage({detail: notifications}) {
            console.log("📩 Notificaciones recibidas en POS:", notifications);

            notifications.forEach((notification) => {
                console.log("🔔 Tipo de notificación:", notification.type);

                if (notification.type === "POS-GLOBAL-NOTIFICATION-FROM-DISCOUNT") {
                    console.log("✅ Se recibió la notificación en el POS:", notification.payload.message);
                    this.notification.add({
                        title: "Actualización de Descuentos",
                        body: notification.payload.message,
                    });
                }

                // Manejar actualización de stock por transferencia
                if (notification.type === "POS_STOCK_UPDATE") {
                    console.log("📦 Actualización de stock recibida:", notification.payload);
                    this._handleStockUpdate(notification.payload);
                }
            });
        },

        async _handleStockUpdate(payload) {
            const productIds = payload.product_ids || [];
            const transferValidated = payload.transfer_validated || false;
            const pos = this.env.services.pos;
            const posSession = pos.pos_session;

            if (!posSession || productIds.length === 0) {
                return;
            }

            console.log("📦 Procesando actualización de stock para productos:", productIds);
            console.log("📦 Transfer validated:", transferValidated);

            // Siempre consultar al servidor para obtener el stock actualizado
            // Esto es más robusto que intentar determinar si somos origen o destino
            await this._refreshStockFromServer(productIds, pos, posSession);

            // Forzar re-renderizado del componente
            this._forceProductScreenRefresh(productIds);

            // Disparar evento para que otros componentes se actualicen
            document.dispatchEvent(new CustomEvent('pos-stock-updated', {
                detail: { productIds, transferValidated }
            }));

            // Mostrar notificación al usuario
            this.notification.add({
                title: transferValidated ? "Transferencia Recibida" : "Stock Actualizado",
                body: payload.message || "El inventario ha sido actualizado por una transferencia",
            });
        },

        async _refreshStockFromServer(productIds, pos, posSession) {
            console.log("🔄 Consultando stock actualizado desde el servidor...");
            try {
                // Obtener stock de todos los productos en una sola llamada (mucho más rápido)
                const stockData = await this.orm.call(
                    "product.product",
                    "pos_stock_bulk_update",
                    [posSession.id, productIds]
                );

                // Actualizar cada producto con los datos recibidos
                for (const productId of productIds) {
                    const data = stockData[productId];
                    if (data) {
                        const product = pos.db.product_by_id[productId];
                        if (product) {
                            product.pos_stock_available = data.pos_stock_available;
                            product.pos_stock_incoming = data.pos_stock_incoming;
                            console.log(`✅ Stock actualizado para producto ${productId}: disponible=${data.pos_stock_available}, por recibir=${data.pos_stock_incoming}`);
                        }
                    }
                }
            } catch (error) {
                console.error("❌ Error actualizando stock de productos:", error);
            }
        },

        _forceProductScreenRefresh(productIds) {
            try {
                // Actualizar el estado reactivo para forzar re-render
                this.stockUpdateState.lastUpdate = Date.now();

                const pos = this.env.services.pos;

                // Forzar una actualización de los productos visibles actualizando el DOM directamente
                // Usamos el ID del input de barcode para encontrar cada tarjeta de producto
                for (const productId of productIds) {
                    const product = pos.db.product_by_id[productId];
                    if (!product) continue;

                    // Encontrar el input de barcode usando su ID único
                    const barcodeInput = document.getElementById(`barcode-${productId}`);
                    if (!barcodeInput) {
                        console.log(`⚠️ No se encontró elemento para producto ${productId} en la vista actual`);
                        continue;
                    }

                    // Navegar al contenedor padre (.py-1) que contiene todos los badges
                    const container = barcodeInput.closest('.py-1');
                    if (!container) {
                        console.log(`⚠️ No se encontró contenedor .py-1 para producto ${productId}`);
                        continue;
                    }

                    // Actualizar el badge de stock
                    const stockBadge = container.querySelector('.badge-stock');
                    if (stockBadge) {
                        stockBadge.innerHTML = `Stock: ${product.pos_stock_available}`;
                        console.log(`✅ Stock actualizado en DOM para producto ${productId}: ${product.pos_stock_available}`);
                    }

                    // Manejar el badge de "Por recibir"
                    const existingIncomingBadge = container.querySelector('.badge-incoming-stock');

                    if (product.pos_stock_incoming > 0) {
                        if (existingIncomingBadge) {
                            // Actualizar el badge existente
                            existingIncomingBadge.innerHTML = `Por recibir: ${product.pos_stock_incoming}`;
                            console.log(`✅ Incoming actualizado en DOM para producto ${productId}: ${product.pos_stock_incoming}`);
                        } else {
                            // Crear nuevo badge después del row de stock/descuento
                            const stockRow = stockBadge?.closest('.row.g-2');
                            if (stockRow) {
                                const newRow = document.createElement('div');
                                newRow.className = 'row g-2 text-center mb-2';
                                newRow.innerHTML = `<div class="col-12"><div class="badge-incoming-stock">Por recibir: ${product.pos_stock_incoming}</div></div>`;
                                stockRow.parentNode.insertBefore(newRow, stockRow.nextSibling);
                                console.log(`✅ Badge incoming creado para producto ${productId}: ${product.pos_stock_incoming}`);
                            }
                        }
                    } else if (existingIncomingBadge) {
                        // Remover el badge si el incoming es 0
                        const incomingRow = existingIncomingBadge.closest('.row.g-2');
                        if (incomingRow) {
                            incomingRow.remove();
                            console.log(`✅ Badge incoming removido para producto ${productId} (stock incoming = 0)`);
                        }
                    }
                }

                // También intentar el método de render estándar de OWL
                if (this.__owl__ && this.__owl__.status === 1) {
                    this.render(true);
                }

                console.log("✅ Interfaz actualizada para productos:", productIds);
            } catch (e) {
                console.warn("No se pudo forzar re-render:", e);
            }
        },
    });
}

// Llamar a la función para activar el listener
setupPOSDiscountSync();
