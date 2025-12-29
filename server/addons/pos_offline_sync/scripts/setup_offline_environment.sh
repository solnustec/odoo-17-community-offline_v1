#!/bin/bash
# =====================================================
# Script de configuración del ambiente POS Offline
# =====================================================
#
# Este script prepara todo el ambiente para ejecutar
# un Odoo 17 optimizado para POS Offline con facturación
# electrónica de Ecuador.
#
# Uso:
#   ./setup_offline_environment.sh [opciones]
#
# Opciones:
#   --build       Construir imagen Docker
#   --start       Iniciar contenedores
#   --stop        Detener contenedores
#   --minimize    Ejecutar minimización de BD
#   --backup      Crear backup de BD
#   --restore     Restaurar backup de BD
#   --help        Mostrar ayuda
#
# =====================================================

set -e

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/local-offline-optimized.yml"
COMPOSE_FILE_ORIGINAL="$PROJECT_ROOT/local-offline.yml"
DATABASE_NAME="${DATABASE_NAME:-odoo_offline}"
BACKUP_DIR="$PROJECT_ROOT/backups"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Funciones de utilidad
print_header() {
    echo -e "${BLUE}"
    echo "======================================================================"
    echo " $1"
    echo "======================================================================"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

show_help() {
    cat << EOF
Uso: $0 [comando]

Comandos:
    build           Construir imagen Docker optimizada
    start           Iniciar contenedores
    stop            Detener contenedores
    restart         Reiniciar contenedores
    logs            Ver logs en tiempo real
    shell           Abrir shell de Odoo
    minimize        Ejecutar minimización de base de datos
    backup          Crear backup de la base de datos
    restore FILE    Restaurar backup desde archivo
    status          Ver estado de contenedores
    clean           Limpiar contenedores y volúmenes
    help            Mostrar esta ayuda

Ejemplos:
    $0 build        # Construir imagen
    $0 start        # Iniciar servicios
    $0 minimize     # Minimizar base de datos
    $0 backup       # Crear backup
    $0 restore backup_2024.sql  # Restaurar

Variables de entorno:
    DATABASE_NAME   Nombre de la base de datos (default: odoo_offline)
    BACKUP_DIR      Directorio para backups (default: ./backups)

EOF
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker no está instalado"
        exit 1
    fi
    if ! docker info &> /dev/null; then
        print_error "Docker no está corriendo"
        exit 1
    fi
}

check_compose_file() {
    if [ -f "$COMPOSE_FILE" ]; then
        print_info "Usando archivo optimizado: $COMPOSE_FILE"
    elif [ -f "$COMPOSE_FILE_ORIGINAL" ]; then
        print_warning "Archivo optimizado no encontrado, usando original"
        COMPOSE_FILE="$COMPOSE_FILE_ORIGINAL"
    else
        print_error "No se encontró archivo docker-compose"
        exit 1
    fi
}

# Comandos principales
cmd_build() {
    print_header "CONSTRUYENDO IMAGEN DOCKER OPTIMIZADA"
    check_docker
    check_compose_file

    print_info "Construyendo imagen..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache

    print_success "Imagen construida correctamente"
}

cmd_start() {
    print_header "INICIANDO SERVICIOS POS OFFLINE"
    check_docker
    check_compose_file

    print_info "Iniciando base de datos..."
    docker-compose -f "$COMPOSE_FILE" up -d db-offline

    print_info "Esperando que PostgreSQL esté listo..."
    sleep 10

    print_info "Iniciando Odoo..."
    docker-compose -f "$COMPOSE_FILE" up -d app-offline

    print_info "Esperando que Odoo inicie..."
    sleep 30

    print_success "Servicios iniciados"
    print_info "Acceder a: http://localhost:8070"
}

cmd_stop() {
    print_header "DETENIENDO SERVICIOS"
    check_docker

    docker-compose -f "$COMPOSE_FILE" down

    print_success "Servicios detenidos"
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_logs() {
    print_header "LOGS EN TIEMPO REAL"
    docker-compose -f "$COMPOSE_FILE" logs -f
}

cmd_shell() {
    print_header "ABRIENDO SHELL DE ODOO"

    docker-compose -f "$COMPOSE_FILE" exec app-offline \
        odoo shell -d "$DATABASE_NAME"
}

cmd_minimize() {
    print_header "MINIMIZACIÓN DE BASE DE DATOS"

    print_warning "Este proceso eliminará módulos no esenciales"
    print_warning "Asegúrese de tener un backup antes de continuar"
    echo ""
    read -p "¿Desea crear un backup ahora? (s/n): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Ss]$ ]]; then
        cmd_backup
    fi

    echo ""
    read -p "¿Continuar con la minimización? (s/n): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        print_info "Operación cancelada"
        exit 0
    fi

    print_info "Ejecutando análisis..."

    # Copiar script al contenedor y ejecutar
    docker cp "$SCRIPT_DIR/minimize_database.py" odoo-offline:/tmp/

    docker-compose -f "$COMPOSE_FILE" exec app-offline \
        odoo shell -d "$DATABASE_NAME" << 'EOFSHELL'
exec(open('/tmp/minimize_database.py').read())
analyze_database(env)
print("\n¿Ejecutar minimización? Presione Ctrl+C para cancelar...")
import time
time.sleep(10)
run_minimization(env, dry_run=False)
EOFSHELL

    print_success "Minimización completada"
    print_info "Reiniciando servicios..."
    cmd_restart
}

cmd_backup() {
    print_header "CREANDO BACKUP"

    mkdir -p "$BACKUP_DIR"

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/${DATABASE_NAME}_${TIMESTAMP}.sql"

    print_info "Creando backup en: $BACKUP_FILE"

    docker-compose -f "$COMPOSE_FILE" exec -T db-offline \
        pg_dump -U odoo "$DATABASE_NAME" > "$BACKUP_FILE"

    # Comprimir
    gzip "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"

    print_success "Backup creado: $BACKUP_FILE"

    # Mostrar tamaño
    ls -lh "$BACKUP_FILE"
}

cmd_restore() {
    if [ -z "$1" ]; then
        print_error "Debe especificar el archivo de backup"
        echo "Uso: $0 restore <archivo.sql.gz>"
        exit 1
    fi

    BACKUP_FILE="$1"

    if [ ! -f "$BACKUP_FILE" ]; then
        print_error "Archivo no encontrado: $BACKUP_FILE"
        exit 1
    fi

    print_header "RESTAURANDO BACKUP"
    print_warning "Esto eliminará todos los datos actuales de la base de datos"

    read -p "¿Está seguro de continuar? (s/n): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        print_info "Operación cancelada"
        exit 0
    fi

    print_info "Deteniendo Odoo..."
    docker-compose -f "$COMPOSE_FILE" stop app-offline

    print_info "Restaurando base de datos..."

    # Recrear base de datos
    docker-compose -f "$COMPOSE_FILE" exec -T db-offline \
        psql -U odoo -c "DROP DATABASE IF EXISTS $DATABASE_NAME;"
    docker-compose -f "$COMPOSE_FILE" exec -T db-offline \
        psql -U odoo -c "CREATE DATABASE $DATABASE_NAME;"

    # Restaurar
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        gunzip -c "$BACKUP_FILE" | docker-compose -f "$COMPOSE_FILE" exec -T db-offline \
            psql -U odoo "$DATABASE_NAME"
    else
        docker-compose -f "$COMPOSE_FILE" exec -T db-offline \
            psql -U odoo "$DATABASE_NAME" < "$BACKUP_FILE"
    fi

    print_info "Iniciando Odoo..."
    docker-compose -f "$COMPOSE_FILE" start app-offline

    print_success "Restauración completada"
}

cmd_status() {
    print_header "ESTADO DE SERVICIOS"

    docker-compose -f "$COMPOSE_FILE" ps
    echo ""

    print_info "Uso de recursos:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        postgres-offline odoo-offline 2>/dev/null || true
}

cmd_clean() {
    print_header "LIMPIEZA DE CONTENEDORES Y VOLÚMENES"
    print_warning "Esto eliminará todos los datos!"

    read -p "¿Está seguro? (escriba 'SI' para confirmar): " -r
    echo ""

    if [ "$REPLY" != "SI" ]; then
        print_info "Operación cancelada"
        exit 0
    fi

    docker-compose -f "$COMPOSE_FILE" down -v --remove-orphans

    print_success "Limpieza completada"
}

# =====================================================
# MAIN
# =====================================================

case "${1:-help}" in
    build)
        cmd_build
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    shell)
        cmd_shell
        ;;
    minimize)
        cmd_minimize
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore "$2"
        ;;
    status)
        cmd_status
        ;;
    clean)
        cmd_clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Comando desconocido: $1"
        show_help
        exit 1
        ;;
esac
