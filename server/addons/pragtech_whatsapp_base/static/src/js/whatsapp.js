/** @odoo-module **/

import {
    Component,
    useState,
    onWillStart,
    onMounted,
    onWillUnmount,
    useEffect,
} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService, useBus} from "@web/core/utils/hooks";
import {debounce} from "@web/core/utils/timing";

export class WhatsappChat extends Component {
    static template = "pragtech_whatsapp_base.whatsappChatTemplate";

    setup() {
        super.setup();
        this.abortController = new AbortController();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.isPolling = false;
        this.state = useState({
            offset_conversations: 0,
            page_size_conversations: 20,
            has_more_conversations: true,
            is_loading_conversations: false,
            conversations: [],
            isLoadingOldMessages: false,
            messages: [],
            chatStates: {},
            selectedChatId: null,
            newMessage: "",
            offset: 0,
            selectedFile: null,
            selectedFileUrl: null,
            currentDate: new Date().toISOString().split("T")[0],
            isRecording: false,
            recordingTime: 0,
            audioBlob: null,
            audioUrl: null,
            lastMessageTime: null,
            pollingInterval: null,
            isLoadingMessages: false,
            isLoadingConversations: false,
            isSendingMessage: false,
            selectedChatName: null,
            searchQuery: "",
            error: {
                type: null,
                message: null,
                timestamp: null,
            },
            retryCount: 0,
            maxRetries: 3,
            notificationSound: new Audio(
                "/pragtech_whatsapp_base/static/src/audio/notification.mp3"
            ),
            notificationPermission: false,
            unreadCount: 0,
            hasFocus: true,
            orders: [],
            showOrders: false,
            ordersByChat: {},
            showEditName: false,
            tempCustomName: "",
        });

        this.busService = this.env.services.bus_service;
        this.channel = "whatsapp_notifications";
        this.busService.addChannel(this.channel);
        this.busService.addEventListener("notification", this.onBusMessage.bind(this));
        this.state.showQuick = false;
        this.state.quickQuery = "";
        this.state.quickSuggestions = [];
        this.state.quickIndex = 0;

        this.fetchQuickDebounced = debounce(this.fetchQuickSuggestions.bind(this), 120);


        this.configureNotificationAudio();
        this._unlockOnce = () => this.ensureAudioUnlocked();

        this.fetchDebounced = debounce(this.startConversationsPolling.bind(this), 200);

        // Check notification permission
        if ("Notification" in window) {
            Notification.requestPermission().then((permission) => {
                this.state.notificationPermission = permission === "granted";
            });
        }

        // Handle window focus
        this.handleFocus = () => {
            this.state.hasFocus = true;
            this.state.unreadCount = 0;
            document.title = "WhatsApp Chat";
        };

        this.handleBlur = () => {
            this.state.hasFocus = false;
        };

        this.fetchDebounced = debounce(this.startConversationsPolling.bind(this), 200);

        this.searchEffect = useEffect(() => {
            const q = (this.state.searchQuery || "").trim();

            Object.assign(this.state, {
                offset_conversations: 0,
                has_more_conversations: true,
                conversations: [],
            });

            this.fetchDebounced();
        }, () => [this.state.searchQuery]);

        window.addEventListener("focus", this.handleFocus);
        window.addEventListener("blur", this.handleBlur);

        onWillStart(async () => {

            this.fetchDebounced();
        });

        onMounted(() => {
            this.setupScrollListener();
            this.scrollToBottom();
            this.setupScrollListenerConversations();
            this.startConversationsPolling();

            window.addEventListener("pointerdown", this._unlockOnce, {once: true});
            window.addEventListener("keydown", this._unlockOnce, {once: true});
        });

        onWillUnmount(() => {
            this.abortController.abort();
            this.stopPolling();
            this.stopConversationsPolling();
            this.state.messages = [];
            this.state.selectedChatId = null;
            window.removeEventListener("focus", this.handleFocus);
            window.removeEventListener("blur", this.handleBlur);
            if (this.state.selectedFileUrl) {
                URL.revokeObjectURL(this.state.selectedFileUrl);
            }
            if (this.state.audioUrl) {
                URL.revokeObjectURL(this.state.audioUrl);
            }
        });
    }

    // Obtiene la palabra "trigger" tipo /algo bajo el cursor
    _getSlashToken(text, caretPos) {
        // Busca el último espacio/salto línea antes del caret
        const left = text.slice(0, caretPos);
        const m = left.match(/(?:^|\s)(\/[^\s/]*)$/);
        if (!m) return null;
        const token = m[1]; // p.ej. "/sal"
        const start = left.lastIndexOf(token);
        return { token, start, end: caretPos };
    }

    async fetchQuickSuggestions() {
        const q = this.state.quickQuery || "";
        try {
            const res = await this.orm.call(
                "whatsapp.quick_reply",
                "search_suggestions",
                [q, 8]
            );
            this.state.quickSuggestions = res || [];
            // Si no hay resultados, ocultar
            this.state.showQuick = (this.state.quickSuggestions.length > 0);
            this.state.quickIndex = 0;
        } catch (e) {
            this.state.quickSuggestions = [];
            this.state.showQuick = false;
        }
    }

