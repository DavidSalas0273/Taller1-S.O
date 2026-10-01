"""
=============================================================
  TALLER — Monitor de Procesos
  Parte 2: Estresar la CPU y monitorear el reparto entre núcleos
  Concepto: Planificador de CPU (scheduler) del kernel
=============================================================
  Equivalente a:  stress-ng --cpu 4 --timeout 60s
  pero implementado en Python puro — sin dependencias externas
  más allá de psutil.

  Requiere: pip install psutil
  Ejecutar: python 2_estres_cpu.py
=============================================================
  El script lanza N workers (uno por núcleo lógico) que hacen
  cálculo intensivo de CPU, mientras un hilo monitor mide en
  tiempo real cómo el kernel reparte el trabajo entre núcleos.
=============================================================
"""

import psutil
import os
import sys
import time
import math
import threading
import multiprocessing
import datetime

# ── Configuración ───────────────────────────────────────────
DURACION_SEGUNDOS = 45      # cuánto dura el estrés
INTERVALO_REFRESCO = 1.0    # segundos entre cada snapshot del monitor
# Núcleos a estresar (None = todos los lógicos disponibles)
NUCLEOS_A_USAR = None

# ══════════════════════════════════════════════════════════
#  WORKER DE CARGA (simula stress-ng --cpu)
# ══════════════════════════════════════════════════════════

def worker_cpu(stop_event: threading.Event, worker_id: int):
    """
    Bucle de cálculo puro que mantiene un núcleo al 100%.
    Usa math.sqrt + math.sin para evitar que el compilador
    optimice y elimine el trabajo (side-effect en acumulador).
    Equivalente a lo que hace stress-ng internamente.
    """
    acumulador = 0.0
    i = 0
    while not stop_event.is_set():
        acumulador += math.sqrt(i * 1.0001) * math.sin(i)
        i += 1
        if i > 10_000_000:   # reinicia para no crecer indefinido
            i = 0
            acumulador = 0.0


# ══════════════════════════════════════════════════════════
#  MONITOR EN TIEMPO REAL
# ══════════════════════════════════════════════════════════

def barra(pct: float, ancho: int = 22) -> str:
    llenos = int((pct / 100) * ancho)
    return "[" + "█" * llenos + "░" * (ancho - llenos) + f"] {pct:5.1f}%"

def color(texto: str, pct: float) -> str:
    if pct < 50:   return f"\033[92m{texto}\033[0m"
    elif pct < 85: return f"\033[93m{texto}\033[0m"
    else:           return f"\033[91m{texto}\033[0m"

def monitor(stop_event: threading.Event, n_workers: int, duracion: int):
    """
    Hilo monitor: muestra el panel de uso de CPU por núcleo
    y estadísticas del proceso en tiempo real.
    """
    proc        = psutil.Process(os.getpid())
    inicio      = time.time()
    snapshots   = []   # historial para estadísticas finales

    # Llamada inicial para calibrar cpu_percent
    psutil.cpu_percent(percpu=True)
    time.sleep(0.5)

    while not stop_event.is_set():
        elapsed     = time.time() - inicio
        restante    = max(0, duracion - elapsed)
        nucleos_pct = psutil.cpu_percent(percpu=True)
        total_pct   = psutil.cpu_percent()
        mem         = psutil.virtual_memory()
        load_avg    = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0,0,0)

        # Estadísticas del proceso actual
        try:
            proc_cpu = proc.cpu_percent()
            proc_mem = proc.memory_info().rss / (1024**2)
            proc_hil = proc.num_threads()
        except psutil.AccessDenied:
            proc_cpu, proc_mem, proc_hil = 0.0, 0.0, 0

        snapshots.append(nucleos_pct)

        # ── Dibuja panel ──────────────────────────────────
        print("\033[H\033[J", end="")
        ahora = datetime.datetime.now().strftime("%H:%M:%S")
        print("=" * 60)
        print(f"  MONITOR DE ESTRÉS CPU — {ahora}")
        print(f"  Workers activos: {n_workers}  |  "
              f"Tiempo restante: {restante:.0f}s / {duracion}s")
        print("=" * 60)

        print(f"\n  CPU TOTAL: {color(barra(total_pct, 30), total_pct)}")
        print(f"\n  USO POR NÚCLEO (reparto del scheduler):")

        for i, pct in enumerate(nucleos_pct):
            etiqueta = f"  Núcleo {i:>2}"
            print(f"  {etiqueta}: {color(barra(pct), pct)}")

        print(f"\n  RAM sistema : {color(barra(mem.percent), mem.percent)}")
        print(f"    Usada  : {mem.used/(1024**2):.0f} MB / "
              f"{mem.total/(1024**3):.1f} GB")

        if hasattr(psutil, "getloadavg"):
            print(f"\n  Load avg (1m / 5m / 15m): "
                  f"{load_avg[0]:.2f} / {load_avg[1]:.2f} / {load_avg[2]:.2f}")

        print(f"\n  Este proceso:")
        print(f"    CPU  : {proc_cpu:.1f}%   |   RAM: {proc_mem:.1f} MB   "
              f"|   Hilos: {proc_hil}")
        print(f"    PID  : {os.getpid()}")

        print("=" * 60)
        print(f"  Carga en progreso... Ctrl+C para detener antes")

        time.sleep(INTERVALO_REFRESCO)

    return snapshots


