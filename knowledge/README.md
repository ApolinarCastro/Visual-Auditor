# Experiencias operacionales MRI

Objetos de conocimiento **read-only** para evitar redescubrir caminos ya demostrados como inválidos.

Reglas:
- `CANDIDATE`: registrado con evidencia, no ejecuta cambios.
- `VALIDATED`: reutilizado y verificado en una corrida real.
- `STALE`: requiere revalidación.
- `RETIRED`: reemplazado por una ruta nueva.

Ningún objeto de este directorio contiene cookies, tokens, credenciales ni datos personales. No modifica scrapers, runners ni base de datos.

Objeto actual:
- [MRI-EXP-ML-ACQUISITION-001](MRI-EXP-ML-ACQUISITION-001.json) — caminos negativos y positivos de adquisición Mercado Libre.
