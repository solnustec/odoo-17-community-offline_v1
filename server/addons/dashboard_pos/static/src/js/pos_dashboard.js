/** @odoo-module **/
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
import { debounce } from "@web/core/utils/timing";
import { Component } from "@odoo/owl";
import { onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
const actionRegistry = registry.category("actions");
export class PosDashboard extends Component {
  //Initializes the PosDashboard component,
  static components = { MultiRecordSelector };
  setup() {
    super.setup(...arguments);
    this.orm = useService("orm");
    this.user = useService("user");
    this.actionService = useService("action");
    this.state = useState({
      start_date: this.props.start_date || "",
      end_date: this.props.end_date || "",
      //filters//
      model_search_user: "hr.employee",
      model_search_warehouse: "stock.warehouse",
      model_search_sector: "hr.department",
      selectedUserIds: [],
      selectedWarehouseIds: [],
      selectedSectorIds: [],

      sale_cash: 0.0,
      sale_card: 0.0,
      sale_check_transfer: 0.0,
      sale_credit: 0.0,

      note_credit_cash: 0.0,
      note_credit_card: 0.0,
      note_credit_check_transfer: 0.0,
      note_credit_credit: 0.0,

      scope_card: 0.0,
      scope_check_transfer: 0.0,
      scope_credit: 0.0,
      scope_advance: 0.0,

      note_credit_scope_card: 0.0,
      note_credit_scope_check_transfer: 0.0,
      note_credit_scope_credit: 0.0,

      retention: 0.0,

      advance_cash: 0.0,
      note_credit_advance_cash: 0.0,

      total_scope: 0.0,
      total_cash: 0.0,
      counting_cash: 0.0,
      missing: 0.0,
      surplus: 0.0,

      columnVisibility: [
        { id: "warehouse_name", label: "Bodega", visible: true },
        { id: "date_order", label: "Fecha", visible: true },
        { id: "cashier_employee", label: "Usuario", visible: true },
        { id: "sale_cash", label: "Venta EF", visible: true },
        { id: "sale_card", label: "Venta TC", visible: true },
        { id: "sale_check_transfer", label: "Venta CH/TR", visible: true },
        { id: "sale_credit", label: "Venta CR", visible: true },
        { id: "note_credit_cash", label: "(-) NC EF", visible: true },
        { id: "note_credit_card", label: "(-) NC TC", visible: true },
        {
          id: "note_credit_check_transfer",
          label: "(-) NC CH/TR",
          visible: true,
        },
        { id: "note_credit_credit", label: "(-) NC CR", visible: true },
        { id: "scope_card", label: "Alc. TC", visible: true },
        { id: "scope_check_transfer", label: "Alc. CH/TR", visible: true },
        { id: "scope_credit", label: "Alc. CR", visible: true },
        { id: "scope_advance", label: "Alc. Ant", visible: true },
        { id: "note_credit_scope_card", label: "(-) Alc. TC", visible: true },
        {
          id: "note_credit_scope_check_transfer",
          label: "(-) Alc. CH/TR",
          visible: true,
        },
        { id: "note_credit_scope_credit", label: "(-) Alc. CR", visible: true },
        { id: "retention", label: "(-) Ret", visible: true },
        { id: "advance_cash", label: "Ant. EF", visible: true },
        { id: "note_credit_advance_cash", label: "(-) Ant. EF", visible: true },
        { id: "total_scope", label: "Total Alcances", visible: true },
        { id: "total_cash", label: "Total EF", visible: true },
        { id: "counting_cash", label: "Arqueo EF", visible: true },
        { id: "missing", label: "Faltante", visible: true },
        { id: "surplus", label: "Sobrante", visible: true },
      ],

      user_lang: "es_EC",
      payment_details: [],
      top_salesperson: [],
      selling_product: [],
      total_sale: [],
      total_order_count: [],
      total_refund_count: [],
      total_session: [],
      today_refund_total: [],
      today_sale: [],
      list_orders: [],
      current_page: 1,
      total_pages: 1,
      total_count: 0,

      offset: 0,
      page_size: 20,
      has_more: true,
      is_loading: false,
    });
    this.fetchDebounced = debounce(this.fetch_data.bind(this), 200);
    // When the component is about to start, fetch data in tiles
    onWillStart(async () => {
      const defaultDate = this.getCurrentDate();
      if (!this.state.start_date) {
        this.state.start_date = defaultDate;
      }
      if (!this.state.end_date) {
        this.state.end_date = defaultDate;
      }
      this.fetchDebounced(
        this.state.start_date,
        this.state.end_date,
        this.state.selectedUserIds,
        this.state.selectedWarehouseIds,
        this.state.selectedSectorIds
      );
    });
    //When the component is mounted, render various charts
    onMounted(async () => {
      this.setupScrollListener();
    });

    onWillUnmount(() => {
      this.removeScrollListener();
    });
  }

  onToggleColumn(event) {
    const columnId = event.target.dataset.column;
    console.log("ver dato ", columnId);
    const column = this.state.columnVisibility.find(
      (col) => col.id === columnId
    );
    if (column) {
      column.visible = event.target.checked;
    }
  }

  getCurrentDate() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  openColumnModal() {
    this.state.showColumnModal = true;
  }

  closeColumnModal() {
    this.state.showColumnModal = false;
  }

  selectAllColumns() {
    this.state.columnVisibility.forEach((column) => {
      column.visible = true;
    });
  }

  deselectAllColumns() {
    this.state.columnVisibility.forEach((column) => {
      column.visible = false;
    });
  }

  onUpdateSelectedUsers(selectedUserIds) {
    this.resetData();
    this.state.selectedUserIds = selectedUserIds;
    this.fetchDebounced(
      this.state.start_date,
      this.state.end_date,
      this.state.selectedUserIds,
      this.state.selectedWarehouseIds,
      this.state.selectedSectorIds
    );
  }

  onUpdateSelectedWarehouse(selectedWarehouseIds) {
    this.resetData();
    this.state.selectedWarehouseIds = selectedWarehouseIds;
    this.fetchDebounced(
      this.state.start_date,
      this.state.end_date,
      this.state.selectedUserIds,
      this.state.selectedWarehouseIds,
      this.state.selectedSectorIds
    );
  }

  onUpdateSelectedSector(selectedSectorIds) {
    this.resetData();
    this.state.selectedSectorIds = selectedSectorIds;
  }

  onStartDateChange(ev) {
    this.resetData();
    this.state.start_date = ev.target.value;
    this.fetchDebounced(
      this.state.start_date,
      this.state.end_date,
      this.state.selectedUserIds,
      this.state.selectedWarehouseIds,
      this.state.selectedSectorIds
    );
  }

  onEndDateChange(ev) {
    this.resetData();
    this.state.end_date = ev.target.value;
    this.fetchDebounced(
      this.state.start_date,
      this.state.end_date,
      this.state.selectedUserIds,
      this.state.selectedWarehouseIds,
      this.state.selectedSectorIds
    );
  }

  async loadOrders() {
    const orders = await this.orm.searchRead(
      "pos.order",
      [["id", "in", this.state.selectedOrderIds]], // Filtrar por IDs seleccionados
      ["cashier"] // Campos a recuperar
    );
    this.state.list_orders = orders; // Actualizar la lista de órdenes
  }

  setupScrollListener() {
    const tableContainer = document.querySelector(".table-container");
    if (tableContainer) {
      tableContainer.addEventListener("scroll", this.handleScroll.bind(this));
    }
  }

  removeScrollListener() {
    const tableContainer = document.querySelector(".table-container");
    if (tableContainer) {
      tableContainer.removeEventListener(
        "scroll",
        this.handleScroll.bind(this)
      );
    }
  }

  handleScroll() {
    const tableContainer = document.querySelector(".table-container");
    if (!tableContainer) return;

    const scrollBottom =
      tableContainer.scrollHeight -
      tableContainer.scrollTop -
      tableContainer.clientHeight;
    if (scrollBottom < 50 && !this.state.is_loading && this.state.has_more) {
      this.fetchDebounced(
        this.state.start_date,
        this.state.end_date,
        this.state.selectedUserIds,
        this.state.selectedWarehouseIds,
        this.state.selectedSectorIds
      );
    }
  }

  resetData() {
    this.state.list_orders = [];
    this.state.offset = 0;
    this.state.has_more = true;
    this.state.is_loading = false;
    this.state.sale_cash = 0.0;
    this.state.sale_card = 0.0;
    this.state.sale_check_transfer = 0.0;
    this.state.sale_credit = 0.0;
    this.state.note_credit_cash = 0.0;
    this.state.note_credit_card = 0.0;
    this.state.note_credit_check_transfer = 0.0;
    this.state.note_credit_credit = 0.0;
    this.state.scope_card = 0.0;
    this.state.scope_check_transfer = 0.0;
    this.state.scope_credit = 0.0;
    this.state.scope_advance = 0.0;
    this.state.note_credit_scope_card = 0.0;
    this.state.note_credit_scope_check_transfer = 0.0;
    this.state.note_credit_scope_credit = 0.0;
    this.state.retention = 0.0;
    this.state.advance_cash = 0.0;
    this.state.note_credit_advance_cash = 0.0;
    this.state.total_scope = 0.0;
    this.state.total_cash = 0.0;
    this.state.counting_cash = 0.0;
    this.state.missing = 0.0;
    this.state.surplus = 0.0;
  }

  async fetch_data(
    startDate = null,
    endDate = null,
    filter_users = [],
    filter_warehouse = [],
    filter_sector = []
  ) {
    if (!this.state.has_more || this.state.is_loading) return;

    const list_data_full = await this.orm.call("pos.order", "get_user_pos", [
      this.state.offset,
      this.state.page_size,
      startDate,
      endDate,
      filter_users,
      filter_warehouse,
      filter_sector,
    ]);

    this.state.list_orders = [
      ...this.state.list_orders,
      ...list_data_full.orders,
    ];
    this.state.user_lang = list_data_full.user_lang;
    const totals = list_data_full.totals;

    this.state.sale_cash = totals.sale_cash;
    this.state.sale_card = totals.sale_card;
    this.state.sale_check_transfer = totals.sale_check_transfer;
    this.state.sale_credit = totals.sale_credit;

    this.state.note_credit_cash = totals.note_credit_cash;
    this.state.note_credit_card = totals.note_credit_card;
    this.state.note_credit_check_transfer = totals.note_credit_check_transfer;
    this.state.note_credit_credit = totals.note_credit_credit;

    this.state.scope_card = totals.scope_card;
    this.state.scope_check_transfer = totals.scope_check_transfer;
    this.state.scope_credit = totals.scope_credit;
    this.state.scope_advance = totals.scope_advance;

    this.state.note_credit_scope_card = totals.note_credit_scope_card;
    this.state.note_credit_scope_check_transfer =
      totals.note_credit_scope_check_transfer;
    this.state.note_credit_scope_credit = totals.note_credit_scope_credit;

    this.state.retention = totals.retention;

    this.state.advance_cash = totals.advance_cash;
    this.state.note_credit_advance_cash = totals.note_credit_advance_cash;

    this.state.total_scope = totals.total_scope;
    this.state.total_cash = totals.total_cash;
    this.state.counting_cash = totals.counting_cash;
    this.state.missing = totals.missing;
    this.state.surplus = totals.surplus;

    this.state.user_lang = list_data_full.user_lang;

    this.state.offset += this.state.page_size;
    this.state.has_more = list_data_full.orders.length === this.state.page_size;
    this.state.is_loading = false;

    //  Function to fetch all the pos details
    var result = await this.orm.call("pos.order", "get_refund_details", []);
    (this.state.total_sale = result["total_sale"]),
      (this.state.total_order_count = result["total_order_count"]);
    this.state.total_refund_count = result["total_refund_count"];
    this.state.total_session = result["total_session"];
    this.state.today_refund_total = result["today_refund_total"];
    this.state.today_sale = result["today_sale"];
    var data = await this.orm.call("pos.order", "get_details", []);
    this.state.payment_details = data["payment_details"];
    this.state.top_salesperson = data["salesperson"];
    this.state.selling_product = data["selling_product"];
  }
  pos_order_today(e) {
    //To get the details of today's order
    var self = this;
    var date = new Date();
    var yesterday = new Date(date.getTime());
    yesterday.setDate(date.getDate() - 1);
    e.stopPropagation();
    e.preventDefault();
    this.user.hasGroup("hr.group_hr_user").then(function (has_group) {
      if (has_group) {
        var options = {
          on_reverse_breadcrumb: self.on_reverse_breadcrumb,
        };
        self.actionService.doAction(
          {
            name: _t("Today Order"),
            type: "ir.actions.act_window",
            res_model: "pos.order",
            view_mode: "tree,form,calendar",
            view_type: "form",
            views: [
              [false, "list"],
              [false, "form"],
            ],
            domain: [
              ["date_order", "<=", date],
              ["date_order", ">=", yesterday],
            ],
            target: "current",
          },
          options
        );
      }
    });
  }
  pos_refund_orders(e) {
    //   To get the details of refund orders
    var self = this;
    var date = new Date();
    var yesterday = new Date(date.getTime());
    yesterday.setDate(date.getDate() - 1);
    e.stopPropagation();
    e.preventDefault();
    this.user.hasGroup("hr.group_hr_user").then(function (has_group) {
      if (has_group) {
        var options = {
          on_reverse_breadcrumb: self.on_reverse_breadcrumb,
        };
        self.actionService.doAction(
          {
            name: _t("Refund Orders"),
            type: "ir.actions.act_window",
            res_model: "pos.order",
            view_mode: "tree,form,calendar",
            view_type: "form",
            views: [
              [false, "list"],
              [false, "form"],
            ],
            domain: [["amount_total", "<", 0.0]],
            target: "current",
          },
          options
        );
      }
    });
  }
  pos_refund_today_orders(e) {
    //  To get the details of today's order
    var self = this;
    var date = new Date();
    var yesterday = new Date(date.getTime());
    yesterday.setDate(date.getDate() - 1);
    e.stopPropagation();
    e.preventDefault();
    this.user.hasGroup("hr.group_hr_user").then(function (has_group) {
      if (has_group) {
        var options = {
          on_reverse_breadcrumb: self.on_reverse_breadcrumb,
        };
        self.actionService.doAction(
          {
            name: _t("Refund Orders"),
            type: "ir.actions.act_window",
            res_model: "pos.order",
            view_mode: "tree,form,calendar",
            view_type: "form",
            views: [
              [false, "list"],
              [false, "form"],
            ],
            domain: [
              ["amount_total", "<", 0.0],
              ["date_order", "<=", date],
              ["date_order", ">=", yesterday],
            ],
            target: "current",
          },
          options
        );
      }
    });
  }
  pos_order(e) {
    //    To get total orders details
    var self = this;
    var date = new Date();
    var yesterday = new Date(date.getTime());
    yesterday.setDate(date.getDate() - 1);
    e.stopPropagation();
    e.preventDefault();
    this.user.hasGroup("hr.group_hr_user").then(function (has_group) {
      if (has_group) {
        var options = {
          on_reverse_breadcrumb: self.on_reverse_breadcrumb,
        };
        self.actionService.doAction(
          {
            name: _t("Total Order"),
            type: "ir.actions.act_window",
            res_model: "pos.order",
            view_mode: "tree,form,calendar",
            view_type: "form",
            views: [
              [false, "list"],
              [false, "form"],
            ],
            target: "current",
          },
          options
        );
      }
    });
  }
  pos_session(e) {
    //    To get the Session wise details
    var self = this;
    e.stopPropagation();
    e.preventDefault();
    this.user.hasGroup("hr.group_hr_user").then(function (has_group) {
      if (has_group) {
        var options = {
          on_reverse_breadcrumb: self.on_reverse_breadcrumb,
        };
        self.actionService.doAction(
          {
            name: _t("sessions"),
            type: "ir.actions.act_window",
            res_model: "pos.session",
            view_mode: "tree,form,calendar",
            view_type: "form",
            views: [
              [false, "list"],
              [false, "form"],
            ],
            target: "current",
          },
          options
        );
      }
    });
  }

  async downloadExcel() {
    if (this.state.list_orders.length === 0) {
      alert("No hay datos disponibles para exportar a Excel.");
      return;
    }

    // Orden fijo deseado
    const orderedColumnLabels = [
      "Bodega",
      "Fecha",
      "Usuario",
      "Venta CR",
      "Venta TC",
      "Venta CH/TR",
      "Venta EF",
      "(-) NC EF",
      "(-) Ret",
      "Total Alcances",
      "(-) Ant. EF",
      "Total EF",
      "Arqueo EF",
      "Faltante",
      "Sobrante",
      "(-) NC TC",
      "(-) NC CH/TR",
      "(-) NC CR",
      "Alc. TC",
      "Alc. CH/TR",
      "Alc. CR",
      "Alc. Ant",
      "(-) Alc. TC",
      "(-) Alc. CH/TR",
      "(-) Alc. CR",
      "Ant. EF",
    ];

    // Ordenar y filtrar solo las columnas visibles, en el orden deseado
    const visibleColumns = orderedColumnLabels
      .map((label) =>
        this.state.columnVisibility.find((col) => col.label === label)
      )
      .filter((col) => col && col.visible);

    // Obtener encabezados remapeados en el orden correcto
    const headers = visibleColumns.map((col) => col.label);

    // Reordenar filas según el orden de columnas
    const data = this.state.list_orders.map((order) => {
      const row = {};
      visibleColumns.forEach((col) => {
        row[col.label] = order[col.id] ?? "";
      });
      return row;
    });

    const filters = {
      start_date: this.state.start_date,
      end_date: this.state.end_date,
      selectedUserIds: this.state.selectedUserIds,
      selectedWarehouseIds: this.state.selectedWarehouseIds,
      selectedSectorIds: this.state.selectedSectorIds,
    };

    // Preparar el payload para enviar al controlador
    const payload = {
      headers: headers,
      data: data,
      filters: filters,
    };

    try {
      const response = await fetch("/dashboard_pos/export_excel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token":
            document.querySelector('meta[name="csrf-token"]')?.content || "",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("Error al generar el archivo Excel");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "pos_dashboard_export.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error al descargar el Excel:", error);
      alert(
        "Hubo un error al generar el archivo Excel. Por favor, intenta de nuevo."
      );
    }
  }

  async downloadPdf() {
    if (!this.state.list_orders || this.state.list_orders.length === 0) {
      alert("No hay órdenes disponibles para generar el PDF.");
      return;
    }

    if (
      !this.state.columnVisibility ||
      this.state.columnVisibility.length === 0
    ) {
      alert("No hay columnas visibles configuradas para generar el PDF.");
      return;
    }

    // Orden fijo deseado
    const orderedColumnLabels = [
      "Bodega",
      "Fecha",
      "Usuario",
      "Venta CR",
      "Venta TC",
      "Venta CH/TR",
      "Venta EF",
      "(-) NC EF",
      "(-) Ret",
      "Total Alcances",
      "(-) Ant. EF",
      "Total EF",
      "Arqueo EF",
      "Faltante",
      "Sobrante",
      "(-) NC TC",
      "(-) NC CH/TR",
      "(-) NC CR",
      "Alc. TC",
      "Alc. CH/TR",
      "Alc. CR",
      "Alc. Ant",
      "(-) Alc. TC",
      "(-) Alc. CH/TR",
      "(-) Alc. CR",
      "Ant. EF",
    ];

    // Diccionario de remapeo
    const headerMapping = {
      Bodega: "Bodega",
      Fecha: "Fecha",
      Usuario: "Usuario",
      "Venta CR": "V.CR",
      "Venta TC": "V.TC",
      "Venta CH/TR": "V.CH/TR",
      "Venta EF": "V.EF",
      "(-) NC EF": "(-) Nc.EF",
      "(-) Ret": "(-) Ret",
      "Total Alcances": "TotalAlc.",
      "(-) Ant. EF": "(-) Ant.EF",
      "Total EF": "TotalEF",
      "Arqueo EF": "Arqueo EF",
      Faltante: "Falt.",
      Sobrante: "Sobr.",
      "(-) NC TC": "(-) Nc.TC",
      "(-) NC CH/TR": "(-) Nc.CH/TR",
      "(-) NC CR": "(-) Nc.CR",
      "Alc. TC": "Alc.TC",
      "Alc. CH/TR": "Alc.CH/TR",
      "Alc. CR": "Alc.CR",
      "Alc. Ant": "Alc.Ant",
      "(-) Alc. TC": "(-) Alc.TC",
      "(-) Alc. CH/TR": "(-) Alc.CH/TR",
      "(-) Alc. CR": "(-) Alc.CR",
      "Ant. EF": "Ant.EF",
    };

    // Ordenar y filtrar solo las columnas visibles, en el orden deseado
    const visibleColumns = orderedColumnLabels
      .map((label) =>
        this.state.columnVisibility.find((col) => col.label === label)
      )
      .filter((col) => col && col.visible);

    // Obtener encabezados remapeados en el orden correcto
    const headers = visibleColumns.map(
      (col) => headerMapping[col.label] || col.label
    );

    // Reordenar filas según el orden de columnas
    const data = this.state.list_orders.map((order) => {
      const row = {};
      visibleColumns.forEach((col) => {
        const header = headerMapping[col.label] || col.label;
        row[header] = order[col.id] ?? "";
      });
      return row;
    });

    // Reordenar totales
    const totals = {};
    visibleColumns.forEach((col) => {
      const header = headerMapping[col.label] || col.label;
      totals[header] = this.state[col.id];
    });

    const filters = {
      start_date: this.state.start_date,
      end_date: this.state.end_date,
      selectedUserIds: this.state.selectedUserIds,
      selectedWarehouseIds: this.state.selectedWarehouseIds,
      selectedSectorIds: this.state.selectedSectorIds,
    };

    const payload = {
      headers: headers,
      data: data,
      filters: filters,
      totals: totals,
    };
    // Verificar si las fechas son iguales
    if (this.state.start_date === this.state.end_date) {
      try {
        const response = await fetch("/pos_dashboard/simple_pdf_report", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token":
              document.querySelector('meta[name="csrf-token"]')?.content || "",
          },
          body: JSON.stringify(payload),
          credentials: "include",
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Error ${response.status}: ${errorText}`);
        }

        // Descargar archivo PDF
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `pos_dashboard_export.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error("Error al generar PDF:", error);
        alert(error.message);
      }
    } else {
      alert("Fecha Desde y Hasta deben ser iguales para descargar el PDF.");
    }
  }
}

PosDashboard.template = "PosDashboard"; // Asocia el componente con su plantilla
actionRegistry.add("pos_order_menu", PosDashboard); // Registra el componente en el sistema de acciones
