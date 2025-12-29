/** @odoo-module */

class Warehouse {
    constructor(data = {}) {
        this.name = data.name || '';
        this.available_quantity = data.available_quantity || 0;
    }

    // Getters
    getName() {
        return this.name;
    }

    getAvailableQuantity() {
        return this.available_quantity;
    }

    // Setters
    setName(name) {
        this.name = name;
    }

    setAvailableQuantity(quantity) {
        this.available_quantity = quantity;
    }

    // Método para inicializar desde JSON
    initFromJSON(json) {
        this.name = json.name || '';
        this.available_quantity = json.available_quantity || 0;
    }

    // Método para exportar como JSON
    exportAsJSON() {
        return {
            name: this.name,
            available_quantity: this.available_quantity,
        };
    }
}

export default Warehouse;
