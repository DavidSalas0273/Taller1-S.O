# Taller — Monitor de Procesos

> Del listado de procesos a la observación real del planificador de CPU

En este taller se construye desde cero una pequeña herramienta de monitoreo similar en espíritu a `top` o `htop`, leyendo directamente las fuentes de información que expone el kernel. El objetivo no es solo listar procesos, sino entender de dónde sale esa información y cómo el planificador de CPU reparte el trabajo entre los núcleos disponibles — sometiendo después al sistema a una carga real para observar ese reparto en acción.

**Requisito único:** `pip install psutil`

---

##  Estructura del proyecto

```
MonitorProcesos/
├── 1_listar_procesos.py    → Parte 1: listar procesos activos y su PID
├── 2_estres_cpu.py         → Parte 2: estresar la CPU y monitorear núcleos
├── monitor_completo.py     → Herramienta unificada tipo htop
└── README.md
```

---

## Parte 1 — Listar los procesos activos y su PID

### ¿Qué hace?

Lee todos los procesos activos del sistema mostrando al menos:
- PID del proceso
- Nombre del proceso
- Estado (Ejecutando, Durmiendo, Espera E/S, Zombie, etc.)
- Número de hilos, RAM consumida (MB) y tiempo de CPU acumulado

**En Linux** lee directamente el filesystem del kernel `/proc/<pid>/status` y `/proc/<pid>/stat`, exactamente como lo hace `top` o `htop`. Equivale a ejecutar:

```bash
cat /proc/<pid>/status | head -5
```

**En Windows** usa psutil, que consulta las mismas APIs internas del kernel NT (`NtQuerySystemInformation`), obteniendo información equivalente.

### Cómo ejecutarlo

```bash
python 1_listar_procesos.py
```

### Resultado de prueba (Windows — 281 procesos detectados)

```
========================================================================================
  LISTADO DE PROCESOS — 2026-09-30 22:10:24   |   Fuente: psutil → kernel NT
  Total procesos: 281   (mostrando primeros 40 por PID)
========================================================================================
      PID  NOMBRE                  ESTADO                  HILOS    RAM MB   CPU seg   UID
----------------------------------------------------------------------------------------
        0  System Idle Process     Ejecutando                 36       0.0  1043134.84  N/A
        4  System                  Ejecutando                407       8.3     7001.22  N/A
      188  ?                       Detenido                    1      66.0        0.00  N/A
      232  Registry                Ejecutando                  4      37.4        3.06  N/A
      868  smss.exe                Ejecutando                  2       1.5        0.22  N/A
     1224  csrss.exe               Ejecutando                 15       6.6        7.38  N/A
     1228  dwm.exe                 Ejecutando                 28     245.3     1454.31  N/A
     1332  wininit.exe             Ejecutando                  2       9.0        0.09  N/A
     1364  python3.11.exe          Ejecutando                  2      29.4        0.31  N/A
     1404  services.exe            Ejecutando                  7      20.4       77.00  N/A
     1520  brave.exe               Ejecutando                 54     591.8      373.86  N/A
     2512  steam.exe               Ejecutando                 56     338.2       88.27  N/A
  ... y 241 procesos más
========================================================================================

  RESUMEN DE ESTADOS:
    Ejecutando                  277  ████████████████████████████████████████
    Detenido                      4  ████

  RAM total (todos los procesos): 15,709.9 MB
  CPU acumulado (todos):       1,061,778.5 seg
========================================================================================
```

### Qué observar

- El **System Idle Process** (PID 0) tiene el mayor CPU acumulado — es el proceso que corre cuando ningún otro necesita el núcleo.
- `brave.exe` y `steam.exe` tienen 54 y 56 hilos respectivamente — cada hilo puede ser planificado en un núcleo distinto.
- Los procesos en estado **Detenido** existen pero no consumen CPU — el kernel los ignora en el scheduling.

---

## Parte 2 — Estresar la CPU y monitorear el reparto entre núcleos

### ¿Qué hace?

Lanza **N workers** (uno por núcleo lógico disponible) que realizan cálculo matemático intensivo en bucle, mientras un hilo monitor muestra en tiempo real cómo el kernel reparte el trabajo entre núcleos.

Equivalente a:
```bash
# Linux con stress-ng
sudo apt install -y stress-ng
stress-ng --cpu 4 --timeout 60s

# O con procesos simples en varias terminales
yes > /dev/null &
```

La diferencia es que aquí el monitor y los workers están integrados, y se genera un reporte final con la distribución estadística entre núcleos.

### Cómo ejecutarlo

```bash
python 2_estres_cpu.py
# Presiona Ctrl+C para detener antes
```

### Resultado de prueba

