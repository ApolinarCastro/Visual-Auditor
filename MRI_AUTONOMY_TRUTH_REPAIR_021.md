# MRI_AUTONOMY_TRUTH_REPAIR_021

**Ejecutor:** ANTIGRAVITY  
**Auditor asignado para revisión independiente:** CODEX  
**Rama:** `feature/mri-autonomy-truth-repair-021`  
**Base:** `feature/mri-autonomous-operation-019` (`5327ffb4562e48bb14daa3a0ccadaef28e4ec02d`)  
**Fuente de verdad de defectos:** `MRI_CODEX_AUTONOMOUS_AUDIT_020.md`  
**Fecha de ejecución:** 2026-10-16

---

## 1. RESUMEN EJECUTIVO Y DICTAMEN PREVIO

En cumplimiento estricto del mandato **MRI-AUTONOMY-TRUTH-REPAIR-021**, se subsanaron integralmente los cuatro defectos materiales señalados por el Auditor CODEX en `MRI_CODEX_AUTONOMOUS_AUDIT_020.md`:

1. **Eliminación total de resultados sintéticos de producción:** Se desmanteló por completo la generación de SKUs artificiales (`RIP_{hash}`, `MLCMLC...`), precios ficticios ($24.990 / $29.990) y vendedores simulados. Los adaptadores rechazan todo ítem sin SKU verificable y exigen observación real (`LIVE_OBSERVATION`) o replay íntegro con SHA-256 (`CONTROLLED_REPLAY`).
2. **Cierre inviolable de la barrera SQLite:** Se incorporó `StorageConfig.assert_write_allowed(self.db_path)` en el constructor de `AutonomousMultiMarketplaceRunner` y en `_init_sqlite_tables()`, impidiendo que cualquier intento de conexión alcance bases de datos productivas.
3. **Dinamización completa de API y Dashboard:** El endpoint `/api/multimarketplace/summary` y la vista `index.html` ya no devuelven constantes ni badges estáticos de éxito. Consultan dinámicamente la base de datos para el `run_id` activo, agregando recuentos y estados fieles (`OPERATIONAL`, `PARTIAL`, `BLOCKED`, `AUTH_REQUIRED`).
4. **Trazabilidad y procedencia primaria en los 4 marketplaces:**
   - **Paris:** Diferenciación transparente entre consulta en vivo a la API Constructor.io y replay HAR que consume efectivamente el payload capturado.
   - **Falabella:** Extracción SSR asociada a su URL primaria, timestamp de captura y SHA-256 del contenido (`source_file_sha256`).
   - **Ripley:** Intentos reales mediante scraper headless y extracción de facetas. Si la adquisición de publicaciones no obtiene productos reales, se registra honestamente cobertura parcial (`PARTIAL` / `PARTIAL_COVERAGE`), con 0 publicaciones sintéticas.
   - **Mercado Libre:** Extracción de catálogo oficial (`tienda_nicopoly`) mediante scraper Playwright headless y consulta de taxonomía pública, segregando clips audiovisuales y registrando honestamente los estados reales sin invención.

---

## 2. RESULTADOS DE LA PRIMERA CORRIDA REAL Y ACOTADA

Se entregó al runner autónomo **únicamente la orden comercial original** sin intervención humana ni asistencia externa:

> *"Investiga las publicaciones y categorías de Nicopoly en Paris, Ripley, Falabella y Mercado Libre. Descubre las fuentes, selecciona los métodos disponibles, recopila las publicaciones, identifica categorías y vendedores, contrasta resultados, conserva evidencias y presenta un informe comercial verificable."*

### Resumen de Ejecución: `mri_021_real_run_1792178465`

- **Duración:** 89.50s
- **Base de datos aislada:** `tmp/mri_021_run/mri_021_truth_repair.db`
- **Estado global:** `PARTIAL` (reporte honesto: 3 marketplaces completados, 1 con cobertura parcial documentada).
- **Publicaciones sintéticas detectadas:** **0 (CERO)**.
- **Publicaciones reales persistidas:** **60** (20 Paris, 20 Falabella, 20 Mercado Libre).

