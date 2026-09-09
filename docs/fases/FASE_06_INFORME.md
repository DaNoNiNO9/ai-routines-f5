# Fase 6 — Motor de ajuste

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- `app/engine/adjustment/types.py`: `WeightPoint`, `IntakePoint`, `AdjustmentInputs` (con validación), `TrendEstimate`, `TdeeEstimate` y `AdjustmentDecision` (`to_dict()`).
- `smoothing.py`: media móvil de 7 días por ventana de calendario (mínimo 3 pesajes) y tendencia en kg/semana por mínimos cuadrados sobre la serie suavizada, con confianza según cobertura y duración; exige ≥ 8 pesajes en ≥ 10 días.
- `energy_balance.py`: TDEE observado por balance energético (`ingesta media + (−Δpeso × 7700) / días`) con ≥ 70 % de días de ingesta, acotado a ±25 % del teórico y mezclado con él según los días de datos (confianza total a los 28 días); adherencia media.
- `rules.py`: revisión quincenal con las reglas de §3.8: esperar sin datos, adherencia antes que metabolismo, recortes ≤ 5 % que respetan el suelo y el tope del 1 %, pasos cuando las calorías ya están en el suelo, subida de calorías si la pérdida supera el 1 %/semana, refeed y descanso de dieta ante estancamiento prolongado, reglas simétricas para superávit y mantenimiento. El TDEE se aprende sobre los últimos 42 días de historia, no solo sobre la ventana de revisión.
- 16 códigos de nota en `messages.py`; `docs/DECISIONES.md` T-48 a T-53; README del motor con la sección de ajuste; `tests/adjustment_sim.py` (modelo corporal sintético con adaptación metabólica y ruido de báscula).

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite de ajuste | `pytest tests/unit/engine/adjustment --cov=app/engine/adjustment` | 22 passed; cobertura 98,1 % |
| Suite del motor | `pytest tests/unit/engine --cov=app/engine` | 247 passed; 98,4 % |
| Suite completa | `pytest --cov` | 360 passed; cobertura de `app/` 98,6 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Suavizado | serie constante con ruido de 0,6 kg → medias a ±0,45 kg; series sin ventana suficiente → sin valor | OK |
| Tendencia | pérdida real de 0,5 kg/semana con ruido de 0,5 kg durante 28 días → −0,5 ±0,15 y confianza alta; 5 pesajes → sin tendencia | OK |
| Balance energético | 2000 kcal comiendo y −0,5 kg/semana → 2550 kcal; TDEE real recuperado a ±6 % con 28 días; mezcla al 50 % con 14 días; registros implausibles acotados al 75 % del teórico; sin cobertura de ingesta → solo teórico | OK |
| Reglas | antes de la fecha → esperar; sin datos → esperar 7 días; en objetivo → mantener; lento con adherencia → recorte ≤ 5 % sobre el suelo; en el suelo → +1000 pasos; pasos al máximo → mantener; adherencia 70 % → sin recorte; pérdida > 1 % → subida ≤ 10 %; estancamiento → refeed (6 semanas) y descanso de dieta (9 semanas); superávit lento/rápido; mantenimiento con deriva; validaciones de entrada | OK |
| Convergencia | 12 semanas simuladas con TDEE real 2350 frente a 2700 teórico, 5 semillas de ruido, revisiones cada 14 días aplicando las decisiones | calorías bajan sin cruzar el suelo, cada recorte ≤ 5 %, TDEE estimado final a ±8 % del real, pérdida final ≤ 1 %/semana |

## Errores aparecidos y cómo se corrigieron

1. **Tests con ruido excesivo para ventanas de 2 semanas**: con ±0,4 kg de ruido no se distingue una pérdida de 0,09 kg/semana en 14 días (y en la vida real tampoco: la regla espera a la siguiente revisión). Tests con ruido de 0,15 kg y 21 días.
2. **Revisión un día antes de la fecha** en el bucle de convergencia (mi error de calendario): corregido.
3. **TDEE aprendido solo sobre la ventana de revisión y mezclado al 50 % con el teórico**: nunca olvidaba un teórico equivocado. Rediseño: historia de 42 días con media de ingesta frente a cambio total de peso, mezcla creciente hasta confianza total.
4. **Artefacto de simulación**: cada bloque reiniciaba el peso real desde la última lectura ruidosa de la báscula, inyectando saltos falsos de ~150 kcal/día en el balance. El simulador ahora arrastra el peso real.
5. **Rama muerta** en la mezcla (tendencia de baja confianza implica ausencia de tendencia): eliminada; rama de confianza baja cubierta con una serie de 10 días.

## Limitaciones conocidas

- Sin registro de ingesta no hay TDEE observado: el motor se limita a las reglas por tendencia de peso con el TDEE teórico.
- Los pesajes con menos de 3 lecturas por semana no generan media móvil; el motor pide más constancia en vez de adivinar.

## Pendiente

- Fase 7: autenticación (registro, login, sesiones, argon2, recuperación, CSRF, rate limiting).
- Los servicios (Fase 8+) convertirán `AdjustmentDecision` en un plan nuevo y en filas de `plan_adjustments`.

## Criterio de cierre

Tests con series temporales simuladas de peso: converge y nunca cruza los límites de seguridad. Cumplido.