# ══════════════════════════════════════════════════════════
#  REPORTE FINAL
# ══════════════════════════════════════════════════════════

def reporte_final(snapshots: list[list[float]], n_workers: int,
                  elapsed: float, n_nucleos: int):
    if not snapshots:
        return

    print("\n\n" + "=" * 60)
    print("  REPORTE FINAL — Análisis del Scheduler")
    print("=" * 60)
    print(f"  Duración real    : {elapsed:.1f} s")
    print(f"  Workers lanzados : {n_workers}")
    print(f"  Núcleos lógicos  : {n_nucleos}")
    print()

    # Promedio de uso por núcleo durante toda la prueba
    print("  USO PROMEDIO POR NÚCLEO:")
    promedios = []
    for i in range(n_nucleos):
        valores = [s[i] for s in snapshots if i < len(s)]
        if valores:
            prom = sum(valores) / len(valores)
            maximo = max(valores)
            promedios.append(prom)
            print(f"    Núcleo {i:>2}:  prom {prom:5.1f}%   max {maximo:5.1f}%  "
                  f"{'█' * int(prom / 5)}")

    if promedios:
        desviacion = (
            sum((x - sum(promedios)/len(promedios))**2
                for x in promedios) / len(promedios)
        ) ** 0.5
        print(f"\n  Desviación estándar entre núcleos: {desviacion:.2f}%")
        if desviacion < 10:
            print("  → El scheduler distribuyó la carga de forma EQUILIBRADA.")
        else:
            print("  → El scheduler tuvo distribución DESIGUAL entre núcleos.")

    print()
    print("  CONCLUSIÓN:")
    print("  El kernel usa Round-Robin con afinidad de núcleo para")
    print("  repartir threads entre CPUs. Con más workers que núcleos,")
    print("  el scheduler hace time-sharing dentro de cada núcleo.")
    print("=" * 60)


# ══════════════════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        import psutil  # noqa
    except ImportError:
        print("Falta psutil. Ejecuta:  pip install psutil")
        sys.exit(1)

    n_nucleos   = psutil.cpu_count(logical=True)
    n_workers   = NUCLEOS_A_USAR or n_nucleos
    stop_event  = threading.Event()

    print("=" * 60)
    print("  ESTRÉS DE CPU — Monitor de Planificador del Kernel")
    print("=" * 60)
    print(f"  Núcleos lógicos disponibles : {n_nucleos}")
    print(f"  Workers a lanzar            : {n_workers}")
    print(f"  Duración                    : {DURACION_SEGUNDOS} segundos")
    print()
    print("  Equivalente a:  stress-ng --cpu", n_workers,
          "--timeout", f"{DURACION_SEGUNDOS}s")
    print()
    print("  Iniciando en 2 segundos...")
    time.sleep(2)

    # ── Lanza workers de carga ────────────────────────────
    workers = []
    for i in range(n_workers):
        t = threading.Thread(
            target=worker_cpu,
            args=(stop_event, i),
            daemon=True,
            name=f"worker-cpu-{i}"
        )
        t.start()
        workers.append(t)

    # ── Lanza monitor en hilo separado ────────────────────
    snapshots_resultado = []

    def run_monitor():
        resultado = monitor(stop_event, n_workers, DURACION_SEGUNDOS)
        snapshots_resultado.extend(resultado)

    hilo_monitor = threading.Thread(target=run_monitor, daemon=True)
    hilo_monitor.start()

    inicio = time.time()

    try:
        # Espera la duración configurada o Ctrl+C
        time.sleep(DURACION_SEGUNDOS)
    except KeyboardInterrupt:
        print("\n\n  Detenido por el usuario.")

    elapsed = time.time() - inicio

    # ── Detiene todo ──────────────────────────────────────
    stop_event.set()
    hilo_monitor.join(timeout=3)
    for t in workers:
        t.join(timeout=2)

    reporte_final(snapshots_resultado, n_workers, elapsed, n_nucleos)
