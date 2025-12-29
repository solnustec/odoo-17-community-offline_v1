/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";

registry.category("user_menuitems").remove("log_out");

function customLogOutItem(env) {
  const route = "/custom/force_logout";
  return {
    type: "item",
    id: "logout",
    description: _t("Log out"),
    href: `${browser.location.origin}${route}`,
    callback: async () => {
      // console.log("🔔 [Logout] Ejecución de callback personalizada INICIADA");

      // 1. Limpiar LocalStorage y SessionStorage
      // console.log("🗑️ [Logout] Limpiando localStorage y sessionStorage...");
      localStorage.clear();
      sessionStorage.clear();

      // 2. Limpiar Cache Storage
      if ("caches" in window) {
        try {
          const names = await caches.keys();
          // console.log("🗑️ [Logout] Limpiando caches:", names);
          await Promise.all(names.map((n) => caches.delete(n)));
        } catch (e) {
          // console.warn("⚠️ [Logout] Error limpiando Cache Storage", e);
        }
      }

      // 3. Limpiar IndexedDB
      if ("indexedDB" in window && indexedDB.databases) {
        try {
          const dbs = await indexedDB.databases();
          // console.log(
          //   "🗑️ [Logout] Limpiando IndexedDB:",
          //   dbs.map((db) => db.name)
          // );
          await Promise.all(dbs.map((db) => indexedDB.deleteDatabase(db.name)));
        } catch (e) {
          // console.warn("⚠️ [Logout] Error limpiando IndexedDB", e);
        }
      }

      // 4. Limpiar cookies accesibles desde JS
      try {
        const cookies = document.cookie
          .split(";")
          .map((c) => c.split("=")[0].trim());
        // console.log("🗑️ [Logout] Limpiando cookies accesibles:", cookies);
        document.cookie.split(";").forEach(function (c) {
          document.cookie = c
            .replace(/^ +/, "")
            .replace(
              /=.*/,
              "=;expires=" + new Date().toUTCString() + ";path=/"
            );
        });
      } catch (e) {
        console.warn(
          "⚠️ Error en Cierre de Sesion. Favor notificar a Sistemas",
          e
        );
      }

      // 5. Esperar un poco para asegurar la limpieza
      await new Promise((res) => setTimeout(res, 200));
      // console.log(
      //   "✅ [Logout] Limpieza completada. Redirigiendo a logout de Odoo..."
      // );

      // 6. Redirigir a logout real de Odoo
      browser.location.href = route;
    },
    sequence: 70,
  };
}

registry.category("user_menuitems").add("log_out", customLogOutItem);
