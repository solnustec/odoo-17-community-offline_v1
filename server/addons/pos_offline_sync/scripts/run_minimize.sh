#!/bin/bash
# =============================================================================
# Script para minimizar base de datos Odoo para POS Offline
# =============================================================================
#
# Uso:
#   ./run_minimize.sh <database_name> [--execute]
#
# Opciones:
#   --execute    Ejecutar la desinstalación (sin esto solo analiza)
#
# Ejemplo:
#   ./run_minimize.sh odoo_offline            # Solo analiza
#   ./run_minimize.sh odoo_offline --execute  # Ejecuta desinstalación
#
# =============================================================================

set -e

# Configuración
ODOO_BIN="${ODOO_BIN:-/home/user/odoo-17-community/odoo-bin}"
ADDONS_PATH="${ADDONS_PATH:-/home/user/odoo-17-community/addons}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funciones
print_header() {
    echo -e "${BLUE}"
    echo "======================================================================"
    echo " MINIMIZACIÓN DE BASE DE DATOS ODOO PARA POS OFFLINE"
    echo "======================================================================"
    echo -e "${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

show_usage() {
    echo "Uso: $0 <database_name> [--execute]"
    echo ""
    echo "Opciones:"
    echo "  --execute    Ejecutar la desinstalación (sin esto solo analiza)"
    echo ""
    echo "Ejemplo:"
    echo "  $0 odoo_offline            # Solo analiza"
    echo "  $0 odoo_offline --execute  # Ejecuta desinstalación"
    exit 1
}

# Verificar argumentos
if [ -z "$1" ]; then
    show_usage
fi

DATABASE="$1"
EXECUTE_MODE=false

if [ "$2" == "--execute" ]; then
    EXECUTE_MODE=true
fi

print_header

echo -e "Base de datos: ${BLUE}$DATABASE${NC}"
echo -e "Modo: ${YELLOW}$([ "$EXECUTE_MODE" == true ] && echo 'EJECUTAR' || echo 'ANÁLISIS')${NC}"
echo ""

# Verificar que exista el script Python
if [ ! -f "$SCRIPT_DIR/minimize_database.py" ]; then
    print_error "No se encontró minimize_database.py en $SCRIPT_DIR"
    exit 1
fi

# Crear script temporal para ejecutar en shell
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'EOFPYTHON'
import sys
sys.path.insert(0, '__SCRIPT_DIR__')
exec(open('__SCRIPT_DIR__/minimize_database.py').read())

# Ejecutar análisis o minimización
if '__EXECUTE_MODE__' == 'true':
    print("\n⚠️  MODO EJECUCIÓN - Los cambios son permanentes")
    print("Presione Ctrl+C en los próximos 5 segundos para cancelar...")
    import time
    time.sleep(5)
    run_minimization(env, dry_run=False)
else:
    analyze_database(env)
    print("\n💡 Para ejecutar la desinstalación, use: run_minimize.sh {} --execute".format('__DATABASE__'))
EOFPYTHON

# Reemplazar placeholders
sed -i "s|__SCRIPT_DIR__|$SCRIPT_DIR|g" "$TEMP_SCRIPT"
sed -i "s|__EXECUTE_MODE__|$EXECUTE_MODE|g" "$TEMP_SCRIPT"
sed -i "s|__DATABASE__|$DATABASE|g" "$TEMP_SCRIPT"

# Ejecutar en shell de Odoo
print_warning "Ejecutando análisis en base de datos $DATABASE..."
echo ""

python3 "$ODOO_BIN" shell -d "$DATABASE" --addons-path="$ADDONS_PATH" < "$TEMP_SCRIPT"

# Limpiar
rm -f "$TEMP_SCRIPT"

echo ""
print_success "Proceso completado"
