# INFORME FINAL — AUDITORÍA INTEGRAL CORREGIDA (VERDAD DE EVIDENCIA)

**TASK_ID:** `VA-4MP-EVIDENCE-TRUTH-001`  
**BASE_COMMIT:** `ff250684a549e53087a77e08ba1dbc2c673e554c`  
**ESTADO:** `PASS`  
**FECHA:** `2026-10-14T12:42:59.744347`  
**MODALIDAD:** `EVIDENCE TRUTH RECONCILIATION / CORRECTION`  
**ALCANCE:** Mercado Libre Chile, Falabella Chile, Paris Chile, Ripley Chile  
**OBJETIVO:** Nicopoly  
**COSTO EXTERNO:** **US$ 0.00 (Zero paid APIs, zero external vendors)**

---

## 1. Resumen de Corrección de Evidencia (Sin Nuevo Barrido Masivo)

Se ejecutó la corrección forense de la auditoría integral de las **3.999 publicaciones**, eliminando sobre-clasificaciones inferidas y reflejando con exactitud matemática la evidencia física observada.

### Métricas Corregidas Transversales por Marketplace

| Métrica | Mercado Libre | Falabella | Paris | Ripley | Consolidado 4MP | % Universo |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Universo de Manifiesto (`MANIFEST_PROCESSED`)** | 1.811 | 1.063 | 763 | 362 | **3.999** | **100.0%** |
| **Peticiones HTTP Intentadas (`HTTP_REQUEST_ATTEMPTED`)** | 4 | 2 | 4 | 1 | **15 (11 corr + 4 probe)** | - |
| **Observadas en Vivo Inequívocas (`LIVE_OBSERVATION_CONFIRMED`)** | 339 | 310 | 158 | 47 | **854** | **21.4%** |
| **Publicaciones Sin Confirmación en Vivo (`NOT_CONFIRMED`)** | 1472 | 753 | 605 | 315 | **3145** | **78.6%** |
| **Bloqueos HTTP Observados (`SOURCE_BLOCKED`)** | 0 | 0 | 0 | 0 | **0** | **0.0%** |
| **Bloqueos Inferidos por Regla WAF (`SOURCE_BLOCKED_INFERRED`)** | 0 | 665 | 0 | 315 | **980** | **24.5%** |
| **Ausencias Demostradas por Negativa (`NOT_FOUND`)** | 0 | 0 | 0 | 0 | **0** | **0.0%** |
| **Publicaciones Pendientes de Intento (`NOT_TESTED`)** | 0 | 0 | 0 | 0 | **0** | **0.0%** |
| **Errores Técnicos (`ERROR`)** | 0 | 0 | 0 | 0 | **0** | **0.0%** |
| **Identidades Verificadas (`TARGET_IDENTITY_VERIFIED`)** | 1133 | 350 | 549 | 116 | **2148** | **53.7%** |
| **Identidades No Vinculadas (`IDENTITY_NOT_LINKED`)** | 678 | 713 | 214 | 246 | **1851** | **46.3%** |
| **Posiciones de Listado Observadas** | 339 | 310 | 158 | 47 | **854** | **21.4%** |
| **Categorías Verificadas (Variantes Estructurales)** | - | - | - | - | **1446** | - |
| **Diferencias Textuales Sujetas a Revisión (`REVIEW_REQUIRED`)** | - | - | - | - | **513** | - |
| **Desalineaciones Comerciales Confirmadas (`CATEGORY_MISMATCH`)** | - | - | - | - | **189** | - |
| **Costo Monetario Externo** | $0.00 | $0.00 | $0.00 | $0.00 | **$0.00** | **0.0%** |

---

## 2. Acciones de Verdad de Evidencia Realizadas

1. **Reclasificación de 1.834 `NOT_FOUND` a `NOT_CONFIRMED`:**
   - La designación previa de `NOT_FOUND` a 1.229 publicaciones en Mercado Libre y 605 en Paris constituía una sobre-afirmación sin evidencia negativa individual (no se emitieron 1.834 peticiones HTTP comprobando 404 o estado pausado).
   - Han sido reclasificadas honestamente como `NOT_CONFIRMED`, preservando la trazabilidad de que se trata de publicaciones históricas ausentes de los corredores públicos principales al momento de la auditoría.

2. **Distinción de 980 `SOURCE_BLOCKED`:**
   - En la corrida previa, 665 publicaciones de Falabella y 315 de Ripley fueron etiquetadas como `SOURCE_BLOCKED` por regla general del marketplace (conocimiento de WAF Cloudflare).
   - Dado que no se enviaron 980 peticiones HTTP individuales a cada PDP, la métrica `SOURCE_BLOCKED` (observada directamente por HTTP 403) se fija en **0**, mientras que los 980 casos se registran como `NOT_CONFIRMED` con el motivo técnico `BLOCKED_INFERRED_WAF_PROTECTED`, documentados en `BLOCKERS.json`.

3. **Certificación Estricta de 854 `LIVE_OBSERVATION_CONFIRMED`:**
   - De los 1.185 anteriores, se descartaron 331 enlaces que dependían exclusivamente de coincidencias aproximadas por título.
   - Se certifican exclusivamente **854 publicaciones** que poseen relación unívoca demostrada por **identificador de publicación (`publication_id`) o URL canónica exacta** con los productos observados en vivo en los corredores oficiales contemporáneos.

4. **Reclasificación de las Discrepancias de Categoría:**
   - Se exigió identidad vinculada al catálogo ERP maestro.
   - De las discrepancias evaluadas sobre identidades verificadas:
     - **513 casos** fueron clasificados como `REVIEW_REQUIRED`: corresponden a variaciones textuales legítimas, grupos de sinónimos de vestuario (ej. Calzas vs Pantalones, Blusa vs Top, Blazer vs Chaqueta) o casos donde la categoría pública coincide con el sustantivo del título del producto.
     - **189 casos** se certifican como `CATEGORY_MISMATCH`: corresponden a desalineaciones comerciales comprobadas con identidad ERP verificada donde el producto fue ubicado en una familia divergente.

5. **Política de Seguridad y Verificación TLS:**
   - Se detectó que el script de prueba scratch `scratch/test_live_fetch.py` contenía `ssl.CERT_NONE` y `check_hostname = False`.
   - Dicho script ha sido **cuarentenado y excluido formalmente** como fuente de evidencia válida.
   - Todas las observaciones vivas certificadas provienen exclusivamente de Playwright headless y adaptadores con verificación TLS estricta por defecto.

---

## 3. Entregables Corregidos Persistidos

Todos los artefactos requeridos están persistidos en `evidence/va_4mp_live_publications_001/`:
- `RUN_MANIFEST.json`
- `EXECUTION_SUMMARY.json`
- `PUBLICATION_OBSERVATIONS.jsonl`
- `IDENTITY_RECONCILIATION.json`
- `CATEGORY_AUDIT.json`
- `BLOCKERS.json`
- `EVIDENCE_INDEX.json`
- `FINAL_REPORT.md`
- `MRI_4MP_PUBLICATIONS_AUDIT.xlsx` (Libro Excel con 9 hojas operativas formateadas y columnas comparativas de auditoría)
