# Importar Notas de Crédito de Proveedores desde TXT del SRI

## 1. Resumen ejecutivo
Este módulo permite cargar un archivo TXT descargado del SRI con claves de autorización de notas de crédito de proveedores, consultar automáticamente el web service de autorizaciones, interpretar el XML y crear las notas en borrador en Odoo 17. Resuelve el problema operativo de digitar manualmente documentos de reverso, asegurando trazabilidad con la factura de origen, consistencia tributaria y clasificación contable según el motivo de la nota.

## 2. Características principales
- **Carga masiva desde TXT (SRI)**: lee la columna `CLAVE_ACCESO` y procesa solo claves válidas de 49 dígitos.
- **Consulta en línea al SRI** mediante WSDL oficial para recuperar el XML autorizado.
- **Creación automática de notas de crédito** de proveedor (`in_refund`) en borrador con impuestos, referencia y vínculo a la factura original.
- **Clasificación por tipo de nota** usando palabras clave configurables (devolución, pronto pago, descuento, bonificación) y aplicación automática de la cuenta contable.
- **Detección de productos, impuestos y banco** reutilizando la información de la factura origen y de los detalles del XML.
- **Botón "Subir .txt"** en la lista de notas de crédito de proveedores para abrir el asistente sin salir de la vista.
- **Catálogo mantenible** de tipos de nota y palabras clave administrable desde Contabilidad › Configuración.

## 3. Arquitectura interna del módulo
```
addons/purchase_upload_credit_note_suppliers/
├── __manifest__.py          # Declaración del módulo, dependencias y assets web
├── __init__.py              # Inicialización de modelos Python
├── models/
│   ├── account_move.py      # Extiende account.move con campos y onchange
│   ├── credit_note_type.py  # Catálogo de tipos de nota; init con valores base
│   ├── credit_note_type_keyword.py  # Palabras clave por tipo; init con defaults
│   └── import_sri_credit_note_txt_wizard.py  # Wizard transitorio para importar TXT
├── security/
│   └── ir.model.access.csv  # Permisos para wizard y catálogos
├── views/
│   ├── account_move_view.xml               # Inserta campos y hereda autorización SRI
│   ├── credit_note_type_view.xml           # Menú, acción y vistas tree/form del catálogo
│   └── import_sri_credit_note_txt_wizard_view.xml  # Formulario modal del asistente
├── static/src/js/account_upload.js         # Parche al controlador de lista para abrir wizard
└── static/src/xml/accountViewUploadButton.xml  # Botón "Subir .txt" en la vista lista
```
- **Datos y seguridad**: el CSV de accesos habilita a usuarios internos a usar el wizard y mantener catálogos.
- **Vistas**: herencias sobre formularios y listas de `account.move` para mostrar `reason` y `credit_note_type`; vista para palabras clave en cuaderno.
- **Assets web**: se inyectan en `web.assets_backend` para agregar el botón y la acción de apertura del wizard.

## 4. Flujo funcional (paso a paso)
1. El usuario abre **Contabilidad › Proveedores › Notas de crédito** (lista de compras).
2. Presiona **Subir .txt**, que abre el asistente `import.sri.credit.note.txt.wizard` en un diálogo modal.
3. Carga el archivo TXT exportado del SRI (tsv con columna `CLAVE_ACCESO`).
4. El asistente valida claves (49 dígitos) y, por cada clave válida:
   - Consulta el web service de autorizaciones del SRI.
   - Limpia y parsea el XML devuelto.
   - Ubica o crea el proveedor según RUC.
   - Localiza la factura origen (`in_invoice`) por número y fecha de sustento.
   - Determina el tipo de nota por palabras clave del motivo y aplica la cuenta contable correspondiente.
   - Construye líneas de producto con impuestos de IVA y cuentas.
5. Se crean notas de crédito en borrador (`in_refund`) enlazadas a la factura, con clave de autorización y número SRI.
6. Odoo muestra una vista filtrada con las notas recién generadas para revisión y validación.

## 5. Explicación técnica
### Modelos principales y campos clave
- **`account.move`** (`models/account_move.py`):
  - `reason` (Text): motivo de la nota.
  - `credit_note_type` (Many2one `credit.note.type`): clasificación del motivo.
  - `@api.onchange('credit_note_type')`: si la nota es `in_refund`, aplica la cuenta del tipo a todas las líneas.
- **`credit.note.type`** (`models/credit_note_type.py`): nombre, `code` interno, `account_id` contable y `keyword_ids`. `init` crea tipos base: devolución, pronto pago, descuento, bonificación.
- **`credit.note.type.keyword`** (`models/credit_note_type_keyword.py`): `keyword` asociado a un `type_id`; `init` precarga palabras clave por tipo.
- **`import.sri.credit.note.txt.wizard`** (`models/import_sri_credit_note_txt_wizard.py`): campos `file` (binary) y `filename`; métodos de consulta y parsing del SRI; `action_import` genera los movimientos.

