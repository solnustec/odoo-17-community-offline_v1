# Sistema de Asignaciones de Encuestas

Este módulo provee dos sistemas de asignación de encuestas:

1. **Campañas de Encuestas** - Asignación masiva por departamento/cargos
2. **Visitas a Sucursales** - Programación de visitas para evaluación

---

## 1. CAMPAÑAS DE ENCUESTAS

### Modelos

#### `in.survey.campaign` (Campaña de Encuesta)

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `name` | Char | Sí | Nombre de la campaña |
| `survey_id` | Many2one | Sí | Encuesta base a aplicar |
| `department_id` | Many2one | Sí | Departamento objetivo |
| `date_start` | Date | Sí | Fecha inicio de vigencia |
| `date_end` | Date | Sí | Fecha fin de vigencia |
| `job_ids` | Many2many | No | Filtro por cargos (opcional) |
| `employee_ids` | Many2many | No | Empleados específicos (opcional) |
| `state` | Selection | - | draft/active/closed/cancelled |
| `assignment_ids` | One2many | - | Asignaciones generadas |

#### `in.survey.campaign.assignment` (Asignación Individual)

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `campaign_id` | Many2one | Sí | Campaña padre |
| `employee_id` | Many2one | Sí | Empleado asignado |
| `state` | Selection | - | pending/answered/expired |
| `user_input_id` | Many2one | - | Respuesta vinculada |

### Flujo de Campañas

```
┌──────────────────────┐
│  1. CREAR CAMPAÑA    │
│     (estado: draft)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  2. Configurar:      │
│  • Encuesta base     │
│  • Departamento      │
│  • Fechas            │
│  • Cargos (opcional) │
│  • Empleados (opc.)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  3. CONFIRMAR        │
│  → Crea asignaciones │
│  → Envía emails      │
│  → Crea actividades  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  4. Empleados        │
│     responden        │
└──────────────────────┘
```

### Ubicación en Menú

```
Encuestas
└── Encuestas
    ├── Programar actividad      ← CAMPAÑAS
    └── Mis Encuestas Asignadas  ← Vista del empleado
```

---

## 2. VISITAS A SUCURSALES

Sistema de programación de visitas para evaluación de sucursales.

### Modelos

#### `survey.branch.visit` (Visita Programada)

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `employee_id` | Many2one | Sí | Empleado asignado |
| `branch_id` | Many2one | Sí | Sucursal a evaluar (stock.warehouse) |
| `scheduled_date` | Date | Sí | Fecha programada |
| `survey_id` | Many2one | Sí | Encuesta de evaluación |
| `state` | Selection | - | programada/completada/vencida/cancelada |
| `user_input_id` | Many2one | - | Respuesta vinculada |
| `scheduled_by_id` | Many2one | - | Quién programó (auditoría) |
| `notes` | Text | No | Notas opcionales |

#### `survey.branch.visit.wizard` (Wizard de Carga en Lote)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `survey_id` | Many2one | Encuesta a usar |
| `line_ids` | One2many | Líneas de visitas a programar |

#### `survey.branch.visit.wizard.line` (Línea del Wizard)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `employee_id` | Many2one | Empleado |
| `branch_id` | Many2one | Sucursal |
| `scheduled_date` | Date | Fecha |
| `notes` | Char | Notas |

### Flujo de Visitas

```
┌─────────────────────────────────────────────────────────────┐
│                    ADMINISTRATIVO                            │
│         (tiene el cronograma de visitas del mes)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              WIZARD: "Programar Visitas"                     │
│                                                             │
│  ┌───────────────┬──────────────────┬────────────┬─────┐   │
│  │   EMPLEADO    │     SUCURSAL     │   FECHA    │  ✕  │   │
│  ├───────────────┼──────────────────┼────────────┼─────┤   │
│  │ Juan Pérez    │ Farmacia Centro  │ 08/01/2026 │  🗑  │   │
│  │ Juan Pérez    │ Farmacia Norte   │ 15/01/2026 │  🗑  │   │
│  │ María García  │ Farmacia Sur     │ 10/01/2026 │  🗑  │   │
│  └───────────────┴──────────────────┴────────────┴─────┘   │
│                                                             │
│  [+ Agregar línea]        [PROGRAMAR VISITAS]               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  SISTEMA:                                                   │
│  • Crea registros survey.branch.visit                       │
│  • Envía email a cada empleado                              │
│  • Crea actividades (campana)                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      EMPLEADOS                               │
│                                                             │
│  Ven en "Mis Visitas" lo que deben evaluar                  │
│  Click "Evaluar Sucursal" → Abre encuesta                   │
│  Al completar → estado cambia a "completada"                │
└─────────────────────────────────────────────────────────────┘
```

### Vista del Empleado

