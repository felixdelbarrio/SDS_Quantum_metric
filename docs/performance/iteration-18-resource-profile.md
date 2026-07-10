# Perfil de recursos Iteración 18

Estado de medición E2E: **BLOCKED por autenticación Quantum**.

Medición local disponible (2026-07-10): 154 pruebas backend en ~4.3 s y 41 pruebas frontend en ~4.5 s en el equipo de desarrollo. El baseline completo `make CI` y `make build` pasó antes de cambios.

El diseño evita cargar RAW/`response_json` en Home: el endpoint lee filas estrechas de `derived/widget_contracts`, filtra dashboard/range y agrupa jerarquía. No se publica una cifra de memoria, red o latencia de captura CO/MX sin una ejecución autenticada reproducible.
