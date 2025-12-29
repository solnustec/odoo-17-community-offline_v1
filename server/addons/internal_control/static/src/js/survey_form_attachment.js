/** @odoo-module **/

import SurveyFormWidget from '@survey/js/survey_form';

const baseEvents = SurveyFormWidget.prototype.events || {};
const myEvents = {
    'change .o_survey_upload_file': '_onFileChange',
    'submit': '_onSubmitSurveyForm',
};

SurveyFormWidget.include({

    events: Object.assign({}, baseEvents, myEvents),

    _onSubmitSurveyForm: function (event) {
        const $form = this.$el;
        const $input = $form.find('input.o_survey_upload_file');

        const data = $input.attr('data-oe-data');
        const fileNames = $input.attr('data-oe-file_name');

        if (data && fileNames) {
            // Inserta el valor con el "name" esperado por Odoo
            $('<input>', {
                type: 'hidden',
                name: $input.attr('name'),
                value: JSON.stringify([JSON.parse(data)[0], JSON.parse(fileNames)[0]])
            }).appendTo($form);
        }
    },
    _prepareSubmitValues(formData, params) {
         // Usa optional chaining por si no existe _super
        this.$('[data-question-type]').each(function () {
            if ($(this).data('questionType') === 'upload_file'){
                params[this.name] = [$(this).data('oe-data'), $(this).data('oe-file_name')];
            }
        });
        this._super?.(...arguments);
    },

    _onFileChange: function (event) {
        var self = this;
        var files = event.target.files;
        var fileNames = [];
        var dataURLs = [];

        for (let i = 0; i < files.length; i++) {
            var reader = new FileReader();
            reader.readAsDataURL(files[i]);
            reader.onload = function (e) {
                var file = files[i];
                var filename = file.name;
                var dataURL = e.target.result.split(',')[1];
                fileNames.push(filename);
                dataURLs.push(dataURL);

                var $input = self.$el.find('input.o_survey_upload_file');
                $input.attr('data-oe-data', JSON.stringify(dataURLs));
                $input.attr('data-oe-file_name', JSON.stringify(fileNames));

                var fileList = document.getElementById('fileList');
                if (fileList) {
                    fileList.innerHTML = '';
                    var ul = document.createElement('ul');
                    fileNames.forEach(function (fileName) {
                        var li = document.createElement('li');
                        li.textContent = fileName;
                        ul.appendChild(li);
                    });

                    var deleteBtn = document.createElement('button');
                    deleteBtn.textContent = 'Eliminar Todos';
                    deleteBtn.className = 'btn btn-danger btn-sm';
                    deleteBtn.addEventListener('click', function () {
                        fileList.innerHTML = '';
                        $input.attr('data-oe-data', '');
                        $input.attr('data-oe-file_name', '');
                        self.$el.find('input[type="file"]').val('');
                    });

                    fileList.appendChild(ul);
                    fileList.appendChild(deleteBtn);
                }
            }
        }

        const $target = $(event.currentTarget);
        const $choiceItemGroup = $target.closest('.o_survey_form_choice');

        this._applyCommentAreaVisibility($choiceItemGroup);
        const isQuestionComplete = this._checkConditionalQuestionsConfiguration($target, $choiceItemGroup);
        if (isQuestionComplete && this.options.usersCanGoBack) {
            const isLastQuestion = this.$('button[value="finish"]').length !== 0;
            if (!isLastQuestion) {
                const questionHasComment = $target.hasClass('o_survey_js_form_other_comment') || $target
                    .closest('.o_survey_form_choice')
                    .find('.o_survey_comment').length !== 0;
                if (!questionHasComment) {
                    this._submitForm({'nextSkipped': $choiceItemGroup.data('isSkippedQuestion')});
                }
            }
        }
    },

});



