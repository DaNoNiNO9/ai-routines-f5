# Fase 5 — Motor de rutinas

Fecha: 2026-09-09. Estado: **cerrada**.

## Qué se ha hecho

- `app/engine/routines/types.py`: `RoutineInputs` (validación de rangos), `ExerciseInfo`, `InjuryInput`, prescripciones, días, tabla de volumen, cardio y `RoutinePlan` con `to_dict()` y `all_notes()`.
- `catalog.py`: construcción de `ExerciseInfo` desde el JSON o filas, filtros duros (material completo, contraindicaciones por severidad mínima, aversiones, nivel técnico por experiencia), historial de hombro.
- `splits.py`: selección de split por días y experiencia (§3.7) y 16 plantillas de día definidas a mano como listas de slots (patrón, rol, músculo objetivo, unilateral).
- `volume.py`: series efectivas (primario 1, secundario 0,5), rangos 8-12 / 12-18 / 16-22, prioridades +27,5 % con compensación del resto, tabla de volumen con estado.
- `selection.py`: puntuación determinista (preferidos, staples del entrenador, músculo objetivo, mecánica del rol, material cargable, unilateral, penalización por reuso) con desempate por CRC32; relajación de un nivel técnico anotada.
- `prescription.py`: series por defecto por experiencia y rol, rangos de reps por rol y objetivo, RIR semanal 3→1, descansos (más cortos con peso corporal), tempo, incrementos de carga por material y sexo, mesociclo y descarga según experiencia y fatiga, estimación de duración.
- `cardio.py`: pasos objetivo, sesiones LISS/HIIT dimensionadas al déficit que la dieta no cubre, HIIT condicionado, nota fija de "nunca como castigo".
- `generator.py`: orquestador: objetivos de volumen escalados al tiempo disponible, ajuste de series, slot extra para músculos prioritarios sin hueco, equilibrio empuje/tracción (añadir tracción, accesorio de tracción o quitar empuje), recorte por tiempo que protege la tracción, cobertura de patrones explicada (recortado, no programado, bloqueado por lesión o imposible con el material), bloqueos con motivo.
- 25 códigos de nota nuevos en `messages.py`; `docs/DECISIONES.md` T-40 a T-47; README del motor reescrito con la sección de rutinas.

## Qué se ha probado

| Prueba | Cómo | Resultado |
|---|---|---|
| Suite de rutinas | `pytest tests/unit/engine/routines --cov=app/engine/routines` | 134 passed; cobertura 97,4 % |
| Suite del motor completo | `pytest tests/unit/engine --cov=app/engine` | 225 passed; 98,5 % |
| Suite completa | `pytest --cov` | 338 passed; cobertura de `app/` 98,6 % |
| Linter y formato | `ruff check .`, `ruff format --check .` | limpios |
| Rejilla de perfiles | 100 combinaciones (5 experiencias × 5 frecuencias × 4 lugares) | cada rutina: material dentro del disponible, sin contraindicados ni aversiones, rangos válidos para la BD (series 1-12, reps ≤ 20, RIR 0-6, descansos 15-600 s), duración ≤ 105 % del tiempo o aviso, ratio tracción/empuje ≥ 0,85 o aviso, patrones cubiertos en gimnasios con ≥ 3 días (o explicación), ≤ 2 grupos bajos en gimnasio, JSON serializable |
| Lesiones | hombro + lumbar moderadas; las 8 zonas graves | sin sentadilla, press militar ni peso muerto; sesgo de tracción ≥ 1,15; con todo grave, rutina parcial explicada o bloqueo con motivo |
| Prioridades | glúteos en 5 días; gemelos en 2 días full body | más volumen que sin prioridad; slot añadido cuando la plantilla no lo tenía |
| Tiempo | 2 días × 25 min y 4 × 120 min | recorte y objetivos escalados en el corto; sin avisos en el largo |
| Preferencias, rendimiento, límites | preferidos y aversiones; objetivo rendimiento (3-6 en principales); 7 días → 6; 0 días y catálogo vacío → bloqueo | OK |
| Determinismo | misma entrada dos veces | `to_dict()` idéntico |
| Prueba manual | 5 perfiles (gimnasio 4 d, casa sin material 3 d, mujer con hombro y lumbar 5 d con prioridad, principiante 2 d × 20 min, avanzado 6 d rendimiento en casa) | selecciones de entrenador (banca, sentadilla, RDL, jalón, remo; press en suelo y hip thrust con lesiones), tiempos ajustados, avisos honestos |

## Errores aparecidos y cómo se corrigieron

1. **Selecciones raras** (press en suelo como principal, sentadilla frontal con kettlebell, bandas en un gimnasio completo): la puntuación no distinguía calidad. Corrección: lista de *staples* y bonus por material cargable (barra > máquina/mancuerna > kettlebell > bandas > peso corporal).
2. **Avisos de volumen bajo en todos los grupos** con sesiones de 60 min: los objetivos por experiencia no caben físicamente. Corrección: objetivos escalados al tiempo disponible con nota explícita.
3. **Ratio empuje/tracción roto por el recorte de tiempo** (equilibrio antes de recortar). Corrección: recorte que protege las series de tracción y segunda pasada de equilibrio en modo "solo reducir empuje" tras el recorte.
4. **Cobertura mal atribuida**: un patrón recortado por tiempo se explicaba como falta de material. Corrección: la comprobación distingue recortado, no programado, bloqueado por lesión o imposible con el material.
5. **Descansos de 3 min en flexiones**: irreal. Corrección: tabla de descansos propia para ejercicios de peso corporal.
6. **Compensación de prioridades sin efecto** por redondeo (16 → 16). Corrección: redondeo hacia abajo para los grupos no prioritarios.
7. **Mensajes de slot vacío en aislamiento** demasiado ruidosos con peso corporal: ahora son informativos; los de patrón siguen siendo avisos.

## Limitaciones conocidas

- Los ejercicios de core estáticos (plancha) se prescriben en repeticiones; la UI deberá mostrar "o 30-45 s".
- Un solo mesociclo: la rotación de plantillas entre mesociclos (variedad) llega con el motor de ajuste y el seguimiento.
- Las rutinas con peso corporal puro no pueden equilibrar bien la tracción sin barra ni bandas; el plan lo dice y sugiere material.

## Pendiente

- Fase 6: motor de ajuste (§3.8): media móvil de 7 días, comparación quincenal, TDEE observado por balance energético, estancamiento, diet break y refeed.

## Criterio de cierre

Tests que generan rutinas para ≥ 30 perfiles distintos y validan volumen, equilibrio de patrones, respeto a lesiones y encaje en el tiempo disponible. Cumplido: 100 perfiles en rejilla más casos específicos.
