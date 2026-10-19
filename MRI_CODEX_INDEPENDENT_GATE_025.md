# MRI_CODEX_INDEPENDENT_GATE_025

Fecha: 2026-10-19 (America/Santiago). Auditor: CODEX. Auditoría posterior, independiente, sin desarrollo ni adquisición comercial.

```makefile
MRI_022_VERDICT=FAIL
MRI_023_VERDICT=FAIL
MCP_REAL_CONNECTION=NO;ADAPTER_USES_URLLIB_HTTP
REGISTRY_RUNNER_INTEGRATION=NO
T1_T8_ORIGINAL=NOT_SATISFIED
SECURITY=FAIL_DOMAIN_BOUNDARY_REDIRECT_VALIDATION_AND_INFLIGHT_REVOCATION
HISTORY_2533=PASS_COUNT_ATTRIBUTE_HASH_AND_SQLITE_INTEGRITY
VA_PRODUCTION=VA_DIFF_ZERO;PRODUCTION_UNCHANGED_DURING_AUDIT
FIRST_MATERIAL_FAILURE=MRI_022_API_CATEGORY_MEMBERSHIP_LEAK_ACROSS_RUNS
NEXT_EXACT_ACTION=CLOSE_MRI_022_RUN_SCOPING_COUNTEREXAMPLE;MRI_023_REMAINS_REJECTED_AGAINST_ORIGINAL_CONTRACT
```

SHAs obligatorios examinados:
- MRI-022: c7ce7e8bb702b4c0cdd4943b33eac13bf29d4c2e.
- MRI-023: cda1e6e3f7548be55cf7035c5d67341754db0dc4.

## Método y límites

Se recuperaron de GitHub los informes y módulos relevantes fijados a esos SHAs. Las reproducciones cargan fuentes extraídas de Git mediante git show, sin ejecutar bytecode local. Se aplicó el preflight y las cuatro skills obligatorias del proyecto. No se iniciaron scrapers, sesiones de navegador, procesos MCP ni solicitudes a marketplaces. No se instaló software.

Las pruebas de persistencia utilizan una copia de la base aislada MRI-021 y sus tablas reales, vaciadas únicamente dentro de la copia para introducir un fixture negativo inequívoco. Las publicaciones AUDIT_* son datos de prueba, nunca observaciones comerciales. Las funciones API exactas se ejecutan por AST, sin arrancar la aplicación completa; no se certifica una sesión de dashboard en navegador.

El transporte del adaptador 023 se sustituyó por un objeto de prueba local que devuelve bytes identificados como OFFLINE AUDIT FIXTURE. Esa prueba demuestra flujo de control y efectos de revocación; no es una operación MCP real ni evidencia de adquisición. Las validaciones de dominio se probaron sin resolver DNS ni navegar a esos destinos.

## A. MRI-022 — FAIL

### Avances demostrados

1. **Barrera anterior a conexión: PASS para el contraejemplo anterior.** El runner construido con una ruta de sandbox y después redirigido a data/sqlite/visibility.db lanza ProductionWriteBlockedError antes de sqlite3.connect. El centinela registra cero llamadas. No se abrió producción.
2. **Procedencia Mercado Libre: PASS para el persistidor probado.** Se ejecutó MeliTaxonomyEngine.persist_to_mri_sqlite() con una publicación de prueba cuyo tipo era LIVE_OBSERVATION y raw_source_id AUDIT-OBS. Ambas observaciones, activa e histórica, conservan esos valores; mri_runs registra MELI_HEADLESS_CATALOG_SCRAPER. Ya no impone OFFICIAL_API_RECORD en este camino.
3. **Estado bloqueado: PASS para el resumen consultado.** Los dos runs del fixture se registraron BLOCKED y la API mantuvo BLOCKED pese a tener publicaciones.
4. **Run inexistente: PASS parcial de delimitación.** AUDIT_UNKNOWN devuelve cero categorías y publicaciones; se corrigió la lectura global indiscriminada anterior.
5. **Fallo local de Ripley: mejora demostrada.** AUDIT_LOCAL_FAILURE_NOT_WAF produce PARTIAL, una causa local explícita y cero publicaciones; ya no se atribuye automáticamente ese caso al WAF ni se devuelve 772 en el objeto del runner.