    // Inserta la respuesta rápida reemplazando "/xxx" por el mensaje
    _applyQuickReply(item) {
        const ta = this._getTextarea();
        const value = this.state.newMessage || "";
        const caret = ta ? ta.selectionStart : value.length;
        const hit = this._getSlashToken(value, caret);
        if (!hit) return;

        const before = value.slice(0, hit.start);
        const after = value.slice(hit.end);
        // Inserta el mensaje (respetar salto de línea si había texto luego)
        const insert = item.message || "";
        const newVal = before + insert + after;

        this.state.newMessage = newVal;
        this.state.showQuick = false;
        this.state.quickSuggestions = [];
        this.state.quickQuery = "";
        this.state.quickIndex = 0;

        // Recolocar el caret al final del bloque insertado
        this.render();
        requestAnimationFrame(() => {
            const el = this._getTextarea();
            if (el) {
                const pos = (before + insert).length;
                el.focus();
                el.setSelectionRange(pos, pos);
            }
        });
    }

    _getTextarea() {
        // textarea del input de chat (por tu XML: el único <textarea/> del input)
        return document.querySelector(".chat-input textarea");
    }


    async onBusMessage({detail: notifications}) {
        for (const notification of notifications) {
            if (notification.type === 'notification') {
                await this._handleWhatsAppNotification(notification.payload);
            }
        }
    }

    async togglePinChat(chatId) {
        try {
            const result = await this.orm.call(
                "whatsapp.chatbot",
                "toggle_pin",
                [chatId]
            );

            if (result && result.chatId) {
                // Forzar recarga completa de conversaciones para que traiga los pinned actualizados
                this.state.offset_conversations = 0;
                this.state.has_more_conversations = true;
                this.state.conversations = [];
                if (this.conversationsMap) {
                    this.conversationsMap.clear();
                }

                await this.startConversationsPolling();

                this.notification.add(
                    result.pinned ? "Chat fijado arriba" : "Chat desfijado",
                    {title: "Listo", type: "success"}
                );
            }
        } catch (error) {
            console.error("Error al fijar/desfijar chat:", error);
            this.notification.add("Error al cambiar fijado", {type: "danger"});
        }
    }

    async _handleWhatsAppNotification(messageData) {
        if (!this.__owl__ || this.__owl__.status === 'destroyed') {
            console.log('Component destroyed, stopping notification handling');
            return;
        }

        try {
            const conversationData = await this.orm.call(
                "whatsapp.messages",
                "get_conversation_by_message_id",
                [messageData.id]
            );

            if (!this.__owl__ || this.__owl__.status === 'destroyed') {
                return;
            }

            if (conversationData && conversationData.length > 0) {
                const updatedConversation = conversationData[0];
                await this._updateSingleConversation(updatedConversation);
            }

        } catch (error) {
            console.error("Error processing notification:", error);
        }
    }

    async _updateSingleConversation(updatedConv) {
        if (!updatedConv?.chatId) return;

        // Inicializar Map si no existe
        if (!this.conversationsMap) {
            this.conversationsMap = new Map();
            this.state.conversations.forEach(conv => {
                if (conv.chatId) {
                    this.conversationsMap.set(conv.chatId, conv);
                }
            });
        }

        let existingConv = this.conversationsMap.get(updatedConv.chatId);

        if (existingConv) {
            // ACTUALIZAR solo los campos que cambian con nuevo mensaje
            // ¡NUNCA sobrescribir pinned ni pin_sequence!
            Object.assign(existingConv, {
                lastMessageTime: updatedConv.lastMessageTime || existingConv.lastMessageTime,
                message_body: updatedConv.message_body || existingConv.message_body,
                unreadCount: updatedConv.unreadCount ?? existingConv.unreadCount,
                chatName: updatedConv.chatName || existingConv.chatName,
                senderName: updatedConv.senderName || existingConv.senderName,
                displayName: updatedConv.displayName || existingConv.displayName,
                // pinned y pin_sequence se mantienen intactos
            });
        } else {
            // Es un chat completamente nuevo → agregar tal cual
            this.conversationsMap.set(updatedConv.chatId, {
                ...updatedConv,
                pinned: updatedConv.pinned || false,
                pin_sequence: updatedConv.pin_sequence || 10,
            });
            existingConv = updatedConv;
        }

        // Actualizar el estado del chat desde el backend
        try {
            const stateData = await this.orm.call(
                "whatsapp.chatbot",
                "get_chat_state",
                [updatedConv.chatId]
            );
            if (stateData?.state) {
                this.state.chatStates[updatedConv.chatId] = stateData.state;
            }
        } catch (e) {
            console.error("Error actualizando estado del chat:", e);
        }

        // Reordenar toda la lista con el comparador mejorado
        this.state.conversations = Array.from(this.conversationsMap.values())
            .sort(this.compareConversations);

        // Opcional: notificación sonora solo si hay mensajes nuevos no leídos
        if (existingConv.unreadCount > 0 && existingConv.chatId !== this.state.selectedChatId) {
            this.playNotificationSound();
        }

        // Si el chat actualizado es el abierto → recargar mensajes
        if (this.state.selectedChatId === updatedConv.chatId) {
            await this.startPolling();
        }
    }

