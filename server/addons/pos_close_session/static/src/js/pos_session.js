/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    redirectToBackend() {
        if (this.is_close_total){
            this.clearClientData()
        } else {
            window.location = "/web#action=point_of_sale.action_client_pos_menu";
        }
    },

    async clearClientData() {
        const results = {
            localStorage: false,
            sessionStorage: false,
            cookies: false,
            caches: false,
            indexedDB: false,
            serviceWorkers: false,
            webSQL: false
        };

        // 1. Clear localStorage
        try {
            localStorage.clear();
            results.localStorage = true;
        } catch (error) {
            console.warn("Error limpiando localStorage:", error);
        }

        // 2. Clear sessionStorage
        try {
            sessionStorage.clear();
            results.sessionStorage = true;
        } catch (error) {
            console.warn("Error limpiando sessionStorage:", error);
        }

        // 3. Clear cookies (versión más agresiva)
        try {
            // Obtener todos los cookies
            const cookies = document.cookie.split(";");

            // Borrar con diferentes combinaciones de path y domain
            const domains = [window.location.hostname, `.${window.location.hostname}`];
            const paths = ['/', '/app', '/admin', ''];

            cookies.forEach((cookie) => {
                const eqPos = cookie.indexOf("=");
                const name = eqPos > -1 ? cookie.substr(0, eqPos).trim() : cookie.trim();

                if (name) {
                    // Intentar borrar con diferentes combinaciones
                    domains.forEach(domain => {
                        paths.forEach(path => {
                            document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=${path};domain=${domain}`;
                            document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=${path}`;
                        });
                    });
                }
            });

            results.cookies = true;
        } catch (error) {
            console.warn("Error limpiando cookies:", error);
        }

        // 4. Clear caches
        try {
            if ('caches' in window) {
                const keys = await caches.keys();
                await Promise.all(keys.map(async key => {
                    try {
                        await caches.delete(key);
                    } catch (err) {
                        console.warn(`Error borrando cache ${key}:`, err);
                    }
                }));
                results.caches = true;
            }
        } catch (error) {
            console.warn("Error limpiando caches:", error);
        }

        // 5. Clear IndexedDB
//        try {
//            if (window.indexedDB) {
//                if (indexedDB.databases) {
//                    const databases = await indexedDB.databases();
//                    await Promise.all(databases.map(async db => {
//                        try {
//                            await new Promise((resolve, reject) => {
//                                const req = indexedDB.deleteDatabase(db.name);
//                                req.onsuccess = () => resolve();
//                                req.onerror = () => reject(req.error);
//                                req.onblocked = () => {
//                                    resolve();
//                                };
//                            });
//                        } catch (err) {
//                            console.warn(`Error borrando IndexedDB ${db.name}:`, err);
//                        }
//                    }));
//                    results.indexedDB = true;
//                } else {
//                    results.indexedDB = true;
//                }
//            }
//        } catch (error) {
//            console.warn("Error limpiando IndexedDB:", error);
//        }

        // 6. Clear WebSQL (legacy)
        try {
            if (window.openDatabase) {
                results.webSQL = true;
            }
        } catch (error) {
            console.warn("Error con WebSQL:", error);
        }

        // 7. Unregister service workers
        try {
            if ('serviceWorker' in navigator) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                await Promise.all(registrations.map(async reg => {
                    try {
                        await reg.unregister();
                    } catch (err) {
                        console.warn("Error desregistrando service worker:", err);
                    }
                }));
                results.serviceWorkers = true;
            }
        } catch (error) {
            console.warn("Error desregistrando service workers:", error);
        }

        // 8. Verificar limpieza
        const verification = {
            localStorage: localStorage.length === 0,
            sessionStorage: sessionStorage.length === 0,
            cookies: document.cookie === "",
            remainingCaches: 'caches' in window ? (await caches.keys()).length : 0
        };

        // Determinar si la limpieza fue exitosa
        const allCleared = Object.values(results).every(result => result === true);
        const verificationPassed = verification.localStorage &&
                                  verification.sessionStorage &&
                                  verification.cookies &&
                                  verification.remainingCaches === 0;

        const have_connection = await this.checkConnection()

        if (have_connection){
            window.location.href = '/web/session/logout?redirect=/web/login';
        }


//        return {
//            success: allCleared && verificationPassed,
//            results,
//            verification
//        };
    },


    async checkConnection() {
        try {
            const result = await this.orm.call("pos.session", "ping_server", [], {});
            console.log("Conectado con Odoo:", result);
            return true;
        } catch (e) {
            console.warn("Sin conexión a Odoo:", e);
            return false;
        }
    }



})