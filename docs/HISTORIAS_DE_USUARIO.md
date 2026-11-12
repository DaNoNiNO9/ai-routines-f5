# Historias de usuario

El texto completo (historias con criterios Dado/Cuando/Entonces y guía para probadores) vive en un documento compartible, pensado para el abogado y los primeros probadores:

**https://claude.ai/artifact/CQd5oDsP2MrrDG1EvZfUYd**

Se puede exportar a Word, PDF o Markdown desde el propio documento. Aquí queda el índice, con los ficheros de test que vigilan cada historia (`tests/integration/`). Si se cambia una historia, actualizar las dos cosas.

Versión del 2026-11-12: 42 historias en 8 épicas, 813 tests en verde.

| Historia | Plan | Tests |
|---|---|---|
| **1. Cuenta, privacidad y consentimiento** | | |
| US-1.1 Crear una cuenta | Gratis | `test_auth` |
| US-1.2 Dar el consentimiento para datos de salud | Gratis | `test_privacy` |
| US-1.3 Sin consentimiento, nada de salud | Gratis | `test_privacy` |
| US-1.4 Retirar el consentimiento | Gratis | `test_privacy` |
| US-1.5 Leer la política de privacidad | Gratis | `test_audit_security` |
| US-1.6 Ningún dato de salud a terceros | Gratis | `test_privacy` |
| US-1.7 Entrar, salir y recuperar la contraseña | Gratis | `test_auth` |
| US-1.8 Cambiar mis datos de cuenta | Gratis | `test_account` |
| **2. Cuestionario, plan en un minuto y seguridad** | | |
| US-2.1 Mi plan en un minuto | Gratis | `test_quick_onboarding` |
| US-2.2 Cuestionario completo | Gratis | `test_onboarding` |
| US-2.3 Bloqueos de seguridad | Gratis | `test_audit_safety`, `test_quick_onboarding`, `test_onboarding` |
| US-2.4 Aviso de herramienta orientativa | Gratis | `test_audit_safety`, `test_billing_rights` |
| US-2.5 Datos imposibles y fallos | Gratis | `test_audit_safety`, `test_audit_robustness`, `test_onboarding` |
| **3. Plan de nutrición, alimentos y menú** | | |
| US-3.1 Entender mi plan de comida | Gratis | `test_plan_pages` |
| US-3.2 Buscar y apuntar alimentos | Pro | `test_food`, `test_billing_rights` |
| US-3.3 Código de barras | Pro | `test_food`, `test_billing_rights` |
| US-3.4 Habituales, copiar ayer y borrar | Pro | `test_food` |
| US-3.5 Total del día a mano | Gratis | `test_tracking_pages`, `test_food` |
| US-3.6 Menú de la semana y lista de la compra | Pro | `test_menu_pages` |
| **4. Entreno, sesiones, ficha de ejercicio, marcas y racha** | | |
| US-4.1 Ver mi rutina | Gratis | `test_plan_pages` |
| US-4.2 Apartar un ejercicio que no me gusta | Gratis | `test_exercise_preferences` |
| US-4.3 Hacer la sesión en el gimnasio | Gratis | `test_workout_flow`, `test_audit_robustness` |
| US-4.4 Ficha del ejercicio | Gratis | `test_exercise_sheet` |
| US-4.5 ¿Cómo llegas hoy? (día suave) | Gratis | `test_connected` |
| US-4.6 Marcas y racha | Gratis | `test_records_streak`, `test_workout_flow` |
| **5. Diario, revisión quincenal y fecha de llegada** | | |
| US-5.1 Panel de hoy | Gratis | `test_plan_pages`, `test_audit_robustness` |
| US-5.2 Apuntar peso, comida, pasos y medidas | Gratis | `test_tracking_pages` |
| US-5.3 Revisión quincenal | Gratis | `test_review_page`, `test_audit_robustness`, `test_logging_edge_cases` |
| US-5.4 Tu fecha de llegada | Pro | `test_arrival`, `test_billing` |
| **6. App instalable y sin cobertura** | | |
| US-6.1 Instalar Alza en el móvil | Gratis | `test_installable` |
| US-6.2 Entrenar sin cobertura | Gratis | `test_installable` |
| **7. Alza Pro, pagos y derechos del consumidor** | | |
| US-7.1 Ver precios con toda la información | Gratis | `test_billing`, `test_billing_rights` |
| US-7.2 Suscribirme con prueba gratis | Pro | `test_billing`, `test_stripe_gateway` |
| US-7.3 Cancelar y reanudar con un clic | Pro | `test_billing_rights`, `test_billing` |
| US-7.4 Desistir en 14 días | Pro | `test_billing_rights` |
| US-7.5 Pagos fiables | Pro | `test_stripe_gateway`, `test_billing_rights`, `test_factory` |
| **8. Exportar, borrar, idiomas y seguridad** | | |
| US-8.1 Plan en PDF | Gratis | `test_account` |
| US-8.2 Todos mis datos en CSV | Gratis | `test_account`, `test_privacy` |
| US-8.3 Borrar mi cuenta | Gratis | `test_account`, `test_billing` |
| US-8.4 Usar Alza en inglés | Gratis | `test_i18n`, `test_brand` |
| US-8.5 Lenguaje claro y tema | Gratis | `test_coherence`, `test_plan_pages` |
| US-8.6 Mis datos son solo míos | Gratis | `test_audit_security`, `test_security` |
