/* @odoo-module */
import {patch} from "@web/core/utils/patch";
import {ProductInfoPopup} from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";
import {useService} from "@web/core/utils/hooks";
import {PopupKardex} from "./modal_kardex";
import {_t} from "@web/core/l10n/translation"; // Para las traducciones
import {useState} from "@odoo/owl";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";

patch(ProductInfoPopup.prototype, {
    setup() {
        this.pos = this.env.pos; // Usar el objeto POS directamente
        this.popup = useService("popup"); // Servicio popup
        this.orm = useService("orm"); // Servicio ORM para llamadas al backend
        super.setup(); // Inicialización base
        this.state = useState({
            sale_list: [],
            transfer_list: [],
            combinate_list: [],
        });
    },

    async btnKardex(product) {
        if (!product) {
            return;
        }

        const pos_id = this.pos.config.point_of_sale_id;
        const productId = product.id;
        const get_kardex_product = await this.orm.call('stock.warehouse', 'get_warehouses_by_external_ids', [pos_id]);
        const sales_warehouse_list = await this.orm.call('stock.picking', 'get_pos_sales_by_warehouse', [get_kardex_product, productId]);
        const transfer_warehouse_list = await this.orm.call(
            'stock.picking',
            'get_product_transfers_by_warehouse',
            [get_kardex_product, productId]
        );

        const refund_warehouse_list = await this.orm.call('stock.picking', 'get_pos_refunds_by_warehouse', [get_kardex_product, productId]);
        this.state.sale_list = sales_warehouse_list.result.sales
        this.state.transfer_list = transfer_warehouse_list.result.transfers
        this.state.combinate_list = [
            ...sales_warehouse_list.result.sales,
            ...transfer_warehouse_list.result.transfers,
            ...refund_warehouse_list.result.refund
        ];

        this.popup.add(PopupKardex, {
            title: _t("Información del Producto"),
            product: product,
            combinedData: this.state.combinate_list,
        });

    },


    // // Nueva función para obtener ventas
    //
    // async getProductSales(productId, posConfigId) {
    //     if (!productId) {
    //         console.error("El ID del producto no está definido");
    //         return [];
    //     }
    //
    //     try {
    //         // Consultar las líneas del POS (pos.order.line) asociadas al producto
    //         const posOrderLines = await this.orm.call("pos.order.line", "search_read", [
    //             [["product_id", "=", productId]], // Filtrar por el producto
    //             ["order_id", "qty", "price_unit", "create_date"] // Campos básicos de las líneas
    //         ]);
    //
    //
    //         // Obtener los IDs de las órdenes del POS
    //         const posOrderIds = [...new Set(posOrderLines.map(line => line.order_id[0]))];
    //
    //         if (posOrderIds.length === 0) {
    //             console.warn("No se encontraron órdenes para este producto.");
    //             return [];
    //         }
    //
    //         // Consultar las órdenes del POS asociadas al punto de venta actual usando config_id
    //         const posOrders = await this.orm.call("pos.order", "search_read", [
    //             [
    //                 ["id", "in", posOrderIds], // Filtrar por las órdenes encontradas
    //                 ["session_id.config_id", "=", posConfigId] // Filtrar estrictamente por el ID del punto de venta actual
    //             ],
    //             ["id", "partner_id", "user_id", "date_order"] // Campos relevantes
    //         ]);
    //
    //
    //         // Crear un mapa de orden_id a cliente y usuario
    //         const orderToDetailsMap = {};
    //         for (const order of posOrders) {
    //             orderToDetailsMap[order.id] = {
    //                 customer: order.partner_id,
    //                 user: order.user_id,
    //                 date_order: order.date_order,
    //             };
    //         }
    //
    //         // Asociar los detalles de cliente y usuario a cada línea de pedido
    //         const salesWithDetails = posOrderLines
    //             .filter(line => orderToDetailsMap[line.order_id[0]]) // Filtrar solo líneas asociadas al punto de venta actual
    //             .map(line => {
    //                 const orderDetails = orderToDetailsMap[line.order_id[0]] || {
    //                     customer: ["", "Cliente desconocido"],
    //                     user: ["", "Usuario desconocido"],
    //                     date_order: "Sin fecha",
    //                 };
    //                 return {
    //                     ...line,
    //                     customer: orderDetails.customer,
    //                     user: orderDetails.user,
    //                     date_order: orderDetails.date_order,
    //                     venta: "VENTA",
    //                 };
    //             });
    //
    //         return salesWithDetails;
    //     } catch (error) {
    //         console.error("Error al obtener las ventas del producto:", error);
    //         return [];
    //     }
    // },
    //
    // async getProductTransfers(productId, currentPosLocation) {
    //     if (!productId) {
    //         return [];
    //     }
    //
    //     // Supongamos que esta es la ubicación principal de referencia (puedes obtenerla dinámicamente si es necesario)
    //     const mainStockLocation = "Stock"; // Reemplaza esto con el nombre de tu ubicación principal
    //
    //
    //     // Consultar los movimientos de stock relacionados con el producto
    //     const stockMoves = await this.orm.call("stock.move", "search_read", [
    //         [
    //             ["product_id", "=", productId],
    //             "|", // Filtrar tanto por ubicación origen como destino
    //             ["location_id", "=", currentPosLocation],
    //             ["location_dest_id", "=", currentPosLocation],
    //         ],
    //         ["id","date", "origin", "product_qty", "location_id", "location_dest_id", "create_uid", "picking_type_id"] // Campos relevantes
    //     ]);
    //
    //
    //     // Mapear los datos para estructurarlos y añadir detalles adicionales
    //     const transfers = stockMoves.map(move => {
    //         const isEntry = move.location_dest_id[1] === mainStockLocation; // Es entrada si la ubicación destino es el almacén principal
    //         const isExit = move.location_id[1] === mainStockLocation; // Es salida si la ubicación origen es el almacén principal
    //
    //
    //         return {
    //             date: move.date, // Fecha del movimiento
    //             origin: move.origin || "Sin origen", // Documento de origen
    //             quantity: move.product_qty, // Cantidad transferida
    //             source_location: move.location_id[1] || "Sin ubicación", // Ubicación de origen
    //             destination_location: move.location_dest_id[1] || "Sin destino", // Ubicación de destino
    //             user: move.create_uid[1] || "Desconocido", // Usuario que creó el movimiento
    //             type: isEntry ? "Entrada" : isExit ? "Salida" : "TRANSFERENCIA" // Clasificar el tipo de transferencia
    //         };
    //     });
    //
    //     return transfers;
    // },
    //
    // async getProductRegulation(productId, currentPosLocation) {
    //     if (!productId) {
    //         return [];
    //     }
    //
    //     const domain = [];
    //
    //     domain.push(["location_dest_id", "=", currentPosLocation]);
    //
    //     domain.push(["product_id", "=", productId]);
    //
    //
    //     const stock = await this.orm.call("stock.move", "search_read", [
    //         domain,
    //         ["id","date", "origin", "product_qty", "location_id", "location_dest_id", "create_uid", "picking_type_id"],
    //     ]);
    //
    //     const mainStockLocation = "Stock";
    //
    //
    //     // Mapear los datos para estructurarlos y añadir detalles adicionales
    //     const regulation = stock.map(move => {
    //
    //         const isEntry = move.location_dest_id[1] === mainStockLocation; // Es entrada si la ubicación destino es el almacén principal
    //         const isExit = move.location_id[1] === mainStockLocation; // Es salida si la ubicación origen es el almacén principal
    //
    //
    //         return {
    //             date: move.date, // Fecha del movimiento
    //             origin: move.origin || "Sin origen", // Documento de origen
    //             quantity: move.product_qty, // Cantidad transferida
    //             source_location: move.location_id[1] || "Sin ubicación", // Ubicación de origen
    //             destination_location: move.location_dest_id[1] || "Sin destino", // Ubicación de destino
    //             user: move.create_uid[1] || "Desconocido", // Usuario que creó el movimiento
    //             type: isEntry ? "Entrada" : isExit ? "Salida" : "REGULACIÓN" // Clasificar el tipo de transferencia
    //         };
    //     });
    //
    //
    //     return regulation;
    //
    // },

});

