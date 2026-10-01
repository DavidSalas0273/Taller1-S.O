"""
=============================================================
  TALLER — Monitor de Procesos (HERRAMIENTA UNIFICADA)
  Combina Parte 1 + Parte 2 en un solo panel tipo htop/top
=============================================================
  Requiere: pip install psutil
  Ejecutar: python monitor_completo.py
  Salir   : Ctrl+C
=============================================================
  Muestra en tiempo real:
    - Lista de procesos con PID, nombre, estado, CPU%, RAM
    - Uso de CPU por núcleo (barras)
    - RAM y Swap del sistema
    - Opción de activar estrés de CPU desde el mismo panel
=============================================================
"""

import psutil
import os
import sys
import time
import math
import threading
import datetime

# ── Configuración ───────────────────────────────────────────
INTERVALO        = 2.0    # segundos entre refreshes
MAX_PROCESOS     = 20     # filas de procesos a mostrar
ORDENAR_POR      = "cpu"  # "cpu" | "ram" | "pid" | "nombre"

# ── Colores ANSI ────────────────────────────────────────────
def verde(t):   return f"\033[92m{t}\033[0m"
def amarillo(t):return f"\033[93m{t}\033[0m"
def rojo(t):    return f"\033[91m{t}\033[0m"
def cyan(t):    return f"\033[96m{t}\033[0m"
def negrita(t): return f"\033[1m{t}\033[0m"

def color_nivel(texto: str, pct: float) -> str:
    if pct < 50:   return verde(texto)
    elif pct < 85: return amarillo(texto)
    else:           return rojo(texto)

def barra(pct: float, ancho: int = 20) -> str:
    llenos = int((pct / 100) * ancho)
    raw = "[" + "█" * llenos + "░" * (ancho - llenos) + f"] {pct:5.1f}%"
    return color_nivel(raw, pct)

# ── Worker de estrés (se activa con la opción --stress) ─────
_stop_stress = threading.Event()

def worker_stress():
    acumulador = 0.0
    i = 0
    while not _stop_stress.is_set():
        acumulador += math.sqrt(i * 1.0001) * math.sin(i)
        i = (i + 1) % 10_000_000

# ══════════════════════════════════════════════════════════
#  SNAPSHOT DE PROCESOS
# ══════════════════════════════════════════════════════════