    compareConversations(a, b) {
        // 1. CHATS FIJADOS SIEMPRE ARRIBA
        if (a.pinned && !b.pinned) return -1;
        if (!a.pinned && b.pinned) return 1;

        // 2. Entre chats fijados: orden por pin_sequence (el que se fija primero queda más arriba)
        if (a.pinned && b.pinned) {
            const seqA = a.pin_sequence ?? 10;
            const seqB = b.pin_sequence ?? 10;
            if (seqA !== seqB) return seqA - seqB;
        }

        // 3. No fijados: por última actividad (más reciente arriba)
        const at = a.lastMessageTime ? new Date(a.lastMessageTime).getTime() : 0;
        const bt = b.lastMessageTime ? new Date(b.lastMessageTime).getTime() : 0;
        if (at !== bt) return bt - at;

        // 4. Desempate final por chatId (estable)
        return String(a.chatId).localeCompare(String(b.chatId));
    }

    // Abre el modal para editar el nombre del contacto actual
    openEditContactName() {
        if (!this.state.selectedChatId) return;
        // Toma el nombre que ves (displayName o fallback)
        const conv = this.state.conversations.find(c => c.chatId === this.state.selectedChatId);
        const current = (conv?.displayName || conv?.senderName || conv?.chatName || conv?.chatId || "").trim();
        this.state.tempCustomName = current;
        this.state.showEditName = true;
    }

    // Cierra el modal sin guardar
    cancelEditContactName() {
        this.state.showEditName = false;
        this.state.tempCustomName = "";
    }

    // Guarda en servidor y actualiza la UI local
    async saveContactName() {
        const chatId = this.state.selectedChatId;
        const newName = (this.state.tempCustomName || "").trim();
        if (!chatId) return;

        try {
            // Llama a tu modelo (crea el método en backend, ver más abajo)
            // Debe devolver { chatId, displayName } con el nombre resultante
            const result = await this.orm.call(
                "whatsapp.chatbot",
                "set_custom_name",
                [chatId, newName]   // args posicionales
            );

            // Actualiza conversación activa y la lista completa
            const conv = this.state.conversations.find(c => c.chatId === chatId);
            if (conv) {
                conv.displayName = result?.displayName ?? newName; // lo que confirme el server
            }

            // Si el header muestra el nombre seleccionado, refresca
            if (this.state.selectedChatId === chatId) {
                this.state.selectedChatName = result?.displayName ?? newName;
            }

            // Reordena manteniendo la lógica existente
            this.state.conversations = [...this.state.conversations].sort(this.compareConversations);

            this.notification.add("Contacto actualizado", {title: "Éxito", type: "success"});
            this.cancelEditContactName();
        } catch (e) {
            console.error("Error guardando nombre personalizado:", e);
            this.notification.add("No se pudo guardar el nombre", {title: "Error", type: "danger"});
        }
    }

