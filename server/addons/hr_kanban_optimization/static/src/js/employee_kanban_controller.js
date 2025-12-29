/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { registry } from "@web/core/registry";

/**
 * EmployeeKanbanController
 *
 * Custom Kanban controller for hr.employee that:
 * - Injects optimization context (kanban_view_optimization: True)
 * - Handles cache invalidation on CRUD operations
 */
export class EmployeeKanbanController extends KanbanController {
    setup() {
        super.setup();
        // Add optimization context to the model
        this.props.context = {
            ...this.props.context,
            kanban_view_optimization: true,
        };
    }

    /**
     * Override to ensure optimization context is passed
     */
    async createRecord() {
        const result = await super.createRecord(...arguments);
        // Invalidate client-side cache after creation
        this._invalidateClientCache();
        return result;
    }

    /**
     * Invalidate client-side caches
     */
    _invalidateClientCache() {
        // Clear any client-side caches
        if (window._employeeDetailsCache) {
            window._employeeDetailsCache.clear();
        }
        if (window._employeeActivitiesCache) {
            window._employeeActivitiesCache.clear();
        }
    }
}

/**
 * EmployeeKanbanRenderer
 *
 * Custom renderer with potential optimizations
 */
export class EmployeeKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
        // Initialize global caches for client-side caching
        if (!window._employeeDetailsCache) {
            window._employeeDetailsCache = new Map();
        }
        if (!window._employeeActivitiesCache) {
            window._employeeActivitiesCache = new Map();
        }
    }
}

/**
 * Register the optimized employee kanban view
 */
export const employeeKanbanOptimizedView = {
    ...kanbanView,
    Controller: EmployeeKanbanController,
    Renderer: EmployeeKanbanRenderer,
};

registry.category("views").add("employee_kanban_optimized", employeeKanbanOptimizedView);
