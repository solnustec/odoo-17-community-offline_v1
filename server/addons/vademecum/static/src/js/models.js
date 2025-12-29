/** @odoo-module */

class Medicine {
    constructor(data = {}) {
      this.name = data.name || '';
      this.active_principles = data.active_principles || [];
      this.concentration = data.concentration || '';
    }
  
    // Getters
    getName() {
      return this.name;
    }
  
    getActivePrinciples() {
        return this.active_principles;
    }

    getConcentration() {
      return this.concentration;
    }

    // Setters
    setName(name) {
      this.name = name;
    }
  
    setActivePrinciples(activePrinciples) {
        this.active_principles = activePrinciples; // Asigna una lista
    }

    setConcentration(concentration) {
      this.concentration = concentration;
    }
  
    // Method to initialize from JSON data
    initFromJSON(json) {
      this.name = json.name || '';
      this.active_principle = json.active_principle || '';
      this.concentration = json.concentration || '';
    }
  
    // Method to export data as JSON
    exportAsJSON() {
      return {
        name: this.name,
        active_principles: this.active_principles,
        concentration: this.concentration,
      };
    }
  
    // Method to export data for printing or display
    exportForPrinting() {
      return {
        name: this.getName(),
        active_principles: this.getActivePrinciples(), // Incluye lista
        concentration: this.getConcentration(),
      };
    }
  }
  
  export default Medicine;
  