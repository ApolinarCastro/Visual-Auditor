# MRI_AND_VA_PHYSICAL_SEPARATION_054_REPORT

**Tarea:** MRI-AND-VA-PHYSICAL-SEPARATION-054 · **Fecha:** 2026-11-12
**Resultado:** MRI quedó en `C:\Users\ASUS Zenbook\Documents\MRI`, funcional y separado del VA.
Los históricos de VA se movieron al respaldo fechado. **No se borró ningún archivo.**

---

## 1. Pesos finales

| Carpeta | Peso |
|---|---:|
| **MRI** (`C:\Users\ASUS Zenbook\Documents\MRI`) | **5.16 GB** |
| **Respaldo VA** (`Visibility Auditor - respaldo 21-09-2026`) | **7.22 GB** |
| Peso original declarado | 10.30 GB |

El objetivo de ~2 GB **no es alcanzable sin mover componentes funcionales**:
`_integration` 2.18 GB, perfiles de navegador ML/Ripley 1.59 GB, base operativa 293 MB,
entorno Python 0.44 GB y Excel de temporada 0.27 GB. Todos son necesarios para adquirir y auditar.

## 2. Movido al respaldo

Destino:

```text
C:\Users\ASUS Zenbook\Documents\Visibility Auditor - respaldo 21-09-2026\historic_20261111\
```

| Elemento movido | Peso aproximado |
|---|---:|
| `evidence/` | 3.317 GB |
| `experiments/` | 1.275 GB |
| `outputs/` | 0.133 GB |
| `logs/` | < 1 MB |
| `data/sqlite/visibility.db` (histórica) | 0.117 GB |
| Backups SQLite (`visibility_backup_*.db`, fixtures, `.bak`, wal/shm) | ~0.38 GB |

**No se movió:**

```text
data/sqlite/mri_operational/     ← base operativa MRI
_integration/                    ← motor actual
data/mercado_libre_profile/      ← perfil funcional ML
data/ripley_profile/             ← perfil funcional Ripley
visibility_auditor_env/          ← entorno Python necesario
Chek List/                       ← Excel de temporada
```

El respaldo ya contenía el VA original del 21-09-2026; los históricos nuevos se guardaron en
`historic_20261111` para no sobrescribir nada.

## 3. Renombrado de la carpeta principal

```text
Antes: C:\Users\ASUS Zenbook\Documents\Visibility Auditor
Ahora: C:\Users\ASUS Zenbook\Documents\MRI
```

El renombrado directo fue bloqueado por un handle de Windows. Se hizo la separación moviendo los
325 elementos a `MRI`. Quedó un residuo bloqueado:

```text
C:\Users\ASUS Zenbook\Documents\Visibility Auditor - residual locked\
  Analisis_Tecnologias_Emergentes_29Ago2026.docx   (23 KB)
```

Ese archivo no se pudo copiar/mover por ACL/bloqueo; **no se borró**.

## 4. Dashboard MRI en la nueva ruta

Validación final 2026-11-12:

```text
Launcher: C:\Users\ASUS Zenbook\Documents\MRI\lanzar_mri_dashboard.bat
ready=True
running=False
build=7e9d88064f62-dirty
branch=integration/mri-deepseek-closure
sections A-H=8
Puerto 8055 respondió
```

Base operativa:

```text
C:\Users\ASUS Zenbook\Documents\MRI\data\sqlite\mri_operational\visibility.db
exists=True
```

El dashboard se cerró tras validar; puerto 8055 libre.

## 5. Rutas en scripts y configuración

- `lanzar_mri_dashboard.bat` y `_integration\lanzar_mri_dashboard.bat` usan `%~dp0`:
  **no contenían la ruta absoluta antigua** y funcionan desde MRI.
- `.env` raíz y `_integration\.env` solo contienen usuario/clave; sin rutas absolutas.
- Se corrigieron los punteros Git del worktree:
  - `_integration\.git` → `MRI/.git/worktrees/_integration`
  - `.git/worktrees/_integration/gitdir` → `MRI/_integration/.git`
- No quedan referencias a la ruta antigua en `.bat` ni `.ps1`.

## 6. Integridad

```text
archivos borrados             = 0
base operativa MRI            = intacta
motor _integration            = intacto
perfiles de adquisición       = intactos
VA histórico                  = respaldado
VA original 21-09-2026        = respaldado
dashboard MRI                 = verificado en MRI
git branch en MRI             = detectado correctamente
```

## 7. Conclusión

| Objetivo | Estado |
|---|---|
| Separación física MRI/VA | **SÍ** |
| MRI en carpeta nueva | **SÍ** (`Documents\MRI`) |
| Históricos VA respaldados | **SÍ** (`historic_20261111`) |
| Nada borrado | **SÍ** |
| Dashboard MRI operativo | **SÍ** |
| Rutas de scripts actualizadas | **SÍ** (relativas; punteros Git corregidos) |
| Peso MRI < 10.30 GB | **SÍ** (5.16 GB) |
| Peso MRI ~2 GB | **NO** por componentes funcionales |
| Criterio de cierre | **PARCIAL**: separación/funcionamiento OK; mínimo real 5.16 GB |

## 8. Estado

```text
MRI_PATH=C:\Users\ASUS Zenbook\Documents\MRI
MRI_GB=5.16
VA_BACKUP=C:\Users\ASUS Zenbook\Documents\Visibility Auditor - respaldo 21-09-2026
VA_BACKUP_GB=7.22
VA_HISTORIC=historic_20261111
OLD_RESIDUAL=Visibility Auditor - residual locked (1 docx bloqueado)
DASHBOARD=STOPPED (validado en MRI)
PORT_8055=FREE
```
