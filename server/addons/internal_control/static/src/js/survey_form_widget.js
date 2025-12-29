/** @odoo-module */
import SurveyFormWidget from 'internal_control/js/survey_form_mock';

SurveyFormWidget.include({
    /** Get all question answers by question type */
    _prepareSubmitValues(formData, params) {
        this._super?.(...arguments); // Usa optional chaining por si no existe _super
        this.$('[data-question-type]').each(function () {
            if ($(this).data('questionType') === 'upload_file'){
                params[this.name] = [$(this).data('oe-data'), $(this).data('oe-file_name')];
            }
        });
    },
});
