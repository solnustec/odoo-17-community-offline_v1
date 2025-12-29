//** @odoo-module */
import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

export class PopupHistoriClient extends AbstractAwaitablePopup {
  static template = "bi_pos_check_info.OrderLinePopup";

  setup() {
    super.setup();

    this.pos = usePos();
    this.popup = useService("popup");
    this.groupedProducts = {};
    this.actionService = useService("action");
    this.props = this.props || {};
    this.state = useState({
      vatClient: localStorage.getItem("vatClient") || "", // Cargar desde localStorage
      groupedProducts: {},
    });
    this.loadVatNumber();
  }

  loadVatNumber() {
    const order = this.pos.get_order();
    if (order && order.partner && order.partner.vat) {
      const vat = order.partner.vat;
      localStorage.setItem("vatClient", vat); // Guardar en localStorage
      this.state.vatClient = vat; // Actualizar el estado en tiempo real
    }
  }

  onInputChange(event) {
    this.state.vatClient = event.target.value;
    localStorage.setItem("vatClient", event.target.value); // Guardar en localStorage en tiempo real
  }

  async searchClient() {
    const inputValue = document.getElementById("history").value;
    await this.getIdentificationClient(inputValue);
  }

  async getHistory(idClient) {
    try {
      const url = `/api-proxy/visualpy_server_get_hist/${idClient}`;
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer cuxiloja2025__"
        },
      });
      if (!response.ok) {
        throw new Error(`Error: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      const jsonConvert = JSON.parse(data.data);
      await this.showClientInfo(jsonConvert);
    } catch (error) {
      console.error("Error al buscar el cliente:", error);
      alert(
        "Ocurrió un error al buscar el cliente. Por favor, intenta nuevamente."
      );
    }
  }

  async getIdentificationClient(idClient) {
    try {
      const url = `/api/contacts`;
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ vat: idClient }),
      });

      if (!response.ok) {
        throw new Error(`Error: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      await this.getHistory(data.result[0].data[0].id_database_old);
    } catch (error) {
      console.error("Error al buscar el cliente:", error);
      alert(
        "Ocurrió un error al buscar el cliente. Por favor, intenta nuevamente."
      );
    }
  }

  async showClientInfo(data) {
    try {
      if (!data || !data.d) {
        console.error("Los datos recibidos no contienen la clave 'd':", data);
        alert("Error al obtener los datos del cliente.");
        return;
      }

      let productIds = [...new Set(data.d.map((item) => item[5]))];

      if (productIds.length === 0) {
        console.warn("No se encontraron productos en los datos del cliente.");
        alert("No se encontraron productos en el historial del cliente.");
        return;
      }

      const productsData = await this.getProduct(productIds);
      const productMap = productsData.reduce((acc, product) => {
        acc[product.id_db_old] = product.name;
        return acc;
      }, {});

      const enrichedData = data.d.map((item) => ({
        ...item,
        product_name: productMap[item[5]] || "Producto desconocido",
      }));

      this.groupedProducts = this.groupByField(enrichedData, 6);
      console.log("Productos agrupados:", this.groupedProducts);

      await this.updateModal(this.groupedProducts);
    } catch (error) {
      console.error("Error al procesar los datos del cliente:", error);
      alert("Error al obtener los productos. Intente nuevamente.");
    }
  }

  async getProduct(productIds) {
    const url = "/api/products/search";
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_ids: productIds }),
    });

    if (!response.ok) {
      throw new Error(`Error: ${response.status} ${response.statusText}`);
    }

    const returnData = await response.json();
    return returnData.result.data;
  }

  groupByField(data, position) {
    return data.reduce((acc, item) => {
      const key = item[position];
      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push(item);
      return acc;
    }, {});
  }

  filterByDate() {
    const startDate = new Date(document.getElementById("startDate").value);
    const endDate = new Date(document.getElementById("endDate").value);

    const filteredProducts = {};

    Object.keys(this.groupedProducts).forEach((groupKey) => {
      const group = this.groupedProducts[groupKey].filter((item) => {
        const purchaseDate = new Date(item[1]); // Fecha en la posición 1
        return purchaseDate >= startDate && purchaseDate <= endDate;
      });

      if (group.length > 0) {
        filteredProducts[groupKey] = group;
      }
    });

    this.updateModal(filteredProducts);
  }

  async updateModal(groupedProducts) {
    // Obtiene el elemento de la tabla donde se mostrarán los datos
    const tableBody = document.querySelector("#tableBody");
    tableBody.innerHTML = ""; // Limpia el contenido previo de la tabla

    // Conjunto para almacenar IDs de bodegas únicas
    const warehouseIds = new Set();

    // Itera sobre los grupos de productos para extraer IDs de bodegas únicas
    Object.keys(groupedProducts).forEach((groupKey) => {
      const firstProduct = groupedProducts[groupKey][0]; // Toma el primer producto del grupo
      if (!firstProduct) return; // Si el grupo está vacío, salta a la siguiente iteración
      warehouseIds.add(firstProduct[2]); // Agrega el ID de la bodega al conjunto
    });

    // Convierte los IDs de bodegas a cadenas de 8 dígitos con ceros a la izquierda
    const formattedWarehouseIds = [...warehouseIds].map((id) =>
      id.toString().padStart(8, "0")
    );
    // console.log("Enviando external_ids corregidos:", formattedWarehouseIds);

    // Obtiene los nombres de las bodegas usando los IDs formateados
    const warehouseNames =
      formattedWarehouseIds.length > 0
        ? await this.getWarehouseNames.call(this, formattedWarehouseIds)
        : { warehouses: [] }; // Si no hay IDs, usa un objeto vacío para evitar errores

    // console.log("Nombres de bodegas:", warehouseNames);

    // Author: Fabricio Franco
    // Date: 2025-03-31
    // Description: Mejora la funcion para obtener el nombre de la bodega y exponerla en el fron junto al historial
    // Se agrega la función getBodegaName para obtener el nombre de la bodega

    // Itera sobre los grupos de productos para crear filas en la tabla
    Object.keys(groupedProducts).forEach((groupKey) => {
      const firstProduct = groupedProducts[groupKey][0]; // Toma el primer producto del grupo
      if (!firstProduct) return; // Si el grupo está vacío, salta a la siguiente iteración

      const invoiceDate = new Date(firstProduct[1]).toLocaleDateString(); // Formatea la fecha de la factura
      const user = firstProduct[3]; // Obtiene el usuario
      const bodegaId = firstProduct[2].toString().padStart(8, "0"); // Formatea el ID de la bodega

      // Función para obtener el nombre de la bodega dado su ID
      const getBodegaName = (warehouseData, bodegaId) => {
        // Verifica si los datos de las bodegas son válidos
        if (
          !warehouseData ||
          !warehouseData.warehouses ||
          !Array.isArray(warehouseData.warehouses)
        ) {
          return "Bodega no se puede determinar";
        }
        // Busca la bodega por su ID y devuelve su nombre
        const warehouse = warehouseData.warehouses.find(
          (w) => w.external_id === bodegaId
        );
        return warehouse ? warehouse.name : "Bodega desconocida";
      };

      //   console.log("1warehouseNames:", warehouseNames);
      //   console.log("2bodegaId:", bodegaId);

      const bodegaName = getBodegaName(warehouseNames, bodegaId); // Obtiene el nombre de la bodega

      // Crea la fila del encabezado del grupo
      const groupHeader = `
            <tr style="background-color: #f0f0f0;">
                <td colspan="5" style="font-weight: bold; text-align: start">
                    Factura: ${groupKey} - ${invoiceDate} - ${user} - ${bodegaName}
                </td>
            </tr>
        `;
      tableBody.innerHTML += groupHeader; // Agrega el encabezado a la tabla

      // Itera sobre los productos del grupo para crear filas de productos
      groupedProducts[groupKey].forEach((product) => {
        // Crea una fila para el producto
        const row = `
                <tr>
                    <td>${product.product_name}</td>
                    <td>${product[7]}</td>
                    <td>${product[9]}</td>
                    <td>${product[8]}%</td>
                    <td>${product[11]}</td>
                </tr>
            `;
        tableBody.innerHTML += row; // Agrega la fila a la tabla
      });
    });
  }

  async getWarehouseNames(warehouseIds) {
    console.log("Enviando external_ids:", warehouseIds);

    try {
      // Verifica si se recibieron IDs de bodega
      if (!Array.isArray(warehouseIds) || warehouseIds.length === 0) {
        console.warn("No se recibieron IDs de bodega para consultar.");
        return {};
      }

      // Obtiene el servicio ORM de Odoo
      const orm = this.orm || this.env.services.orm;
      if (!orm) {
        console.error("ORM no está disponible en este contexto.");
        return {};
      }

      // Llama al método del ORM para obtener los nombres de las bodegas
      const params = { external_ids: warehouseIds };
      const result = await orm.call(
        "stock.warehouse",
        "get_warehouses_by_external_ids",
        [params]
      );

      // Verifica si se encontraron bodegas
      if (!result || Object.keys(result).length === 0) {
        console.warn(
          "No se encontraron bodegas para los IDs proporcionados:",
          warehouseIds
        );
        return {};
      }

      //   console.log("Nombres de bodegas obtenidos:", result);
      return result; // Devuelve los nombres de las bodegas
    } catch (error) {
      console.error("Error al obtener los nombres de las bodegas:", error);
      return {};
    }
  }

  confirm() {
    console.log("clickaaaa");
  }

  cancel() {
    this.props.close({ confirmed: false, payload: null });
  }
}