### Onchange, compute y lógica de negocio
- **Onchange en `account.move`**: tras elegir `credit_note_type`, si existe `account_id` se asigna a cada línea (`invoice_line_ids`). Esto fuerza la consistencia contable según el motivo.【F:addons/purchase_upload_credit_note_suppliers/models/account_move.py†L17-L38】
- **Parsing y creación** (wizard):
  - `_get_xml_from_sri` usa `zeep` y WSDL oficial; falla si no hay autorización o falta el XML.
  - `_convert_xml_to_element_tree` limpia saltos y CDATA antes de usar `ElementTree`.
  - `_obtain_or_create_partner` busca por RUC y crea proveedor con `supplier_rank=1` y tipo de identificación RUC.
  - `_obtain_credit_note_type` normaliza el motivo y busca coincidencias en palabras clave normalizadas.
  - `_find_purchase_vat_tax` prioriza impuestos activos de compra/none que coincidan en porcentaje y contengan “IVA”; fallback por nombre.
  - `_obtain_product_lines` detecta productos por `default_code` o nombre; asigna cantidad, precio, IVA y cuenta (del tipo de nota o del producto).【F:addons/purchase_upload_credit_note_suppliers/models/import_sri_credit_note_txt_wizard.py†L175-L263】
  - `_parse_credit_note_xml` valida estructura, obtiene datos tributarios, factura relacionada, fechas, motivo, tipo y líneas; si falta la factura lanza `UserError` instructivo.【F:addons/purchase_upload_credit_note_suppliers/models/import_sri_credit_note_txt_wizard.py†L265-L343】
  - `action_import` recorre claves válidas, consulta SRI, parsea, y crea `account.move` en borrador con impuestos, banco, motivo, tipo y vínculo `reversed_entry_id`; devuelve acción filtrada a las notas creadas.【F:addons/purchase_upload_credit_note_suppliers/models/import_sri_credit_note_txt_wizard.py†L345-L417】

### Wizards y propósito
- **Importar TXT**: formulario modal con campos `file` y `filename`; botón **Importar** ejecuta `action_import`. Actúa como entrada única al proceso y gestiona validaciones de claves, conexión SRI, parsing y creación de notas.【F:addons/purchase_upload_credit_note_suppliers/views/import_sri_credit_note_txt_wizard_view.xml†L1-L23】

### Integraciones con otros módulos
- **`account`**: creación y herencia de `account.move`, impuestos, productos y vistas.
- **`web`**: assets backend (JS/XML) para extender la lista con el botón de carga.【F:addons/purchase_upload_credit_note_suppliers/__manifest__.py†L9-L20】【F:addons/purchase_upload_credit_note_suppliers/static/src/xml/accountViewUploadButton.xml†L1-L15】
- **`l10n_ec_edi`**: hereda vista para mostrar `l10n_ec_authorization_number` en notas de proveedor y usar campos de autorización/documento SRI.【F:addons/purchase_upload_credit_note_suppliers/views/account_move_view.xml†L12-L23】

### Dependencias y razones
- `base`: modelos y seguridad base.
- `account`: facturación, notas de crédito y impuestos.
- `web`: assets Owl para añadir el botón y abrir el wizard desde listas.
- `l10n_ec_edi`: campos y vistas de autorización SRI para documentos ecuatorianos.
- Python `zeep`: requerido para consumir el web service del SRI (notificado al usuario si falta).

## 6. Diagrama textual del flujo
```
TXT SRI (CLAVE_ACCESO) → Wizard importa → Valida claves (49 dígitos)
    → Por cada clave válida → Llama WSDL SRI (Autorización)
        → XML autorizado → Limpia/parsea → Valida estructura
            → Busca/crea proveedor por RUC
            → Identifica factura origen (numDocModificado + fecha)
            → Normaliza motivo → Busca tipo por palabras clave → Obtiene cuenta
            → Genera líneas (producto, qty, precio, IVA, cuenta)
            → Crea account.move in_refund en borrador (clave, número, fechas, ref, banco, vínculo factura)
→ Devuelve acción con lista filtrada de NC creadas → Usuario revisa y valida
```

## 7. Instalación
### Requisitos técnicos
- Odoo 17 instalado.
- Acceso a Internet desde el servidor Odoo para consumir el WSDL del SRI.
- Python package `zeep` disponible en el entorno.

### Dependencias Odoo
- `base`, `account`, `web`, `l10n_ec_edi` (se instalan automáticamente al instalar el módulo).

