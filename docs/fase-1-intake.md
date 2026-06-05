# Fase 1 — Intake con preguntas + brief consolidado

Disponible desde **v0.3.0**.

## Qué resuelve

En Fase 0 el bot solo pasaba prompts libres a Claude. Para arrancar un proyecto
de venta CodeCanyon necesitamos un proceso más estructurado: **prompt original
+ preguntas que clarifican + brief consolidado que sirve de contrato.**

Inspirado en el MASTER-PROMPT v2 § 2.2.

## Flujo desde el móvil

```
Tú      → /nuevo
Bot     → "Mandame el prompt inicial del producto…"

Tú      → "Quiero un módulo Perfex que detecte facturas duplicadas…"
Bot     → ⏳ Analizando…
Bot     → 📋 Intake — Perfex Duplicate Invoice Detector
          Stack detectado: Perfex
          Slug propuesto: perfex-dup-facturas

          Tengo 5 preguntas:
          P1. ¿Para clientes con qué volumen mensual?
          P2. ¿Detectar por nro factura, total + RUC, o ambos?
          P3. ¿Acción automática o solo flag para revisión humana?
          P4. ¿Histórico desde hace cuánto?
          P5. ¿Notificar cuando se detecta duplicado? ¿Cómo?

          Respondé TODAS en UN solo mensaje, formato:
          P1: tu respuesta
          P2: tu respuesta
          ...

Tú      → "P1: PYMEs 1k-10k facturas/mes
            P2: nro factura + cliente_id
            P3: solo flag
            P4: 90 días
            P5: email + notif interna Perfex"

Bot     → ⏳ Consolidando brief…
Bot     → ✅ Brief listo
          Proyecto: perfex-dup-facturas
          Stack: Perfex
          Carpeta: /Users/datacole/proyectos/perfex-dup-facturas

          /verbrief para verlo completo.
          Próximo paso (Fase 2): /arrancar perfex-dup-facturas
```

## Comandos

| Comando | Cuando se usa |
|---------|---------------|
| `/nuevo` | Iniciar proyecto (idle → awaiting_prompt) |
| `/cancelar` | Abortar proyecto en curso, volver a idle |
| `/proyectos` | Listar todos los briefs guardados |
| `/verbrief [slug]` | Ver brief completo (último activo si no se da slug) |
| `/estado` | Salud del bot + estado de tu sesión |

## Estructura generada

```
~/proyectos/<slug>/
├── prompt-original.md    # lo que mandaste al inicio (literal, auditable)
├── intake.json           # análisis de Claude: stack, nombre, slug, preguntas
├── respuestas.json       # tus respuestas tal como las recibí
└── brief.md              # el contrato consolidado (11 secciones)
```

### brief.md — 11 secciones

1. Pitch original literal
2. Interpretación consolidada
3. Público target
4. Diferenciadores vs competencia
5. Stack confirmado
6. Alcance v1.0 (qué SÍ)
7. Fuera de alcance v1.0 (qué NO)
8. **Matriz base §3** (i18n, fullscreen, notif, user panel, footer version,
   sidebar colapsable, dark/light/auto, responsive) — siempre incluida
9. Preguntas y respuestas del intake
10. Acceptance Criteria
11. Próximo paso

## Estado de sesiones

Persistido en `telegram-bot/state/sessions.json`. Formato por user_id:

```json
{
  "1412094786": {
    "estado": "awaiting_answers",
    "proyecto_slug": "perfex-dup-facturas",
    "proyecto_dir": "/Users/datacole/proyectos/perfex-dup-facturas",
    "prompt_original": "Quiero un módulo Perfex…",
    "stack_detectado": "Perfex",
    "nombre_sugerido": "Perfex Duplicate Invoice Detector",
    "preguntas": [{ "id": "P1", "texto": "…" }],
    "iniciado_en": "2026-06-05T01:30:00+00:00",
    "actualizado_en": "2026-06-05T01:35:42+00:00"
  }
}
```

Estados:
- `idle` — sin proyecto activo. Mensajes libres van a `claude -p` directo (Fase 0).
- `awaiting_prompt` — el bot pidió el prompt y lo está esperando.
- `awaiting_answers` — el bot mandó las preguntas y espera respuestas.
- `done` — brief consolidado. Siguiente `/nuevo` arranca otro.

## Modo libre coexiste con intake

Si estás en `idle` o `done`, cualquier texto sigue funcionando como Fase 0:
pasa directo a `claude -p`. El intake solo se activa con `/nuevo`.

## Parseo de respuestas

El bot acepta varios formatos en el mensaje de respuestas:

```
P1: respuesta uno
P2: respuesta dos
```

```
P1 - respuesta uno
P2 - respuesta dos
```

```
1. respuesta uno
2. respuesta dos
```

Si das N líneas y hay N preguntas, las asigna en orden por fallback.

Si te falta alguna, el bot avisa cuál y te pide reenviar todas en un mensaje.

## Próximo — Fase 2

Cuando tengas un brief listo:

```
/arrancar <slug>
```

(pendiente de implementar)

Esto invocará al architect del stack detectado, luego al builder, y empezará a
construir el producto en `/work/<slug>/` para validación posterior.