| Marketplace | Estrategia Activa | Estado Operativo | Pubs de Marca | Categorías | Publicaciones Muestra | Vendedores | Evidencia Primaria Vinculada |
|---|---|---|---|---|---|---|---|
| **Paris** | `REA_CONSTRUCTOR_PUBLIC_API` | `COMPLETED` | 4.904 | 19 | 20 (`LIVE_OBSERVATION`) | NICOPOLY | Endpoint Constructor.io Search AI (`total_num_results: 4904`) |
| **Falabella** | `FALABELLA_SSR_BRAND_EXTRACTION` | `COMPLETED` | 368 | 1 | 20 (`LIVE_OBSERVATION`) | Nicopoly | SSR Next.js (`SHA-256: 01bcdb53...`, `sellerId: SC75ABC`) |
| **Mercado Libre** | `MELI_HEADLESS_CATALOG_SCRAPER` | `COMPLETED` | 537 | 1 | 20 (`LIVE_OBSERVATION`) | Nicopoly | Scraper headless catálogo oficial (`tienda_nicopoly`, 537 pubs) |
| **Ripley** | `RIPLEY_FACET_AND_COUNTER_VERIFICATION` | `PARTIAL` | 772 | 3 | 0 (Honesto: sin fakes) | Nicopoly | Verificación de facetas y contador (WAF/Turnstile documentado) |

---

## 3. CUMPLIMIENTO RIGUROSO DE CRITERIOS DE SALIDA

1. **Cero publicaciones ficticias:**
   - Verificado: Ningún SKU contiene prefijos sintéticos `RIP_{hash}`, `MLCMLC...` ni precios uniformes ficticios ($24.990 / $29.990).
   - Recuento auditado en SQLite: `synthetic_publications_count = 0`.
2. **Cero conteos constantes presentados como observaciones:**
   - La API `/api/multimarketplace/summary` calcula dinámicamente los valores en base a `mri_runs` y `mri_publications`.
   - Si no hay datos, responde `status: NO_RUN_DATA`. Si Ripley sólo aporta metadatos de facetas, su recuento de publicaciones es 0 y su estado es `PARTIAL`.
3. **Cero escritores sin protección:**
   - `AutonomousMultiMarketplaceRunner.__init__` ejecuta `StorageConfig.assert_write_allowed(self.db_path)`.
   - `_init_sqlite_tables` valida la barrera antes del `CREATE TABLE`.
4. **Evidencia primaria para cada resultado:**
   - Paris: Consulta real en vivo con clave pública y facetado CDP.
   - Falabella: SHA-256 (`01bcdb5364e052f864eabc9e80ec2f2577ca72b7406b684d0b375452643f18aa`) y fecha UTC vinculados en `commercial_attributes`.
   - Mercado Libre: Items extraídos directamente del DOM de la tienda oficial con enlaces canónicos (`https://articulo.mercadolibre.cl/MLC...`).
   - Ripley: Registro honesto del obstáculo WAF/Turnstile en la navegación headless y registro de metadatos sin publicaciones inventadas.
5. **Preservación estricta de las 2.533 observaciones originales:**
   - Consulta ejecutada sobre `data/sqlite/visibility.db`:
     - Recuento: `2533`
     - SHA-256 ordenado: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
     - Resultado: **PASS** (100% idéntico a la referencia certificada).
6. **Cero modificaciones en Visual Auditor:**
   - `git diff origin/main app/auditor app/scrapers app/dashboard app/storage app/loaders app/config`: **VACÍO** (0 líneas modificadas).

---

## 4. ARTEFACTOS Y EVIDENCIAS PRODUCIDAS

- **Manifiesto:** `evidence/mri_autonomy_truth_repair_021/MRI_021_MANIFEST.json`
- **Trazabilidad de la corrida:** `evidence/mri_autonomy_truth_repair_021/mri_021_real_run_1792178465_evidence.json`
- **Script reproducible:** `scripts/run_mri_021_real_execution.py`
- **Base de datos aislada de la corrida:** `tmp/mri_021_run/mri_021_truth_repair.db`

---

## 5. TRANSFERENCIA AL SIGUIENTE EJECUTOR

**Siguiente ejecutor:** **CODEX**  
**Objetivo:** Auditar independientemente la primera corrida real y verificar:
1. Ausencia de datos sintéticos en la base SQLite aislada.
2. Comportamiento dinámico de `/api/multimarketplace/summary`.
3. Inviolabilidad de las 2.533 observaciones históricas y código productivo de Visual Auditor.
4. Dictaminar si procede autorizar pruebas de repetibilidad.
