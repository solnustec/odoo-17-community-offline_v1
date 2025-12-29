/** @odoo-module */
import { TimeOffCard } from "@hr_holidays/dashboard/time_off_card";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";


const originalSetup = TimeOffCard.prototype.setup;

patch(TimeOffCard.prototype, {
     setup() {
        originalSetup.apply(this, arguments);
        this.orm = useService("orm");
        this._loadEmployeeDepartmentField();


    },
    async _loadEmployeeDepartmentField() {
        try {

            const employees = await this.orm.call(
                'hr.employee',
                'search_read',
                [[['user_partner_id', '=', this.env.services.user.partnerId]]],
                { fields: ['id', 'department_id'] }
            );

            if (!employees || employees.length === 0) {
                console.warn("No se encontró empleado para el partnerId:", this.env.services.user.partnerId);
                return;
            }

            const employee = employees[0];

            if (!employee.department_id || !employee.department_id[0]) {
                console.warn("El empleado no tiene departamento asignado");
                return;
            }

            const departmentId = employee.department_id[0];

            const departments = await this.orm.call(
                'hr.department',
                'search_read',
                [[['id', '=', departmentId]]],
                { fields: ['periodes_leaves'] }
            );

            if (!departments || departments.length === 0) {
                console.warn("No se encontró el departamento con ID:", departmentId);
                return;
            }

            const department = departments[0];
            this.props.data.departmentFieldValue = department.periodes_leaves;
        } catch (error) {
            console.error("Error al cargar el empleado o departamento:", error);
        }
    }

});
