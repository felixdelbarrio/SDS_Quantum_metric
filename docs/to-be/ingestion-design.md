# Ingestion Design

La ingesta usa una estrategia de browser-capture para no inventar queries:

1. Obtiene cookies en memoria.
2. Inyecta cookies en un contexto Playwright no persistente.
3. Navega al dashboard configurado.
4. Captura respuestas de `/analytics` y `/analytics/historical`.
5. Persiste request/response sin headers sensibles.
6. Genera manifest.

Esta estrategia permite que cambios de body en Quantum se capturen como contratos versionados antes de adaptar parsers derivados.