Estos resultados son acotados a los caminos ejecutados; no certifican todos los escritores o toda la autonomía comercial.

### Primer defecto material reproducible: categorías heredadas por el historial

Reproducción mínima:
1. En una copia del esquema SQLite real, persistir AUDIT_MELI / AUDIT_SKU en AUDIT_A con categoría CAT_A.
2. Persistir la misma publicación en AUDIT_B con categoría CAT_B, usando el adaptador real de MRI-022.
3. Consultar get_multimarketplace_summary(run_id='AUDIT_A').
4. Resultado: Mercado Libre tiene categories_count=2. El valor correcto es 1: solo CAT_A. AUDIT_B devuelve 1.

SQLite conserva por separado la observación histórica A y la activa B. El error está en la proyección: la subconsulta p filtra publicaciones por run_id, pero la rama de mri_publication_categories incluye todas las pertenencias activas y las une solo por publication_id. Así, la publicación histórica A se une a la pertenencia activa B. Filtrar únicamente el lado de publicaciones no delimita toda la relación por corrida.

Evidencia: results.json → 022_summary, 022_persistence y 022_links. Es un contraejemplo directo de una exigencia de esta entrega; basta para FAIL de MRI-022.

Condición de cierre mínima: la recuperación de categorías históricas debe usar las pertenencias del mismo run, sin unirlas a las pertenencias activas de una observación posterior. Repetir exactamente el caso A/B y verificar categorías y conteos exclusivos. No se cambió código.

### Conteos y etiquetas comerciales pendientes

El fallback de Ripley devuelve listas vacías en el resultado, pero llama normalize_items_to_publications([]), que sigue generando tres entidades desde RIPLEY_VERIFIED_CATEGORIES con reported_total 284/256/232 y evidence_status VERIFIED_PUBLIC_TRAFFIC. La reproducción inserta tres filas de categoría Ripley sin publicaciones adquiridas. get_commercial_summary() sigue sumando 772; la ruta /api/ripley/nicopoly continúa expuesta sobre ese método. La eliminación de constantes no es global aunque el resultado del runner haya mejorado.

El esquema mri_runs sigue usando run_id como clave única y los adaptadores INSERT OR REPLACE; no representa simultáneamente todos los estados por marketplace de una misma corrida. No se declara resuelto el historial multimarketplace por comprobar un estado de un solo adaptador.

## B. MRI-023 — FAIL contra el plan original

### 1. Inventario estático presentado como capacidad operativa

CapabilityRegistry.__init__() ejecuta _init_default_capabilities() y registra ocho entradas escritas en código. No descubre servidores, herramientas, dependencias ni disponibilidad mediante comprobaciones reales.

Las definiciones parten de health=HEALTHY y success_rate=1.0, sin historial ni comprobación: last_verified_at=None. Las ocho tasas iniciales son 1.0, incluidas capacidades de MCP que no han establecido sesión. Esto incumple expresamente la prohibición de inventar tasas por ausencia de historial y de considerar operativas capacidades no validadas.

Registrar una definición nueva y ordenar definiciones sí funciona como primitiva local. No equivale al descubrimiento operativo requerido en T1.

### 2. Orquestador sin conexión al registro y selector

El runner del SHA 023 no importa ni utiliza CapabilityRegistry o StrategySelector. La búsqueda de referencias en app y scripts encuentra únicamente sus módulos de definición y el uso interno del registro por el selector. La secuencia del runner continúa predeterminada por marketplace.