### Instalación en Odoo 17 (entorno local)
1. Copiar la carpeta `purchase_upload_credit_note_suppliers` dentro de `addons` y actualizar el `addons_path`.
2. Instalar dependencias Python si faltan: `pip install zeep`.
3. Actualizar aplicaciones y buscar **Importar Notas de Crédito SRI desde TXT**.
4. Instalar el módulo.

### Instalación con Docker
1. Asegurar que la imagen incluya `zeep` (agregar a `requirements.txt` o `pip install zeep` en el Dockerfile).
2. Montar el módulo en el `addons_path` del contenedor (volumen o build).
3. Ejecutar actualización de lista de apps dentro del contenedor y luego instalar el módulo desde la interfaz o con `-u purchase_upload_credit_note_suppliers`.

## 8. Configuración en Odoo
- **Tipos de nota de crédito**: Contabilidad › Configuración › **Tipos de Notas de Crédito**. Crear/editar registros con nombre, código y **cuenta contable** para que el onchange la propague a las líneas.
- **Palabras clave**: en cada tipo, pestaña **Palabras clave**. Agregar términos representativos del motivo (sin tildes, variaciones comunes) para mejorar la detección automática.
- **Impuestos**: verificar IVA de compra activos con tarifas requeridas (0%, 12%, 15%).
- **Factura origen**: debe existir la factura de proveedor con número (`l10n_latam_document_number`) y fecha que coincidan con `numDocModificado` y `fechaEmisionDocSustento` del XML.
- **Permisos**: usuarios internos (grupo base) pueden usar el wizard y mantener catálogos; ajustar si se requiere mayor restricción en `ir.model.access.csv`.

## 9. Modo de uso detallado
1. Descargar del portal SRI el TXT que contenga las claves de acceso de las notas de crédito de proveedores.
2. En Odoo, ir a **Contabilidad › Proveedores › Notas de crédito**.
3. Presionar **Subir .txt** (visible solo en notas de crédito de proveedor).
4. En el asistente, cargar el archivo y pulsar **Importar**.
5. Revisar los mensajes de error si los hay (clave no autorizada, XML inválido, factura no encontrada, falta de `zeep`).
6. El asistente crea las notas en borrador con motivo, tipo sugerido, impuestos, cuenta contable y vínculo a la factura.
7. Abrir la nota creada desde la lista filtrada, ajustar tipo/motivo si es necesario y **Validar**.

## 10. Consideraciones contables, lógicas y buenas prácticas
- Configure la **cuenta contable** en cada tipo de nota para asegurar clasificación consistente; de lo contrario se usarán cuentas de producto o quedarán vacías.
- Mantenga actualizadas las **palabras clave** para reflejar terminología de sus proveedores.
- Verifique que las facturas de origen existan con el mismo número y fecha; el asistente bloqueará la creación si no las encuentra.
- Confirme la **autorización SRI** y el número SRI en el registro (`l10n_ec_authorization_number`, `l10n_latam_document_number`).
- Revise impuestos generados; `_find_purchase_vat_tax` busca coincidencias exactas de porcentaje, luego por nombre.
- Si usa múltiples compañías, asegúrese de que los impuestos y cuentas existan en cada compañía.

## 11. Troubleshooting (errores comunes del SRI)
- **"Falta 'zeep'"**: instale con `pip install zeep` en el entorno del servidor.
- **"No se encontró autorización para la clave"**: la clave no está autorizada o es incorrecta; verifique el TXT o el estado en el SRI.
- **"El XML no corresponde a una Nota de Crédito"**: el SRI devolvió otro comprobante; confirme la clave.
- **"No se encontró la factura..."**: cree primero la factura de proveedor con el mismo número (`numDocModificado`) y fecha de sustento.
- **Errores de parseo XML**: descargue nuevamente el TXT o reintente; el asistente limpia CDATA y saltos pero falla ante XML incompleto.
- **Impuesto no asignado**: agregue o active el impuesto de compra con la tarifa exacta y nombre que contenga el porcentaje.

## 12. Changelog sugerido
- **17.0.1.0.0**: versión inicial. Importación desde TXT, consulta SRI, creación de NC, detección por palabras clave, assets web y catálogos configurables.

## 13. Roadmap de mejoras
- Reintentos y timeouts configurables para el web service del SRI.
- Asignación de impuestos y cuentas por producto/partner con reglas avanzadas.
- Reporte de log de importación (aciertos/errores) descargable.
- Pruebas unitarias y de integración para los métodos de parsing y asignación de impuestos.
- Soporte para múltiples compañías con configuración por compañía en tipos y palabras clave.

## 14. Licencia
LGPL-3, conforme al manifiesto del módulo.