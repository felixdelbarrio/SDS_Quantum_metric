# Correlación request–response–widget

`correlation.py` puntúa solo identificadores fuertes. `widget_id` exacto aporta 0.95, `card_id` exacto 0.90 y tab/section solo complementan. El umbral automático es 0.90.

Si más de un widget supera el umbral, el resultado es `failed_ambiguous_widget_correlation`. No se usan similitud de título, posición aproximada, tipo TABLE ni orden de captura. Cada candidato conserva request id, request hash, response hash, tab/section, confianza y evidencia.
