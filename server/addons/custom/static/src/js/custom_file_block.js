document.addEventListener('DOMContentLoaded', function () {
    const fileZones = document.getElementsByClassName('o_files_zone');
    Array.prototype.forEach.call(fileZones, function (fileZone) {
        if (fileZone.type === 'file') {
            fileZone.onchange = null;
            fileZone.addEventListener('change', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                const files = ev.target.files;
                if (files.length > 0) {
                }
            });
        }
    });
});