def obtener_procesos() -> list[dict]:
    attrs = ["pid", "name", "status", "cpu_percent",
             "memory_info", "num_threads", "ppid"]
    # "uids" no existe en Windows — no se solicita
    resultado = []
    for proc in psutil.process_iter(attrs=attrs, ad_value=None):
        try:
            info = proc.info
            ram = (info["memory_info"].rss / (1024**2)
                   if info["memory_info"] else 0.0)
            resultado.append({
                "pid"    : info["pid"],
                "nombre" : (info["name"] or "?")[:20],
                "estado" : info["status"] or "?",
                "cpu"    : info["cpu_percent"] or 0.0,
                "ram_mb" : ram,
                "hilos"  : info["num_threads"] or 1,
                "ppid"   : info["ppid"] or 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Ordenar
    claves = {"cpu": "cpu", "ram": "ram_mb", "pid": "pid", "nombre": "nombre"}
    clave  = claves.get(ORDENAR_POR, "cpu")
    reverso = clave in ("cpu", "ram_mb")
    return sorted(resultado, key=lambda p: p[clave], reverse=reverso)


ESTADO_COLOR = {
    "running"   : verde,
    "sleeping"  : lambda t: t,
    "disk-sleep": amarillo,
    "zombie"    : rojo,
    "stopped"   : amarillo,
}

def estado_fmt(estado: str) -> str:
    abrev = {
        "running"   : "RUN",
        "sleeping"  : "SLP",
        "disk-sleep": "DSK",
        "zombie"    : "ZMB",
        "stopped"   : "STP",
        "idle"      : "IDL",
        "dead"      : "DED",
        "waiting"   : "WAT",
    }
    corto = abrev.get(estado, estado[:3].upper())
    fn    = ESTADO_COLOR.get(estado, lambda t: t)
    return fn(corto)


# ══════════════════════════════════════════════════════════
#  PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════

def panel(stress_activo: bool, n_workers: int):
    # Datos del sistema
    nucleos_pct = psutil.cpu_percent(percpu=True)
    cpu_total   = psutil.cpu_percent()
    mem         = psutil.virtual_memory()
    swap        = psutil.swap_memory()
    procesos    = obtener_procesos()
    ahora       = datetime.datetime.now().strftime("%H:%M:%S")
    n_total     = len(procesos)

    # Limpiar pantalla
    print("\033[H\033[J", end="")

    # ── Cabecera ──────────────────────────────────────────
    titulo = "MONITOR DE PROCESOS"
    if stress_activo:
        titulo += rojo(f"  [ESTRÉS ACTIVO — {n_workers} workers]")
    print(negrita(cyan(f"  ══ {titulo} ══  {ahora}")))
    print()

    # ── CPU por núcleo ────────────────────────────────────
    print(negrita("  CPU POR NÚCLEO (reparto del scheduler):"))
    cols = 2
    pares = [nucleos_pct[i:i+cols] for i in range(0, len(nucleos_pct), cols)]
    for fila_idx, fila in enumerate(pares):
        linea = ""
        for j, pct in enumerate(fila):
            idx = fila_idx * cols + j
            linea += f"  Núcleo {idx:>2}: {barra(pct, 18)}    "
        print(linea)

    print(f"\n  CPU Total : {barra(cpu_total, 30)}")

    # ── RAM y Swap ────────────────────────────────────────
    print(f"\n  RAM    : {barra(mem.percent, 30)}  "
          f"{mem.used/(1024**3):.1f}/{mem.total/(1024**3):.1f} GB")
    if swap.total > 0:
        print(f"  Swap   : {barra(swap.percent, 30)}  "
              f"{swap.used/(1024**2):.0f}/{swap.total/(1024**2):.0f} MB")

    # ── Tabla de procesos ─────────────────────────────────
    print(f"\n  {'─'*80}")
    print(negrita(f"  {'PID':>7}  {'NOMBRE':<20}  {'EST':>4}  "
                  f"{'CPU%':>6}  {'RAM MB':>8}  {'HILOS':>5}  {'PPID':>7}"))
    print(f"  {'─'*80}")

    for p in procesos[:MAX_PROCESOS]:
        cpu_str = (rojo if p["cpu"] > 80 else
                   amarillo if p["cpu"] > 40 else verde)(f"{p['cpu']:6.1f}")
        print(f"  {p['pid']:>7}  {p['nombre']:<20}  {estado_fmt(p['estado']):>4}  "
              f"{cpu_str}  {p['ram_mb']:>8.1f}  {p['hilos']:>5}  {p['ppid']:>7}")

    ocultos = n_total - MAX_PROCESOS
    if ocultos > 0:
        print(f"  {'─'*80}")
        print(f"  ... {ocultos} procesos más (ordenado por {ORDENAR_POR})")

    print(f"  {'─'*80}")
    print(f"  Total: {n_total} procesos  |  Intervalo: {INTERVALO}s  |  "
          f"Orden: {ORDENAR_POR}  |  Ctrl+C para salir")


# ══════════════════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        import psutil  # noqa
    except ImportError:
        print("Falta psutil. Ejecuta:  pip install psutil")
        sys.exit(1)

    # Argumento --stress activa workers de carga
    stress_activo = "--stress" in sys.argv
    n_nucleos     = psutil.cpu_count(logical=True) or 1
    stress_threads = []

    if stress_activo:
        print(f"  Iniciando {n_nucleos} workers de estrés de CPU...")
        for _ in range(n_nucleos):
            t = threading.Thread(target=worker_stress, daemon=True)
            t.start()
            stress_threads.append(t)
        time.sleep(1)

    # Primera llamada de calibración para cpu_percent
    psutil.cpu_percent(percpu=True)
    time.sleep(0.5)

    try:
        while True:
            panel(stress_activo, len(stress_threads))
            time.sleep(INTERVALO)
    except KeyboardInterrupt:
        _stop_stress.set()
        print("\n\n  Monitor detenido.")
        if stress_activo:
            print("  Esperando fin de workers de estrés...")
            for t in stress_threads:
                t.join(timeout=2)
        print("  Listo.")
