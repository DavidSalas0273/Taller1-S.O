"""
=============================================================
  TALLER — Monitor de Procesos
  Parte 1: Listar procesos activos y su PID
  Concepto: El planificador del kernel y el sistema /proc
=============================================================
  En Linux: lee directamente /proc/<pid>/status  (como el taller pide)
  En Windows: usa psutil que consulta las mismas APIs del kernel NT

  Requiere: pip install psutil
  Ejecutar: python 1_listar_procesos.py
=============================================================
"""

import os
import sys
import psutil
import time
import datetime

# ── Mapa de estados del proceso (código kernel → legible) ──
ESTADOS = {
    # Letras de /proc/<pid>/stat  (Linux)
    "R": "Ejecutando  (Running)",
    "S": "Durmiendo   (Sleeping)",
    "D": "Espera E/S  (Disk wait)",
    "Z": "Zombie",
    "T": "Detenido    (Stopped)",
    "t": "Traza/Debug",
    "X": "Muerto      (Dead)",
    "I": "Idle (kernel thread)",
    # Strings de psutil (Windows/Mac/Linux)
    "running"   : "Ejecutando",
    "sleeping"  : "Durmiendo",
    "disk-sleep": "Espera E/S",
    "stopped"   : "Detenido",
    "zombie"    : "Zombie",
    "dead"      : "Muerto",
    "idle"      : "Idle",
    "locked"    : "Bloqueado",
    "waiting"   : "En espera",
}

# ══════════════════════════════════════════════════════════
#  LECTOR DE /proc  (Linux — fuente directa del kernel)
# ══════════════════════════════════════════════════════════

def leer_proc_status(pid: int) -> dict | None:
    """
    Lee /proc/<pid>/status exactamente como hace top o htop.
    Equivalente a: cat /proc/<pid>/status | head -5
    """
    ruta = f"/proc/{pid}/status"
    try:
        with open(ruta, "r") as f:
            lineas = f.readlines()
    except (FileNotFoundError, PermissionError):
        return None

    datos = {}
    for linea in lineas:
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            datos[clave.strip()] = valor.strip()
    return datos


def leer_proc_stat(pid: int) -> list | None:
    """
    Lee /proc/<pid>/stat — contiene el estado (una letra) y
    tiempo de CPU en jiffies (utime + stime).
    """
    ruta = f"/proc/{pid}/stat"
    try:
        with open(ruta, "r") as f:
            contenido = f.read()
        # El nombre del proceso puede tener espacios y va entre paréntesis
        inicio = contenido.rfind(")")
        campos = contenido[inicio + 2:].split()
        return campos
    except (FileNotFoundError, PermissionError):
        return None


def procesos_desde_proc() -> list[dict]:
    """
    Enumera todos los procesos leyendo /proc directamente.
    Equivalente a: ls /proc | grep '^[0-9]'
    """
    procesos = []
    try:
        entradas = os.listdir("/proc")
    except PermissionError:
        return []

    for entrada in entradas:
        if not entrada.isdigit():
            continue
        pid = int(entrada)
        status = leer_proc_status(pid)
        if status is None:
            continue

        stat = leer_proc_stat(pid)
        estado_letra = stat[0] if stat else "?"

        # CPU time: jiffies → segundos (HZ=100 en la mayoría de kernels)
        try:
            utime  = int(stat[11]) if stat and len(stat) > 11 else 0
            stime  = int(stat[12]) if stat and len(stat) > 12 else 0
            cpu_seg = (utime + stime) / 100.0
        except (ValueError, IndexError):
            cpu_seg = 0.0

        # RAM RSS desde VmRSS en /proc/<pid>/status  (en kB)
        try:
            vmrss_kb = int(status.get("VmRSS", "0 kB").split()[0])
        except ValueError:
            vmrss_kb = 0

        procesos.append({
            "pid"    : pid,
            "nombre" : status.get("Name", "?"),
            "estado" : estado_letra,
            "hilos"  : int(status.get("Threads", "1")),
            "uid"    : status.get("Uid", "?").split()[0],
            "ram_mb" : vmrss_kb / 1024,
            "cpu_seg": cpu_seg,
        })

    return sorted(procesos, key=lambda p: p["pid"])


# ══════════════════════════════════════════════════════════
#  LECTOR MULTIPLATAFORMA con psutil  (Windows / Mac / Linux)
# ══════════════════════════════════════════════════════════

