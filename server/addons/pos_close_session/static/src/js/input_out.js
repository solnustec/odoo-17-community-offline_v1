/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(PosStore.prototype, {
  async mounted() {
    await super.mounted(...arguments);
  },

  async _processData(loadedData) {
    await super._processData(loadedData);
    if (loadedData["pos.session"]) {
      const session = loadedData["pos.session"];
      const sessionId = session.id;
      this.outMoneyPOS = session?.out_money_point_of_sale || 0.0;
    }
  },
});

patch(ClosePosPopup.prototype, {
  setup() {
    super.setup();
    this.rpc = useService("rpc");
    this.state.out_money_point_of_sale = this.pos.outMoneyPOS || 0.0;
  },

  async confirm() {
    const sessionId = this.pos.pos_session.id;
    // 1) send the cash-out value
    const raw = document.getElementById("data_out").value;
    const outValue = parseFloat(raw) || 0;
    await this.rpc("/web/dataset/call_kw/pos.session/write", {
      model: "pos.session",
      method: "write",
      args: [[sessionId], { out_money_point_of_sale: outValue }],
      kwargs: { context: {} },
    });

    // 2) ConfirmPopup and only return once the user clicks “De acuerdo” or “Cancelar”.
    const res = await super.confirm(...arguments);

    // 3) after closing second popup, open the ticket PDF
    await this.waitAndOpenPDF(sessionId);
    // console.log("🔄 Limpiando storage al cerrar sesión POS");
    // console.log("LocalStorage Antes de limpiar:", Object.keys(localStorage));
    // console.log(
    //   "🔎 SessionStorage ANTES de limpiar:",
    //   Object.keys(sessionStorage)
    // );
    // Cleanning LocalStorage y SessionStorage
    localStorage.clear();
    sessionStorage.clear();

    return res;
  },

  async waitAndOpenPDF(sessionId, retries = 10, delay = 1500) {
    // console.log("[waitAndOpenPDF] start", { sessionId, retries, delay });
    if (!sessionId || typeof sessionId !== "number") {
      // console.log("[waitAndOpenPDF] Invalid sessionId", sessionId);
      return;
    }

    const fetchTicketAndOpen = async () => {
      // console.log(
      //   "[fetchTicketAndOpen] Attempt RPC pos.close.session.user.ticket/search_read",
      //   { sessionId }
      // );
      try {
        const result = await this.rpc(
          "/web/dataset/call_kw/pos.close.session.user.ticket/search_read",
          {
            model: "pos.close.session.user.ticket",
            method: "search_read",
            args: [
              [["pos_session_id", "=", sessionId]],
              ["id", "pos_session_id"],
            ],
            kwargs: {
              limit: 1,
              order: "id desc",
            },
          }
        );
        // console.log("[fetchTicketAndOpen] RPC result", result);

        if (result.length > 0 && result[0].pos_session_id[0] === sessionId) {
          const ticketId = result[0].id;
          const url = `/report/pdf/pos_close_session.report_user_ticket/${ticketId}`;
          // console.log("[fetchTicketAndOpen] Opening PDF", { url, ticketId });
          window.open(url, "_blank");
        } else if (retries > 0) {
          // console.log("[fetchTicketAndOpen] Retry", { retriesLeft: retries });
          setTimeout(fetchTicketAndOpen, delay);
        } else {
          console.warn(
            "Se encontró el ticket, y no se pudo abrir pdf, ver Vista de tickets de cierre de sesión."
          );
          window.location.href =
            "/web?reload=true#action=1827&model=pos.close.session.user.ticket&view_type=list&cids=1&menu_id=918";
        }
      } catch (err) {
        window.location.href = "/web?";
      }
    };

    fetchTicketAndOpen();
  },
});