```
┌─────────────────────────────────────────────────────────────┐
│  📋 MIS VISITAS PROGRAMADAS                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ⏳ PRÓXIMAS / PENDIENTES                                   │
│  ┌──────────────────┬────────────┬──────────────────────┐  │
│  │ Farmacia Centro  │ 15/01/2026 │  [EVALUAR SUCURSAL]  │  │
│  │ Farmacia Norte   │ 22/01/2026 │  [EVALUAR SUCURSAL]  │  │
│  └──────────────────┴────────────┴──────────────────────┘  │
│                                                             │
│  ✅ COMPLETADAS                                             │
│  ┌──────────────────┬────────────┬──────────────────────┐  │
│  │ Farmacia Centro  │ 05/01/2026 │  [VER EVALUACIÓN]    │  │
│  └──────────────────┴────────────┴──────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Ubicación en Menú

```
Encuestas
└── Visitas a Sucursales      ← NUEVO
    ├── Programar Visitas     ← Wizard (administrativo)
    ├── Todas las Visitas     ← Vista lista (administrativo)
    └── Mis Visitas           ← Vista lista (empleado)
```

### Vistas Disponibles

| Vista | Descripción |
|-------|-------------|
| Tree | Lista con fecha, empleado, sucursal, estado |
| Kanban | Tarjetas agrupadas por estado |
| Calendar | Vista de calendario mensual |
| Form | Formulario detallado con botones de acción |
| Pivot | Análisis de visitas por empleado/estado |
| Graph | Gráfico de barras por estado |

---

## 3. INTEGRACIÓN CON survey.user_input

Cuando el empleado completa una encuesta, el sistema:

1. Detecta si viene de una **campaña** (`assignment_id`) o **visita** (`branch_visit_id`)
2. Actualiza el estado correspondiente:
   - Campaña: `assignment.state = 'answered'`
   - Visita: `visit.state = 'completada'`
3. Vincula la respuesta (`user_input_id`)
4. Calcula métricas según categoría de encuesta

### Campos en survey.user_input

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `campaign_id` | Many2one | Campaña (si aplica) |
| `assignment_id` | Many2one | Asignación de campaña |
| `branch_visit_id` | Many2one | Visita a sucursal (si aplica) |

---

## 4. ARCHIVOS DEL SISTEMA

### Campañas

| Archivo | Contenido |
|---------|-----------|
| `models/in_survey_campaign.py` | Modelos Campaign y Assignment |
| `views/survey_campaign_views.xml` | Vistas y acciones |
| `views/survey_menu.xml` | Menús |

### Visitas a Sucursales

| Archivo | Contenido |
|---------|-----------|
| `models/survey_branch_visit.py` | Modelo Visit y Wizards |
| `views/survey_branch_visit_views.xml` | Vistas, acciones y menús |
| `data/email_templates.xml` | Template de email |

### Compartido

| Archivo | Contenido |
|---------|-----------|
| `models/in_survey_input.py` | Extensión de survey.user_input |
| `security/ir.model.access.csv` | Permisos |

---

## 5. VALIDACIONES

### Visitas a Sucursales

| Validación | Comportamiento |
|------------|----------------|
| Visita duplicada | Error si existe misma combinación empleado+sucursal+fecha+encuesta |
| Fecha en el pasado | Permitido (para correcciones) |
| Estado completada | No permite abrir encuesta nuevamente |
| Estado cancelada | No permite abrir encuesta |

---

## 6. NOTIFICACIONES

### Email

- **Campañas**: Template `email_template_survey_assignment`
- **Visitas**: Template `email_template_branch_visit`

### Actividades

Se crea una actividad tipo "Por Hacer" con:
- Usuario: empleado asignado
- Fecha límite: fecha fin (campaña) o fecha programada (visita)
- Resumen: nombre de campaña/sucursal

---

## 7. COMPARACIÓN DE SISTEMAS

| Característica | Campañas | Visitas a Sucursales |
|----------------|----------|---------------------|
| **Uso principal** | Encuestas masivas por departamento | Evaluación de sucursales específicas |
| **Requiere** | Departamento obligatorio | Sucursal (stock.warehouse) |
| **Fechas** | Rango (inicio-fin) compartido | Fecha individual por visita |
| **Asignación** | Automática al confirmar | Manual en wizard |
| **Flexibilidad** | Menor (por departamento) | Mayor (empleado-sucursal específico) |
| **Wizard** | No | Sí (carga en lote) |

---

## 8. INSTALACIÓN

Después de desplegar los cambios, ejecutar:

```bash
./odoo-bin -u internal_control -d tu_base_de_datos
```

Esto creará:
- Los nuevos modelos en la base de datos
- Los menús de "Visitas a Sucursales"
- Los templates de email
- Los permisos de acceso