    onKeypress(ev) {
        // Navegación del popup de respuestas rápidas
        if (this.state.showQuick && this.state.quickSuggestions.length) {
            if (["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(ev.key)) {
                ev.preventDefault();
            }
            if (ev.key === "ArrowDown") {
                this.state.quickIndex = (this.state.quickIndex + 1) % this.state.quickSuggestions.length;
                return;
            }
            if (ev.key === "ArrowUp") {
                this.state.quickIndex = (this.state.quickIndex - 1 + this.state.quickSuggestions.length) % this.state.quickSuggestions.length;
                return;
            }
            if (ev.key === "Escape") {
                this.state.showQuick = false;
                return;
            }
            if (ev.key === "Enter" || ev.key === "Tab") {
                const item = this.state.quickSuggestions[this.state.quickIndex];
                if (item) this._applyQuickReply(item);
                return;
            }
        }

        // Envío normal con Enter (mantienes tu lógica)
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }


    // Métodos auxiliares
    shouldLoadMessages() {
        return this.state.selectedChatId &&
            this.state.chatStates[this.state.selectedChatId] !== 'manejar_salida';
    }

    renderPlainMarkdown(text) {
        if (!text) return "";
        return text.replace(/\*\*(.+?)\*\*/g, (_, p1) => p1.toUpperCase());
    }

    hasPendingOrders(chatId) {
        const orders = this.state.ordersByChat && this.state.ordersByChat[chatId]
            ? this.state.ordersByChat[chatId]
            : [];
        const draftOrders = orders.filter(order => order.state === 'draft');
        return draftOrders.length > 0;
    }

    copyChatNumber() {
        const chatId = this.state.selectedChatId;
        if (!chatId) return;

        const tempInput = document.createElement("input");
        tempInput.style.position = "absolute";
        tempInput.style.left = "-9999px";
        tempInput.value = chatId.slice(3);

        document.body.appendChild(tempInput);
        tempInput.select();
        document.execCommand("copy");
        document.body.removeChild(tempInput);

        this.notification.add("Número copiado al portapapeles", {
            title: "Copiado",
            type: "success",
        });
    }

    getOrderColor(chatId) {
        const orders = this.state.ordersByChat && this.state.ordersByChat[chatId]
            ? this.state.ordersByChat[chatId]
            : [];
        const draftOrders = orders.filter(order => order.state === 'draft');
        return draftOrders.length ? draftOrders[0].color_pago : '#6c757d';
    }

    hasCotizarReceta(id) {
        const state = this.state.chatStates[id];
        // No mostrar indicador para estados cerrados/vacíos
        const closedStates = ['cerrar_chat', 'salir', 'salir_conversacion', ''];
        if (!state || closedStates.includes(state)) {
            return false;
        }
        return true;
    }

    get_color_state(id) {
        const state = this.state.chatStates[id];

        // Estados cerrados/inactivos - sin color (transparente)
        const closedStates = ['cerrar_chat', 'salir', 'salir_conversacion', ''];
        if (!state || closedStates.includes(state)) {
            return 'transparent';
        }

        switch (state) {
            case 'cotizar-receta':
                return '#dc3545';
            case 'confirmar_pago':
                return '#28a745';
            default:
                // Para otros estados activos, mostrar un color neutro
                return '#6c757d';
        }
    }


    async startConversationsPolling() {
        if (!this.state.has_more_conversations || this.state.is_loading_conversations) return;

        if (this.abortController.signal.aborted) {
            return;
        }

        Object.assign(this.state, {
            is_loading_conversations: true
        });

        try {
            const q = (this.state.searchQuery || '').trim();
            const method = q ? "search_conversations" : "get_conversations";
            const args = q
                ? [q, this.state.offset_conversations, this.state.page_size_conversations]
                : [this.state.offset_conversations, this.state.page_size_conversations];

            const newConversations = await this.orm.call(
                "whatsapp.messages",
                method,
                args
            );

            if (this.abortController.signal.aborted) return;

            const validConversations = newConversations.filter(conv =>
                conv?.chatId && conv?.lastMessageTime
            );

            if (validConversations.length === 0) {
                Object.assign(this.state, {
                    has_more_conversations: false
                });
                return;
            }

            // Procesar estados de chat
            for (const conversation of validConversations) {
                if (this.abortController.signal.aborted) return;

                try {
                    const stateData = await this.orm.call(
                        "whatsapp.chatbot",
                        "get_chat_state",
                        [conversation.chatId]
                    );

                    if (this.abortController.signal.aborted) return;

                    this.state.chatStates[conversation.chatId] = stateData.state;

                } catch (stateError) {
                    if (stateError.name === 'AbortError') {
                        return;
                    }
                }
            }

            if (this.abortController.signal.aborted) return;

            this.insertConversationsSorted(validConversations);

            Object.assign(this.state, {
                offset_conversations: this.state.offset_conversations + validConversations.length,
                has_more_conversations: validConversations.length >= this.state.page_size_conversations
            });

            if (this.state.selectedChatId &&
                this.state.chatStates[this.state.selectedChatId] !== 'manejar_salida' &&
                !this.abortController.signal.aborted) {
                await this.startPolling();
            }

        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
        } finally {
            if (!this.abortController.signal.aborted) {
                Object.assign(this.state, {
                    is_loading_conversations: false
                });
            }
        }
    }

    insertConversationsSorted(newConversations) {
        // Normalizar las nuevas (asegurar pinned y pin_sequence)
        const normalizedNew = newConversations.map(conv => ({
            ...conv,
            pinned: conv.pinned || false,
            pin_sequence: conv.pin_sequence ?? 10,
        }));

        // Crear o usar el Map
        if (!this.conversationsMap) {
            this.conversationsMap = new Map();
            this.state.conversations.forEach(conv => {
                if (conv.chatId) {
                    this.conversationsMap.set(conv.chatId, {
                        ...conv,
                        pinned: conv.pinned || false,
                        pin_sequence: conv.pin_sequence ?? 10,
                    });
                }
            });
        }

        // Insertar/actualizar las nuevas (sin perder pinned de las viejas)
        normalizedNew.forEach(conv => {
            const existing = this.conversationsMap.get(conv.chatId);
            if (existing) {
                // Conservar pinned y pin_sequence del existente
                this.conversationsMap.set(conv.chatId, {
                    ...conv,
                    pinned: existing.pinned,
                    pin_sequence: existing.pin_sequence,
                });
            } else {
                this.conversationsMap.set(conv.chatId, conv);
            }
        });

        // Reordenar todo
        this.state.conversations = Array.from(this.conversationsMap.values())
            .sort(this.compareConversations);
    }


    stopConversationsPolling() {
        if (this.conversationsPollingInterval) {
            clearInterval(this.conversationsPollingInterval);
            this.conversationsPollingInterval = null;
        }
    }

    async startPolling() {
        if (!this.state.selectedChatId) return;
        if (this.isPolling) return; // Prevenir ejecuciones concurrentes
        this.isPolling = true;

        const currentState = this.state.chatStates[this.state.selectedChatId];
        if (currentState === 'manejar_salida') {
            return;
        }

        try {
            const lastMessage = this.state.messages[this.state.messages.length - 1];
            const lastMessageTime = lastMessage?.time || null;

            const response = await this.orm.call(
                "whatsapp.messages",
                "get_messages",
                [this.state.selectedChatId, lastMessageTime]
            );

            if (response?.messages?.length > 0) {
                const existingIds = new Set(this.state.messages.map(msg => msg.id));
                const newMessages = response.messages.filter(msg =>
                    !existingIds.has(msg.id)
                );

                if (newMessages.length > 0) {
                    this.state.messages.push(...newMessages);
                    this.scrollToBottom();

                    if (newMessages.some(m => !m.fromMe)) {
                        this.playNotificationSound();
                    }
                }
            }
        } catch (error) {
            console.error("Error en polling:", error);
        } finally {
            this.isPolling = false;
        }
    }

    stopPolling() {
        if (this.state.pollingInterval) {
            clearInterval(this.state.pollingInterval);
            this.state.pollingInterval = null;
        }
    }

    // get filteredConversations() {
    //     const conversations = this.state.conversations || [];
    //     if (!this.state.searchQuery) {
    //         return conversations;
    //     }
    //     const query = this.state.searchQuery.toLowerCase();
    //     return conversations.filter(chat =>
    //         chat.chatId.toLowerCase().includes(query) ||
    //         (chat.message_body && chat.message_body.toLowerCase().includes(query))
    //     );
    // }

    get filteredConversations() {
        const list = this.state.conversations || [];
        const qRaw = (this.state.searchQuery || '').trim();
        if (!qRaw) return list;

        // Normalizador
        const norm = (s) =>
            (s ?? '')
                .toString()
                .normalize('NFD')
                .replace(/[\u0300-\u036f]/g, '')
                .toLowerCase();

        // Solo dígitos
        const normPhone = (s) => (s ?? '').toString().replace(/[^\d]/g, '');

        const q = norm(qRaw);
        const qDigits = normPhone(qRaw);
        const terms = q.split(/\s+/).filter(Boolean);

        return list.filter((c) => {
            const fields = [
                norm(c.displayName),
                norm(c.senderName),
                norm(c.chatName),
                norm(c.chatId),
                norm(c.message_body),
            ].join(' ');

            const phone = normPhone(c.chatId);

            const textMatch = terms.every((t) => fields.includes(t));
            const phoneMatch = qDigits && phone.includes(qDigits);

            return textMatch || phoneMatch;
        });
        return this.state.conversations || [];
    }


    get filteredMessages() {
        return this.state.messages;
    }

    async selectChat(chatId) {
        if (this.state.selectedChatId === chatId) return;

        // Reset básicos
        this.state.error = {type: null, message: null, timestamp: null};
        this.state.selectedChatId = chatId;
        this.state.selectedChatName = null;
        this.state.offset = 0;

        try {
            this.state.isLoadingMessages = true;

            // Estado del chat (para manejar 'manejar_salida')
            const stateData = await this.orm.call("whatsapp.chatbot", "get_chat_state", [chatId]);
            this.state.chatStates[chatId] = stateData.state;

            // Cargar todos los mensajes primero
            await this.loadMessages(chatId);

            // Conversación en la lista (trae displayName si existe)
            const conv = this.state.conversations.find(c => c.chatId === chatId);
            // Primer mensaje recibido (para fallback de nombre)
            const receivedMessage = this.state.messages.find(msg => !msg.fromMe);

            // Prioridad de nombre: custom (displayName) > senderName de conv > chatName > senderName recibido > chatId
            this.state.selectedChatName =
                conv?.displayName ||
                conv?.senderName ||
                conv?.chatName ||
                receivedMessage?.senderName ||
                chatId;

            // Marcar como leído solo si NO está en 'manejar_salida'
            if (stateData.state !== 'manejar_salida') {
                await this.markMessagesAsRead(chatId);
                // Opcional: limpia badge localmente para UX inmediata
                if (conv) conv.unreadCount = 0;
            }

            this._scrollToBottom(true);
        } catch (error) {
            console.error("Error al seleccionar el chat:", error);
            this.state.error = {
                type: "api",
                message: "Error al cargar mensajes. Por favor, intente nuevamente.",
                timestamp: new Date().toISOString(),
            };
        } finally {
            this.state.isLoadingMessages = false;
            // Inicia polling solo si no estamos en 'manejar_salida'
            if (this.state.chatStates[chatId] !== 'manejar_salida') {
                await this.startPolling();
            }
        }
    }


    async loadMessages(chatId, offset = 0, limit = 50) {
        if (this.state.isLoadingMessages && offset > 0) return;

        try {
            this.state.isLoadingMessages = true;

            // Cambiar la llamada para obtener todos los mensajes sin filtrar por tiempo
            const response = await this.orm.call(
                "whatsapp.messages",
                "get_messages",
                [chatId]
            );

            if (response?.messages?.length > 0) {
                // Reemplazar completamente los mensajes en la carga inicial
                if (offset === 0) {
                    this.state.messages = response.messages;
                } else {
                    // Para cargas adicionales (scroll up)
                    this.state.messages = [...response.messages, ...this.state.messages];
                }
                this.state.offset = response.messages.length;

                // Forzar scroll al final solo en carga inicial
                if (offset === 0) {
                    this._scrollToBottom(true);
                }
            }
        } catch (error) {
            console.error("Error loading messages:", error);
        } finally {
            this.state.isLoadingMessages = false;
        }
    }

    async loadOlderMessages() {
        if (this.state.isLoadingOldMessages || !this.shouldLoadMessages()) return;

        try {
            this.state.isLoadingOldMessages = true;
            const container = document.querySelector(".messages-scroll-container");
            const prevHeight = container?.scrollHeight || 0;

            const newMessages = await this.orm.searchRead(
                "whatsapp.messages",
                [["chatId", "=", this.state.selectedChatId]],
                [],
                {
                    order: "id DESC",
                    limit: 20,
                    offset: this.state.offset,
                }
            );

            if (newMessages.length > 0) {
                const orderedMessages = newMessages.reverse();
                this.state.messages = [...orderedMessages, ...this.state.messages];
                this.state.offset += newMessages.length;

                if (container) {
//                    requestAnimationFrame(() => {
//                        const newHeight = container.scrollHeight;
//                        const heightDiff = newHeight - prevHeight;
//                        container.scrollTop = heightDiff;
//                    });
                }
            }
        } catch (error) {
            console.error("Error cargando mensajes:", error);
            this.state.error = {
                type: "load",
                message: "Error cargando mensajes antiguos",
                timestamp: new Date().toISOString(),
            };
        } finally {
            this.state.isLoadingOldMessages = false;
        }
    }

    async markMessagesAsRead(chatId) {
        await this.orm.call("whatsapp.messages", "mark_messages_as_read", [], {
            chatId,
        });
    }

    // Métodos de envío de mensajes
    async sendMessage() {
        if (!this.state.newMessage && !this.state.selectedFile && !this.state.audioBlob) return;

        try {
            this.state.isSendingMessage = true;
            this.stopPolling();
            this.state.error = {type: null, message: null, timestamp: null};

            let messageData = {
                chatId: this.state.selectedChatId,
                message_body: this.state.newMessage || "",
                type: "text",
            };

            if (this.state.audioBlob) {
                const audioBase64 = await this.fileToBase64(this.state.audioBlob);
                messageData = {
                    chatId: this.state.selectedChatId,
                    message_body: "",
                    type: "audio",
                    attachment_data: audioBase64,
                    filename: "audio.mp3",
                };
            } else if (this.state.selectedFile) {
                const fileBase64 = await this.fileToBase64(this.state.selectedFile);
                const fileType = this.state.selectedFile.type.startsWith("image/") ? "image" : "document";
                messageData = {
                    chatId: this.state.selectedChatId,
                    message_body: this.state.selectedFile.name || "",
                    type: fileType,
                    attachment_data: fileBase64,
                    filename: this.state.selectedFile.name,
                    mime_type: this.state.selectedFile.type,
                };
            }

            const result = await this.orm.call(
                "whatsapp.messages",
                "send_whatsapp_message",
                [],
                messageData
            );

            // ✅ Actualizar conversación activa y reordenar la lista
            const conv = this.state.conversations.find(c => c.chatId === this.state.selectedChatId);
            if (conv) {
                conv.lastMessageTime = new Date().toISOString();
                // mensaje “preview”
                if (messageData.type === "text") {
                    conv.message_body = messageData.message_body || "";
                } else if (messageData.type === "image") {
                    conv.message_body = "📷 Imagen";
                } else if (messageData.type === "audio") {
                    conv.message_body = "🎧 Audio";
                } else if (messageData.type === "document") {
                    conv.message_body = "📎 Documento";
                }
                // Si quieres: conv.unreadCount = 0;
            }
            this.state.conversations = [...this.state.conversations].sort(this.compareConversations);

        } catch (error) {
            console.error("Error al enviar el mensaje:", error);
            this.state.error = {
                type: error.message?.includes("procesar") ? "upload" : "api",
                message: error.message || "Error al enviar el mensaje",
                timestamp: new Date().toISOString(),
            };
            this.notification.add(this.state.error.message, {
                title: "Error",
                type: "danger",
            });
        } finally {
            this.state.isSendingMessage = false;
            this.state.newMessage = "";
            this.clearSelectedFile();
            this.cancelAudio();
            this.render();
        }
    }


    // Métodos de UI y utilidades
    formatDate(dateString) {
        const date = new Date(dateString);
        return date
            .toLocaleString("es-ES", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            })
            .replace(".", "");
    }

    formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${minutes}:${secs < 10 ? "0" : ""}${secs}`;
    }

    setupScrollListener() {
        const container = document.querySelector(".messages-scroll-container");
        if (container) {
            container.addEventListener("scroll", () => {
                if (this.scrollTimeout) {
                    clearTimeout(this.scrollTimeout);
                }

                this.scrollTimeout = setTimeout(() => {
                    if (container.scrollTop === 0 && !this.state.isLoadingOldMessages) {
                        this.loadOlderMessages();
                    }
                }, 150);
            });
        }
    }

    scrollToBottom(force = false) {
        const container = document.querySelector(".messages-scroll-container");
        if (container) {
            // Calcular si el usuario está cerca del final (100px de margen)
            const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;

            // Solo hacer scroll si está cerca del final o es forzado
            if (force || isNearBottom) {
                // Usar setTimeout para asegurar que el DOM se haya actualizado
                setTimeout(() => {
                    container.scrollTo({
                        top: container.scrollHeight,
                        behavior: "smooth"
                    });
                }, 50);
            }
        }
    }

    _scrollToBottom() {
        this.scrollToBottom(true);
    }

    clearSelectedFile() {
        if (this.state.selectedFileUrl) {
            URL.revokeObjectURL(this.state.selectedFileUrl);
        }
        this.state.selectedFile = null;
        this.state.selectedFileUrl = null;
    }

    // --- Audio: configuración y desbloqueo (autoplay-safe) ---
    configureNotificationAudio() {
        const a = this.state?.notificationSound;
        if (!a) return;
        a.preload = "auto";
        try {
            a.setAttribute("playsinline", "");
            a.setAttribute("webkit-playsinline", "");
        } catch {
        }
        a.volume = 1.0; // dejamos volumen alto para cuando suene de verdad
    }

    async ensureAudioUnlocked() {
        try {
            // 1) Reanudar WebAudio si está suspendido (Safari/Chrome móviles)
            const AC = window.AudioContext || window.webkitAudioContext;
            if (AC) {
                if (!this._audioCtx) this._audioCtx = new AC();
                if (this._audioCtx.state === "suspended") {
                    await this._audioCtx.resume();
                }
            }

            // 2) “Desbloquear” HTMLAudio con una reproducción silenciada
            const a = this.state?.notificationSound;
            if (a) {
                a.muted = true;
                a.currentTime = 0;
                try {
                    await a.play();
                } catch {
                }
                a.pause();
                a.muted = false;
            }
        } finally {
            // Quitamos los listeners de desbloqueo
            window.removeEventListener("pointerdown", this._unlockOnce);
            window.removeEventListener("keydown", this._unlockOnce);
        }
    }


    async fileToBase64(file) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result.split(",")[1]);
        });
    }

    // --- Notificaciones: sonido al recibir mensajes (no altera lógica existente) ---
    playNotificationSound() {
        // Antirrebote: no más de 1 sonido / 1.5s
        if (!this._lastNotifyAt) this._lastNotifyAt = 0;
        const now = performance.now();
        if (now - this._lastNotifyAt < 1500) return;
        this._lastNotifyAt = now;

        try {
            const audio = this.state?.notificationSound;
            if (audio) {
                // Preparar y reproducir con volumen alto
                audio.pause();
                audio.currentTime = 0;     // empezar desde el inicio
                audio.volume = 1.0;        // fuerte
                // Intentar reproducir; si el navegador lo bloquea, usar fallback
                audio.play().catch(() => this._fallbackRinRin());
            } else {
                this._fallbackRinRin();
            }
        } catch {
            this._fallbackRinRin();
        }
    }


    _fallbackRinRin() {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        if (!this._audioCtx) this._audioCtx = new AC();

        const ctx = this._audioCtx;
        const now = ctx.currentTime;

        // Cadena limpia: gain maestro + highpass para quitar DC/ruido bajo
        const master = ctx.createGain();
        master.gain.setValueAtTime(0.85, now);

        const hp = ctx.createBiquadFilter();
        hp.type = "highpass";
        hp.frequency.setValueAtTime(120, now);
        hp.Q.setValueAtTime(0.7, now);

        master.connect(ctx.destination);
        hp.connect(master);

        // Config del "rin–rin": dos toques casi iguales
        const f1 = 880;   // A5
        const f2 = 840;   // casi A5 (ligeramente más bajo)
        const ringDur = 0.72; // duración de cada "rin"
        const gap = 0.28;     // pausa entre ellos

        const mkRing = (t0, freq) => {
            const osc = ctx.createOscillator();
            osc.type = "sine";
            osc.frequency.setValueAtTime(freq, t0);

            const g = ctx.createGain();

            // ADSR suave para que se sienta “liso/armonioso/delicado”
            const A = 0.02, D = 0.08, S = 0.55, R = 0.18;
            g.gain.setValueAtTime(0.0001, t0);
            g.gain.exponentialRampToValueAtTime(0.95, t0 + A);
            g.gain.linearRampToValueAtTime(S, t0 + A + D);
            g.gain.setValueAtTime(S, t0 + ringDur - R);
            g.gain.exponentialRampToValueAtTime(0.0001, t0 + ringDur);

            // Tremolo muy sutil para “vida”, sin sonar a radio
            const lfo = ctx.createOscillator();
            const lfoGain = ctx.createGain();
            lfo.frequency.setValueAtTime(5.8, t0);
            lfoGain.gain.setValueAtTime(0.12, t0); // modulación pequeña
            lfo.connect(lfoGain).connect(g.gain);

            osc.connect(g).connect(hp);

            lfo.start(t0);
            lfo.stop(t0 + ringDur);
            osc.start(t0);
            osc.stop(t0 + ringDur);
        };

        mkRing(now, f1);                   // primer “rin”
        mkRing(now + ringDur + gap, f2);   // segundo “rin”
    }


    // Métodos de archivos y grabación
    async openFileSelector() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "*/*";
        input.onchange = async (event) => {
            const file = event.target.files[0];
            const maxSize = 2 * 1024 * 1024 * 1024;
            if (file.size > maxSize) {
                alert("El archivo es demasiado grande. Máximo permitido: 2GB.");
                return;
            }
            this.state.selectedFile = file;
        };
        input.click();
    }

    async openImageSelector() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "image/*";
        input.onchange = async (event) => {
            const file = event.target.files[0];
            const maxSize = 16 * 1024 * 1024;
            if (file.size > maxSize) {
                alert("La imagen es demasiado grande. Máximo permitido: 16MB.");
                return;
            }
            this.state.selectedFile = file;
            if (this.state.selectedFileUrl) {
                URL.revokeObjectURL(this.state.selectedFileUrl);
            }
            this.state.selectedFileUrl = URL.createObjectURL(file);
        };
        input.click();
    }

    async openAudioSelector() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "audio/*";
        input.onchange = (event) => {
            const file = event.target.files[0];
            const maxSize = 16 * 1024 * 1024;
            if (file.size > maxSize) {
                alert("El audio es demasiado grande. Máximo permitido: 16MB.");
                return;
            }
            this.state.selectedFile = file;
        };
        input.click();
    }

    async startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert("Tu navegador no soporta grabación de audio.");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            this.mediaRecorden = new MediaRecorder(stream);
            const chunks = [];

            this.mediaRecorden.ondataavailable = (e) => chunks.push(e.data);
            this.mediaRecorden.onstop = async () => {
                const rawBlob = new Blob(chunks, {type: "audio/webm"});
                const audioBlob = await this.convertToMp3(rawBlob);
                this.state.audioBlob = audioBlob;
                this.state.audioUrl = URL.createObjectURL(audioBlob);
                this.state.isRecording = false;
                if (this.timerInterval) clearInterval(this.timerInterval);
                stream.getTracks().forEach((track) => track.stop());
            };

            this.mediaRecorden.start();
            this.state.isRecording = true;
            this.state.recordingTime = 0;
            this.timerInterval = setInterval(() => {
                this.state.recordingTime += 1;
            }, 1000);
        } catch (e) {
            console.error("Error al iniciar grabación:", e);
            alert("No se pudo iniciar la grabación. Verifica permisos de micrófono.");
        }
    }

    async convertToMp3(rawBlob) {
        return new Promise((resolve) => {
            const audioContext = new (window.AudioContext ||
                window.webkitAudioContext)();
            const fileReader = new FileReader();

            fileReader.onload = async () => {
                const arrayBuffer = fileReader.result;
                const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                const channelData = audioBuffer.getChannelData(0);
                const sampleRate = audioBuffer.sampleRate;

                const mp3encoder = new lamejs.Mp3Encoder(1, sampleRate, 128);
                const mp3Data = [];
                const samples = new Int16Array(channelData.length);
                for (let i = 0; i < channelData.length; i++) {
                    samples[i] = channelData[i] * 32767.5;
                }

                const blockSize = 1152;
                for (let i = 0; i < samples.length; i += blockSize) {
                    const chunk = samples.subarray(i, i + blockSize);
                    const mp3buf = mp3encoder.encodeBuffer(chunk);
                    if (mp3buf.length > 0) mp3Data.push(mp3buf);
                }

                const mp3buf = mp3encoder.flush();
                if (mp3buf.length > 0) mp3Data.push(mp3buf);

                const mp3Blob = new Blob(mp3Data, {type: "audio/mp3"});
                resolve(mp3Blob);
            };

            fileReader.readAsArrayBuffer(rawBlob);
        });
    }

    stopRecording() {
        if (this.mediaRecorden && this.state.isRecording) {
            this.mediaRecorden.stop();
            if (this.timerInterval) {
                clearInterval(this.timerInterval);
                this.timerInterval = null;
            }
        }
    }

    cancelAudio() {
        if (this.state.audioUrl) {
            URL.revokeObjectURL(this.state.audioUrl);
        }
        this.state.audioBlob = null;
        this.state.audioUrl = null;
        this.state.recordingTime = 0;
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    updateNewMessage(event) {
        this.state.newMessage = event.target.value;

        // Detectar si hay un "/xxx" bajo el cursor y pedir sugerencias
        const ta = event.target;
        const caret = ta.selectionStart;
        const hit = this._getSlashToken(this.state.newMessage, caret);

        if (hit) {
            this.state.quickQuery = hit.token; // incluye "/"
            this.state.showQuick = true;
            this.fetchQuickDebounced();
        } else {
            this.state.quickQuery = "";
            this.state.showQuick = false;
            this.state.quickSuggestions = [];
            this.state.quickIndex = 0;
        }
    }


    // Métodos de órdenes
    openOrders() {
        this.state.showOrders = true;
    }

    closeOrders() {
        this.state.showOrders = false;
    }

    setupScrollListenerConversations() {
        const tableContainer = document.querySelector(".chat-list");
        if (tableContainer) {
            tableContainer.addEventListener("scroll", this.handleScroll.bind(this));
        }
    }


    handleScroll() {
        const tableContainer = document.querySelector(".chat-list");
        if (!tableContainer) return;

        const scrollBottom =
            tableContainer.scrollHeight -
            tableContainer.scrollTop -
            tableContainer.clientHeight;
        if (scrollBottom < 20 && !this.state.is_loading_conversations && this.state.has_more_conversations) {
            this.fetchDebounced();
        }
    }

}

registry.category("actions").add("whatsapp_chat_action", WhatsappChat);