def procesos_desde_psutil() -> list[dict]:
    """
    Usa psutil para obtener la misma información de forma portable.
    En Linux, psutil también lee /proc internamente.
    """
    procesos = []
    # "uids" solo existe en Unix; en Windows se omite
    attrs_base = ["pid", "name", "status", "num_threads", "memory_info", "cpu_times"]
    tiene_uids = not sys.platform.startswith("win")
    attrs = attrs_base + (["uids"] if tiene_uids else [])

    for proc in psutil.process_iter(attrs=attrs, ad_value=None):
        try:
            info = proc.info
            ram_mb = (
                info["memory_info"].rss / (1024 ** 2)
                if info["memory_info"] else 0.0
            )
            cpu_seg = (
                info["cpu_times"].user + info["cpu_times"].system
                if info["cpu_times"] else 0.0
            )
            uid = str(info["uids"].real) if tiene_uids and info.get("uids") else "N/A"
            procesos.append({
                "pid"    : info["pid"],
                "nombre" : info["name"] or "?",
                "estado" : info["status"] or "?",
                "hilos"  : info["num_threads"] or 1,
                "uid"    : uid,
                "ram_mb" : ram_mb,
                "cpu_seg": cpu_seg,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return sorted(procesos, key=lambda p: p["pid"])


# ══════════════════════════════════════════════════════════
#  VISUALIZACIÓN
# ══════════════════════════════════════════════════════════

def estado_legible(estado: str) -> str:
    return ESTADOS.get(estado, estado)


def imprimir_tabla(procesos: list[dict], fuente: str, limite: int = 40):
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(procesos)

    print("=" * 88)
    print(f"  LISTADO DE PROCESOS — {ahora}   |   Fuente: {fuente}")
    print(f"  Total procesos: {total}   (mostrando primeros {min(limite, total)} por PID)")
    print("=" * 88)
    print(f"  {'PID':>7}  {'NOMBRE':<22}  {'ESTADO':<22}  {'HILOS':>5}  "
          f"{'RAM MB':>8}  {'CPU seg':>8}  {'UID':>6}")
    print("-" * 88)

    for p in procesos[:limite]:
        est = estado_legible(p["estado"])
        print(f"  {p['pid']:>7}  {p['nombre']:<22.22}  {est:<22.22}  "
              f"{p['hilos']:>5}  {p['ram_mb']:>8.1f}  {p['cpu_seg']:>8.2f}  "
              f"{p['uid']:>6}")

    if total > limite:
        print(f"  ... y {total - limite} procesos más")
    print("=" * 88)

    # Resumen de estados
    estados_count: dict[str, int] = {}
    for p in procesos:
        e = estado_legible(p["estado"])
        estados_count[e] = estados_count.get(e, 0) + 1

    print("\n  RESUMEN DE ESTADOS:")
    for estado, cuenta in sorted(estados_count.items(), key=lambda x: -x[1]):
        barra = "█" * min(cuenta, 40)
        print(f"    {estado:<25} {cuenta:>5}  {barra}")

    ram_total = sum(p["ram_mb"] for p in procesos)
    cpu_total = sum(p["cpu_seg"] for p in procesos)
    print(f"\n  RAM total (todos los procesos): {ram_total:.1f} MB")
    print(f"  CPU acumulado (todos):          {cpu_total:.1f} seg")
    print("=" * 88)


# ══════════════════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        import psutil  # noqa
    except ImportError:
        print("Falta psutil. Ejecuta:  pip install psutil")
        sys.exit(1)

    es_linux = sys.platform.startswith("linux")

    if es_linux:
        print("\n  Sistema Linux detectado — leyendo /proc directamente\n")
        procesos = procesos_desde_proc()
        fuente   = "/proc/<pid>/status  (kernel filesystem)"

        # Demo exacta del taller: cat /proc/<pid>/status | head -5
        if procesos:
            pid_demo = procesos[0]["pid"]
            print(f"  >> cat /proc/{pid_demo}/status | head -5")
            print("  " + "-" * 45)
            status_raw = leer_proc_status(pid_demo)
            if status_raw:
                for i, (k, v) in enumerate(status_raw.items()):
                    if i >= 5:
                        break
                    print(f"  {k}: {v}")
            print()
    else:
        print(f"\n  Sistema {sys.platform} detectado.")
        print("  Nota: en Linux este script lee /proc directamente.")
        print("  En Windows usa psutil (mismas APIs del kernel NT).\n")
        procesos = procesos_desde_psutil()
        fuente   = "psutil → kernel NT (equivalente a /proc en Linux)"

    imprimir_tabla(procesos, fuente)
