#!/bin/bash
# =====================================================
# Script para crear backup de Odoo en formato .zip
# Compatible con restauración desde interfaz web
# =====================================================
#
# Uso:
#   ./backup_odoo_database.sh <nombre_bd> [directorio_salida]
#
# Ejemplo:
#   ./backup_odoo_database.sh odoonueva ./backups
#
# =====================================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }

# Parámetros
DB_NAME="${1:-odoonueva}"
OUTPUT_DIR="${2:-.}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="${DB_NAME}_backup_${TIMESTAMP}"
TEMP_DIR="/tmp/${BACKUP_NAME}"

# Configuración de contenedores (ajustar según tu docker-compose)
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres-offline}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo-offline}"
DB_USER="${DB_USER:-odoo}"

echo ""
echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}     BACKUP DE BASE DE DATOS ODOO${NC}"
echo -e "${BLUE}=====================================================${NC}"
echo ""

print_info "Base de datos: $DB_NAME"
print_info "Contenedor PostgreSQL: $POSTGRES_CONTAINER"
print_info "Contenedor Odoo: $ODOO_CONTAINER"
echo ""

# Verificar que los contenedores estén corriendo
if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
    print_error "El contenedor $POSTGRES_CONTAINER no está corriendo"
    exit 1
fi

# Crear directorio temporal
print_info "Creando directorio temporal..."
mkdir -p "$TEMP_DIR"
mkdir -p "$OUTPUT_DIR"

# 1. Exportar SQL
print_info "Exportando base de datos SQL..."
docker exec "$POSTGRES_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" > "$TEMP_DIR/dump.sql"

if [ ! -s "$TEMP_DIR/dump.sql" ]; then
    print_error "Error: El archivo SQL está vacío"
    rm -rf "$TEMP_DIR"
    exit 1
fi

SQL_SIZE=$(du -h "$TEMP_DIR/dump.sql" | cut -f1)
print_success "SQL exportado ($SQL_SIZE)"

# 2. Obtener versión de PostgreSQL
PG_VERSION=$(docker exec "$POSTGRES_CONTAINER" psql -U "$DB_USER" -t -c "SELECT version();" | grep -oP '\d+\.\d+' | head -1)
print_info "PostgreSQL versión: $PG_VERSION"

# 3. Copiar filestore si existe
print_info "Buscando filestore..."
if docker exec "$ODOO_CONTAINER" test -d "/var/lib/odoo/filestore/$DB_NAME" 2>/dev/null; then
    print_info "Copiando filestore..."
    docker cp "$ODOO_CONTAINER:/var/lib/odoo/filestore/$DB_NAME" "$TEMP_DIR/filestore"
    FILESTORE_SIZE=$(du -sh "$TEMP_DIR/filestore" 2>/dev/null | cut -f1)
    print_success "Filestore copiado ($FILESTORE_SIZE)"
    HAS_FILESTORE=true
else
    print_warning "No se encontró filestore (esto es normal si no hay archivos adjuntos)"
    HAS_FILESTORE=false
fi

# 4. Crear manifest.json
print_info "Creando manifest.json..."
cat > "$TEMP_DIR/manifest.json" << EOF
{
    "odoo_dump": "1",
    "db_name": "$DB_NAME",
    "version": "17.0",
    "version_info": [17, 0, 0, "final", 0, ""],
    "major_version": "17.0",
    "pg_version": "$PG_VERSION",
    "modules": {}
}
EOF
print_success "manifest.json creado"

# 5. Crear archivo ZIP
print_info "Creando archivo ZIP..."
cd "$TEMP_DIR"

if [ "$HAS_FILESTORE" = true ]; then
    zip -r "$OUTPUT_DIR/${BACKUP_NAME}.zip" dump.sql manifest.json filestore
else
    zip -r "$OUTPUT_DIR/${BACKUP_NAME}.zip" dump.sql manifest.json
fi

# 6. Verificar y mostrar resultado
FINAL_PATH="$OUTPUT_DIR/${BACKUP_NAME}.zip"
if [ -f "$FINAL_PATH" ]; then
    FINAL_SIZE=$(du -h "$FINAL_PATH" | cut -f1)
    print_success "Backup creado exitosamente!"
    echo ""
    echo -e "${GREEN}=====================================================${NC}"
    echo -e "${GREEN}  BACKUP COMPLETADO${NC}"
    echo -e "${GREEN}=====================================================${NC}"
    echo ""
    echo -e "  📁 Archivo: ${BLUE}$FINAL_PATH${NC}"
    echo -e "  📊 Tamaño:  ${BLUE}$FINAL_SIZE${NC}"
    echo ""
    echo -e "  Para restaurar:"
    echo -e "  1. Ir a ${YELLOW}http://localhost:8070/web/database/manager${NC}"
    echo -e "  2. Click en 'Restore Database'"
    echo -e "  3. Seleccionar el archivo .zip"
    echo ""
else
    print_error "Error al crear el backup"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 7. Limpiar
rm -rf "$TEMP_DIR"

print_success "Proceso completado"