**Durante el estrés (panel en tiempo real):**
```
============================================================
  MONITOR DE ESTRÉS CPU — 22:15:33
  Workers activos: 12  |  Tiempo restante: 31s / 45s
============================================================

  CPU TOTAL: [██████████████████████████░░░░] 87.4%

  USO POR NÚCLEO (reparto del scheduler):
  Núcleo  0: [████████████████████░░] 91.2%
  Núcleo  1: [███████████████████░░░] 88.7%
  Núcleo  2: [████████████████████░░] 90.1%
  Núcleo  3: [██████████████████░░░░] 84.3%
  Núcleo  4: [███████████████████░░░] 87.9%
  Núcleo  5: [████████████████████░░] 90.5%
  ...

  RAM    : [████████░░░░░░░░░░░░░░] 42.3%  6.7/15.8 GB
  Swap   : [░░░░░░░░░░░░░░░░░░░░░░]  0.0%  0/16.4 GB

  Este proceso:
    CPU  : 843.2%   |   RAM: 48.3 MB   |   Hilos: 14
    PID  : 22104
```

**Reporte final:**
```
============================================================
  REPORTE FINAL — Análisis del Scheduler
============================================================
  Duración real    : 45.0 s
  Workers lanzados : 12
  Núcleos lógicos  : 12

  USO PROMEDIO POR NÚCLEO:
    Núcleo  0:  prom  89.3%   max  97.1%  █████████████████
    Núcleo  1:  prom  87.8%   max  96.4%  █████████████████
    Núcleo  2:  prom  91.2%   max  98.0%  ██████████████████
    Núcleo  3:  prom  86.5%   max  95.8%  █████████████████
    ...

  Desviación estándar entre núcleos: 2.14%
  → El scheduler distribuyó la carga de forma EQUILIBRADA.

  CONCLUSIÓN:
  El kernel usa Round-Robin con afinidad de núcleo para
  repartir threads entre CPUs. Con más workers que núcleos,
  el scheduler hace time-sharing dentro de cada núcleo.
============================================================
```

### Qué observar

- Con exactamente **N workers = N núcleos**, cada núcleo queda casi al 100%.
- La **desviación estándar baja** (< 5%) confirma que el scheduler de Linux/Windows distribuye la carga de forma equitativa — no hay núcleo "favorito".
- El campo **CPU del proceso** puede superar 100% (ej. 843%) porque suma el porcentaje de todos los núcleos usados.

---

## Herramienta unificada — Monitor tipo htop

Combina el listado de procesos y el monitor de núcleos en un panel único, con actualización cada 2 segundos.

```bash
# Solo monitorear
python monitor_completo.py

# Monitorear + activar estrés de CPU simultáneamente
python monitor_completo.py --stress
```

**Vista del panel:**
```
══ MONITOR DE PROCESOS ══  22:18:45

  CPU POR NÚCLEO (reparto del scheduler):
  Núcleo  0: [████████████░░░░░░░░]  54.2%    Núcleo  1: [██████░░░░░░░░░░░░░░]  28.1%
  Núcleo  2: [█████████████░░░░░░░]  61.3%    Núcleo  3: [████████░░░░░░░░░░░░]  37.4%

  CPU Total : [████████████░░░░░░░░░░░░░░░░░░]  45.3%
  RAM       : [█████████░░░░░░░░░░░░░░░░░░░░░]  42.1%  6.7/15.8 GB

  ────────────────────────────────────────────────────────────
    PID  NOMBRE                EST    CPU%    RAM MB  HILOS    PPID
  ────────────────────────────────────────────────────────────
   1520  brave.exe             RUN    12.3     591.8     54    1484
   2512  steam.exe             RUN     4.1     338.2     56    1404
   1228  dwm.exe               RUN     2.8     245.3     28    1332
  22104  python.exe            RUN     1.9      49.1     14   22080
  ...
```

---

## Resumen de conceptos cubiertos

| Script | Concepto SO | Resultado clave |
|---|---|---|
| `1_listar_procesos.py` | Filesystem `/proc` del kernel | 281 procesos, lectura directa de metadatos del SO |
| `2_estres_cpu.py` | Scheduler Round-Robin con afinidad | Desviación ±2.1% entre núcleos — reparto equitativo |
| `monitor_completo.py` | Vista integrada tipo htop | Panel tiempo real con procesos + núcleos + estrés |

---

## Instalación rápida

```bash
git clone https://github.com/DavidSalas0273/Sistemas-Operativos-taller.git
cd Sistemas-Operativos-taller/MonitorProcesos
pip install psutil
python 1_listar_procesos.py
python 2_estres_cpu.py
```

> **Nota:** En Linux los scripts leen `/proc` directamente. En Windows usan psutil que accede a las mismas APIs internas del kernel NT.
