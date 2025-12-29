function printReceipt() {
    var receiptContainer = document.getElementById("receipt-container");
    if (!receiptContainer) {
        return;
    }

    var printWindow = window.open('', '_blank');
    var styles = `
        <style>
            ${document.querySelector('#receipt-container style')?.innerHTML || ''}
            body { 
                margin: 0;
                font-family: Arial, sans-serif;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 5px;
                border: 1px solid #ddd;
                page-break-inside: avoid;
            }
            @media print {
                .modal-body {
                    max-height: none !important;
                    overflow: visible !important;
                }
                tr {
                    page-break-inside: avoid;
                }
                .page-break {
                    page-break-before: always;
                }
            }
        </style>
    `;

    printWindow.document.write(`
        <html>
            <head>
                <title>Regulação de Inventário</title>
                ${styles}
            </head>
            <body>
                ${receiptContainer.innerHTML}
            </body>
        </html>
    `);

    printWindow.document.close();
    printWindow.focus();
    
    setTimeout(function() {
        printWindow.print();
        printWindow.close();
    }, 500);
}