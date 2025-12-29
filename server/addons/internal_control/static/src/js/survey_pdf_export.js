/** @odoo-module **/

import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { archParseBoolean } from "@web/views/utils";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";
import { _t } from "@web/core/l10n/translation";
import { jsonrpc } from "@web/core/network/rpc_service";
import { SurveyExportDialog } from "./survey_export_dialog";
import { Component } from "@odoo/owl";

const cogMenuRegistry = registry.category("cogMenu");

/**
 * 'Exportar Métricas de Encuesta PDF' menu
 *
 * Este componente se usa para exportar PDF los registros de métricas de encuesta con observaciones.
 * @extends Component
 */
export class SurveyExportPdf extends Component {
    static template = "web.SurveyExportPdf";
    static components = { DropdownItem };

    //---------------------------------------------------------------------
    // Protected
    //---------------------------------------------------------------------
    
    async onDirectExportPdf() {
        this.env.searchModel.trigger('direct-export-pdf');
        var self = this.__owl__.parent.parent.parent.parent.parent.component;
        
        // Get available fields from the current view
        const fields = this.__owl__.parent.parent.parent.parent.parent.component.props.archInfo.columns
            .filter((col) => col.type === "field")
            .map((col) => this.__owl__.parent.parent.parent.parent.parent.component.props.fields[col.name])
        
        const exportedFields = fields.map((field) => ({
            name: field.name,
            label: field.label || field.string,
        }));
        
        const resIds = await this.__owl__.parent.parent.parent.parent.parent.component.getSelectedResIds();
        
        // Show the extended dialog
        this.__owl__.parent.parent.parent.parent.parent.component.dialogService.add(SurveyExportDialog, {
            title: _t("Exportar Métricas de Encuesta PDF"),
            body: _t("Seleccione los campos que desea exportar y agregue observaciones opcionales:"),
            exportedFields: exportedFields,
            confirm: (observations) => {
                let exportField = [];
                // Use the exact same selector as the original module
                let checkboxes = document.querySelectorAll(`#${'check'} input[type="checkbox"]`);
                console.log('Found checkboxes:', checkboxes.length); // Debug log
                
                checkboxes.forEach(item => {
                    console.log('Checkbox:', item.name, item.value, item.checked); // Debug log
                    if (item.checked === true) {
                        exportField.push({name: item.name, label: item.value})
                    }
                });
                
                console.log('Selected fields:', exportField); // Debug log
                
                var length_field = Array.from(Array(exportField.length).keys());
                
                // Call our extended controller
                jsonrpc('/survey/get_export_data', {
                    'model': this.__owl__.parent.parent.parent.parent.parent.component.model.root.resModel,
                    'res_ids': resIds.length > 0 && resIds,
                    'fields': exportField,
                    'grouped_by': this.__owl__.parent.parent.parent.parent.parent.component.model.root.groupBy,
                    'context': this.__owl__.parent.parent.parent.parent.parent.component.props.context,
                    'domain': this.__owl__.parent.parent.parent.parent.parent.component.model.root.domain,
                    'observations': observations,
                }).then(function (data) {
                    console.log('Controller response:', data); // Debug log
                    
                    if (self.model.root.groupBy[0]) {
                        var group_length = Array.from(Array(self.model.root.groups));
                        var action = {
                            'type': 'ir.actions.report',
                            'report_type': 'qweb-pdf',
                            'report_name': 'internal_control.export_survey_metrics_group_by',
                            'data': {
                                'length': length_field,
                                'group_len': [0, 1, 2, 3],
                                'record': data
                            }
                        };
                    } else {
                        var action = {
                            'type': 'ir.actions.report',
                            'report_type': 'qweb-pdf',
                            'report_name': 'internal_control.export_survey_metrics',
                            'data': {
                                'length': length_field,
                                'record': data
                            }
                        };
                    }
                    return self.model.action.doAction(action);
                });
            },
            cancel: () => {},
        });
    }
}

// Registrar el elemento del menú de exportación PDF para modelos de métricas de encuesta
export const surveyExportPdfItem = {
    Component: SurveyExportPdf,
    groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
    isDisplayed: async (env) => {
        // Only show for survey metrics models
        const surveyModels = [
            'survey.revised.items',
            'survey.compliance', 
            'survey.satisfaction',
            'survey.participation'
        ];
        
        return env.config.viewType === "list" &&
               surveyModels.includes(env.model.root.resModel) &&
               !env.model.root.selection.length &&
               await env.model.user.hasGroup("base.group_allow_export") &&
               archParseBoolean(env.config.viewArch.getAttribute("export_xlsx"), true);
    },
};

cogMenuRegistry.add("survey-export-pdf-menu", surveyExportPdfItem, { sequence: 10 }); 