No existe un flujo demostrado objetivo → alternativas del registro → selección → ejecución de adaptador → resultado/evidencia → actualización de experiencia en el MRI operativo. StrategySelector calcula prioridades y IDs de fallback, pero no ejecuta ni controla por sí mismo intentos, presupuesto o cancelación de una investigación.

### 3. No existe la conexión MCP exigida

StealthBrowserMCPAdapter.fetch_page_content() construye urllib.request.Request y llama urllib.request.urlopen. El módulo no inicializa transporte MCP, ClientSession, negociación initialize, listado/invocación de herramientas ni sesión con Stealth Browser MCP. El nombre de la clase, adapter_mode STEALTH_MCP y la metadata mcp_adapter_version no cambian ese transporte HTTP.

La prueba nueva llamada T6 contacta robots.txt mediante ese mismo urllib y acepta 200/403/404; prueba bytes y SHA, no navegación/lectura mediante MCP. No se repitió esa solicitud. No hay captura versionada en evidence/mri_stealth_mcp_captures en el SHA entregado. Incluso una respuesta HTTP real allí no satisfaría T4 original.

MCP_REAL_CONNECTION=NO en la implementación examinada; no se considera un bloqueo ambiental que oculte una implementación existente.

### 4. Política de destinos vulnerable

_assert_allowed() comprueba si un dominio autorizado aparece como subcadena de urlparse(url).netloc. Resultado reproducido, sin red:

| Destino | Resultado real | Evaluación |
|---|---|---|
| https://paris.cl.attacker.invalid/ | ALLOWED | Dominio engañoso aceptado |
| https://notparis.cl/ | ALLOWED | Dominio ajeno aceptado |
| https://paris.cl@attacker.invalid/ | ALLOWED | Credencial de URL confundida con host |
| https://unauthorized.invalid/ | BLOCKED | Control negativo correcto |
| ftp://paris.cl/file | ALLOWED | Esquema no restringido |

No verifica hostname mediante igualdad o límite de subdominio, ni esquema admitido, ni revalida destinos de redirección. urllib sigue redirecciones por defecto. En el transporte simulado, una respuesta cuya URL final era unauthorized.invalid se aceptó sin consultar geturl(); la captura se atribuyó a la URL inicial autorizada. La prueba no contactó ese host.

### 5. Revocación parcial y rollback no demostrado

Se reconoce que revoke_permissions() bloquea una petición posterior: el control negativo pasa.

Sin embargo, se revocó el permiso dentro de la función de transporte simulada antes de devolver la respuesta. fetch_page_content() continuó, escribió el archivo y registró FETCH_SUCCESS. Solo valida permiso al inicio; no lo revalida antes de guardar o emitir éxito. No demuestra cancelación de operaciones en curso.

Cada nueva instancia comienza con _permission_active=True y grant_permissions() reactiva el booleano sin alcance, caducidad ni autoridad externa. No hay revocación de sesión/proceso MCP, porque no se crea tal sesión/proceso.

evidence_dir es una ruta proporcionada por el llamador y se escribe con mkdir/write_bytes sin la barrera StorageConfig ni un límite de sandbox propio. Se inspeccionó este camino; no se intentó escribir en recursos protegidos. Los archivos usados por el auditor estuvieron dentro de su carpeta.

El informe propone volver a un SHA base, pero no entrega puntos verificables por fase ni registros de ejecución/restauración de almacenes, permisos, procesos y configuración conforme al plan. Una referencia Git permite recuperar código; no demuestra el rollback integral requerido. No se ejecutó rollback sobre las ramas del implementador ni sobre producción.

### 6. Correspondencia con T1–T8 originales

La entrega renumera requisitos RG y pruebas; se evalúa el significado original del plan aprobado:

| Prueba original | Evidencia examinada | Resultado |
|---|---|---|
| T1 Inventario operativo automático | Ocho entradas estáticas sin health checks | FAIL |
| T2 Selección autónoma conectada a MRI | Ranking local; runner sin integración | FAIL |
| T3 Gestión de fallos, alternativas y límites | Circuit breaker alimentado manualmente; sin ejecución orquestada ni presupuesto demostrado | INCOMPLETA |
| T4 Lectura real mediante Stealth Browser MCP | urllib HTTP; ninguna sesión MCP | FAIL |
| T5 Seguridad y aislamiento | Bypass de dominios; no revalidación de redirect/revocación en curso | FAIL |
| T6 Procedencia verificable | Hash local implementado; sin vínculo de operación MCP y sin corrección del origen tras redirect | INCOMPLETA |
| T7 Regresión y 2.533 observaciones | Preservación histórica comprobada por Codex; no paquete de regresión/rollback del registro que cubra todo el requisito | PARCIAL |
| T8 Extensibilidad mediante alta, ejecución, desactivación y retiro sin cambiar núcleo | Test nuevo T8 solo rechaza un dominio; registro no ofrece retiro/ejecución integrada demostrada | NO DEMOSTRADA |

No se usa el número de tests nuevos aprobados como aceptación. Las primitivas de registro, ranking, hash y bloqueo de peticiones posteriores se reconocen, pero no completan los criterios operativos originales.

## Preservación independiente

Se compararon ambos SHAs contra main consultado en GitHub: 3e5d058aa3c0b9b388bab990b14d8cc134627d2e. Cero cambios en app/auditor, app/scrapers, app/core, app/dashboard, app/storage, app/loaders y app/config en esas comparaciones.

La carpeta evidence/mri_autonomy_truth_repair_021 permanece sin diff entre 274005dbef951392d0952253522f645a723b0af4 y el SHA 023.

La copia productiva de solo lectura conserva 2.533 observaciones originales y todos sus atributos compartidos. Hash:
c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b.
integrity_check=ok; foreign_key_check=[].

Los cinco archivos productivos protegidos mantienen hashes idénticos antes/después de estas comprobaciones. Se limita esta garantía al intervalo de la auditoría; no se certifican acciones anteriores del implementador sin una línea base anterior.

El checkout inicial ya contenía modificaciones de cuatro pyc versionados. Se registraron antes/después; las pruebas cargaron fuentes exactas y deshabilitaron generación de bytecode. No se limpiaron ni deshicieron cambios ajenos. No se presenta el checkout como limpio.

## Evidencias y reproducción

Carpeta local: evidence/mri_codex_independent_gate_025/.
- check_gate.py: reproducción completa, acotada y sin red.
- results.json: barrera, persistencia, categorías por corrida, fallback Ripley, inventario, dominios, transporte simulado, revocación, hashes e integridad.
- subcarpetas con fuentes exactas de ambos SHAs.
- remote_evidence.json: consultas GitHub y comparación de recursos protegidos.
- SHA256SUMS.txt: hashes de evidencia local.

Comando: python evidence/mri_codex_independent_gate_025/check_gate.py. Requiere ambos objetos Git y las bases locales indicadas en el script. Solo se escriben copias y artefactos dentro de su carpeta. Las bases, resultados derivados y capturas simuladas se conservan localmente; se publica únicamente este informe.

## Decisión y siguiente acción

**MRI-022: FAIL**, por fuga de categorías históricas al consultar la misma publicación en dos corridas, además de metadatos estáticos de Ripley aún persistidos.

**MRI-023: FAIL**, por falta de transporte MCP real e integración con el runner, inventario no comprobado y defectos de límites/revocación reproducibles.

Siguiente acción exacta: cerrar el contraejemplo A/B de pertenencias en MRI-022 y devolver esa prueba mínima. MRI-023 no está aprobado: su revisión posterior deberá demostrar los criterios originales, especialmente sesión MCP auténtica, integración real y controles de destinos/revocación. Esta decisión no inicia desarrollo, no autoriza adquisiciones, no concede repetibilidad y no fusiona a main.
