"""
Contexto rico por stack — para que el intake NO haga preguntas obvias.

Cada constante describe qué TRAE de fábrica el stack, qué patrones de módulo
se esperan, y qué tipo de preguntas SÍ son útiles (las que clarifican el
módulo NUEVO sin re-preguntar lo que ya está resuelto en el stack base).

Usado por intake.py para enriquecer el prompt al LLM antes de generar preguntas.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────
# Perfex CRM (PHP + CodeIgniter 3)
# ─────────────────────────────────────────────────────────────────────────


PERFEX_CONTEXT = """\
Perfex CRM es un CRM PHP open-source basado en CodeIgniter 3.

============================================================
PERFEX YA TRAE (no preguntes por esto, ya está resuelto):
============================================================

ENTIDADES NATIVAS (tablas con prefijo `tbl`):
- customers (con contacts asociados)
- leads (con conversión a customer)
- staff (con roles + permissions granulares por feature)
- departments
- items (productos/servicios con precio, tax, etc.)
- invoices, estimates, proposals (con statuses, templates PDF, recurring)
- payments, credit_notes, subscriptions
- expenses (con recurring incluido)
- contracts (con renewal automático)
- tasks, projects (con time tracking, milestones)
- tickets (sistema de soporte completo con departments)
- calendar, events, reminders
- knowledge_base
- goals, surveys, news (feed)
- custom_fields (en cualquier entidad principal)
- email_templates con merge fields
- contracts y subscriptions

INFRAESTRUCTURA NATIVA:
- Auth multi-rol (admin / staff / customer / contact) con sessions
- Sistema de roles con permissions granulares por feature (view/create/edit/delete)
- Hooks system completo: `after_invoice_added`, `before_lead_converted`,
  `after_payment_recorded`, etc. (más de 100 hooks documentados)
- Email templates con merge fields {customer_company}, {invoice_number}, etc.
- Cron jobs (1 cron line en host → corre tareas recurrentes)
- Multi-language (i18n nativo con archivos en application/language/)
- Themes y customización vía modules
- API REST (en application/controllers/api/)
- File uploads con storage local o S3 configurable
- Backup automático (módulo Backup bundled)
- Search global
- Activity log
- Custom fields system (extiende cualquier tabla principal sin migración)
- Notifications system (campanita arriba)
- Calendar events
- PDF generation (TCPDF integrado)
- SMS gateway (Twilio, MSG91, etc.)

PATRÓN DE MÓDULO PERFEX (vive en `modules/<nombre>/`):
- manifest `<nombre>.php` con headers Module Name/Version/Author
- install.php (idempotente con `IF NOT EXISTS`)
- uninstall.php (limpia SOLO tablas del módulo)
- migrations/ (subir versión sin reinstalar)
- controllers/ (extends `AdminController`, valida `staff_cant()`)
- models/ (extends `App_Model`)
- views/ (≤5 líneas <style>, ≤30 líneas <script> inline)
- language/english/ + language/spanish/ (lang keys obligatorias)
- assets/css/ (scoped `.modulo-*`)
- assets/js/ (`"use strict"` + IIFE + `window.MODULO_NS`)
- Hooks para integrar con entidades existentes (NO modificar core)
- Custom fields si necesita extender entidades
- Permissions registradas con `register_permission()`

PRODUCTO REFERENCIA INTERNO: DupliGuard v1.1.1 (aprobado en CodeCanyon).
Path local: C:\\xampp\\perfex\\modules\\dupliguard\\

============================================================
PREGUNTAS BUENAS para un módulo Perfex (clarifican lo NUEVO):
============================================================

1. Lógica de negocio EXACTA del módulo:
   - "¿La comisión se calcula al MARCAR invoice paid o al CREAR el payment?"
   - "¿Los tramos son por VENTA o por VOLUMEN MENSUAL acumulado?"
   - "¿Las reglas se evalúan en cascada (primer match) o todas (sumadas)?"

2. Integración con entidades core de Perfex:
   - "¿Qué hook dispara el cálculo? (after_payment_added / after_invoice_status_change)"
   - "¿Tabla nueva tblstaff_commissions o custom_field en tblstaff?"
   - "¿Modificas tabla core o solo creas tablas nuevas con FK?"

3. Workflows de aprobación:
   - "¿La liquidación requiere aprobación de admin antes de pagarse?"
   - "¿Hay estados intermedios (calculated → reviewed → approved → paid)?"
   - "¿Auditoría de cambios?"

4. Reportes/Dashboards específicos:
   - "¿Widget en dashboard del staff con su acumulado del mes?"
   - "¿Exportar a Excel/PDF la liquidación mensual?"
   - "¿Reporte comparativo entre vendedores?"

5. Notificaciones específicas:
   - "¿Notificar al vendedor cuando se aprueba? (email + notif Perfex)"
   - "¿Admin recibe alert cuando alguien supera meta?"

6. Diferenciadores comerciales:
   - "¿Qué hace mejor que los módulos existentes en CodeCanyon?"
   - "¿Por qué pagarían USD 40-80 por esto vs hacerlo manual?"

============================================================
PREGUNTAS MALAS (NO HAGAS estas, Perfex ya las resuelve):
============================================================

❌ "¿Cómo manejas la autenticación?" → Perfex tiene auth nativa
❌ "¿Qué tipos de usuarios habrá?" → admin/staff/customer ya existen
❌ "¿Cómo gestionas roles y permisos?" → Sistema de permissions nativo
❌ "¿Qué motor de base de datos?" → Siempre MySQL/MariaDB
❌ "¿Cómo se internacionaliza?" → Sistema i18n nativo con _l()
❌ "¿Qué framework de UI?" → AdminLTE + Bootstrap 3 (no se cambia)
❌ "¿Cómo notificas por email?" → Email templates con merge fields nativos
❌ "¿Cómo se sube archivos?" → File upload nativo de Perfex
❌ "¿Cómo se hace backup?" → Módulo Backup bundled
❌ "¿Habrá API REST?" → Hay API nativa, se extiende si hace falta

============================================================
LO QUE PERFEX NO HACE (sí preguntar):
============================================================

✅ Lógica de negocio específica del dominio del módulo
✅ Cálculos automáticos con reglas configurables
✅ Workflows multi-etapa con aprobaciones
✅ Integraciones con servicios externos específicos
✅ Reportes/dashboards específicos
✅ Custom UI components específicos al módulo
✅ Lógica de notificaciones específicas al módulo
"""


# ─────────────────────────────────────────────────────────────────────────
# WordPress (+ WooCommerce opcional)
# ─────────────────────────────────────────────────────────────────────────


WP_CONTEXT = """\
WordPress + WooCommerce ecosystem.

============================================================
WORDPRESS YA TRAE:
============================================================

CORE:
- Posts, pages, custom post types, taxonomies
- Comments con moderation
- Users + roles (admin/editor/author/contributor/subscriber)
- Media library (uploads + media handling)
- Themes API (templates, hooks, customizer)
- Plugins API (activation/deactivation hooks, options API)
- REST API completa en /wp-json/
- WP-Cron (scheduled tasks)
- i18n con __() y .pot/.po/.mo
- Settings API (admin pages con secciones/fields)
- Transients (cache)
- Capabilities + roles personalizables
- Nonces para CSRF protection
- Sanitization + escape functions

WOOCOMMERCE (si aplica):
- Products (simple, variable, grouped, virtual, downloadable)
- Cart + checkout
- Orders con statuses
- Payment gateways (Stripe, PayPal, etc.)
- Shipping zones + methods
- Taxes
- Coupons
- Reports
- HPOS (High Performance Order Storage)
- Hooks específicos: `woocommerce_order_status_completed`, etc.

PATRÓN DE PLUGIN WORDPRESS:
- vive en `wp-content/plugins/<nombre>/`
- header en archivo principal con Plugin Name, Version, etc.
- activation_hook / deactivation_hook
- uninstall.php para cleanup completo
- includes/ con clases (PSR-4 recomendado)
- assets/ con CSS + JS scoped al plugin
- languages/ con .pot generado
- Cumplir 85 requisitos oficiales de Envato

PRODUCTO REFERENCIA: ReviewPulse AI (WP 7.0 + WooCommerce 10.7).

============================================================
PREGUNTAS BUENAS para un plugin WP:
============================================================

1. Compatibilidad:
   - "¿Compat con WooCommerce HPOS o solo legacy?"
   - "¿Requiere temas Storefront/Botiga o agnóstico?"
   - "¿Multisite supported?"

2. UX en admin:
   - "¿Menu top-level o submenú de Settings?"
   - "¿Settings via Settings API o pantalla custom?"

3. Lógica específica:
   - "¿Frontend output via shortcode, widget, block Gutenberg o las tres?"
   - "¿Backend via metabox en Post edit, screen propio, o ambos?"

4. Integraciones:
   - "¿APIs externas? ¿Qué auth (API key, OAuth)?"
   - "¿Webhooks salientes?"

5. Performance:
   - "¿Cache de algo? (transient, object cache)"
   - "¿Async via WP-Cron o action scheduler?"

============================================================
PREGUNTAS MALAS:
============================================================

❌ "¿Cómo manejas users?" → WP tiene users + capabilities
❌ "¿Cómo guardas settings?" → Options API o Settings API
❌ "¿Cómo gestionas roles?" → Capabilities + roles built-in
❌ "¿Cómo i18n?" → __(), _e(), .pot
❌ "¿Cómo subir archivos?" → Media library
❌ "¿Cómo cron?" → WP-Cron
❌ "¿Database?" → wpdb con $wpdb->prefix
"""


# ─────────────────────────────────────────────────────────────────────────
# Laravel SaaS (Laravel 12 + Livewire + Tailwind v4)
# ─────────────────────────────────────────────────────────────────────────


LARAVEL_CONTEXT = """\
Laravel SaaS standalone (NO Filament, NO Inertia+Vue/React).

Stack canónico: Laravel 12 + PHP 8.2+ + Livewire 3/4 + Tailwind v4 +
Alpine.js + MySQL 8 / MariaDB 10.3+.

============================================================
LARAVEL YA TRAE:
============================================================

CORE:
- Eloquent ORM con relationships
- Migrations + seeders
- Auth (web + API tokens via Sanctum)
- Authorization (Policies + Gates)
- Mail (Mailables) con templates
- Notifications (Database + Mail + SMS providers)
- Queues (database, redis, sync) con Jobs
- Scheduler (artisan schedule:run)
- Cache (file, redis, memcached)
- Sessions (database driver recomendado)
- Validation (Form Requests + inline rules)
- Localization con resources/lang/
- Events + Listeners
- Service Container + Service Providers
- Middleware
- Throttle / Rate Limiting
- File Storage (local, S3)

LIVEWIRE 3/4:
- Componentes reactivos sin escribir JS
- Wire:model, wire:click, wire:loading
- Lifecycle hooks (mount, updated, etc.)
- Computed properties
- Pagination
- File uploads

PATRÓN DE PRODUCTO SAAS LARAVEL (estilo MailTrixy):
- Installer wizard 6 pasos (welcome/requirements/db/app/admin/run)
- Middleware `EnsureInstalled` con `storage/app/installed.lock`
- Vendor + public/build/ pre-compilados en ZIP final
- Multi-idioma EN+ES mínimo desde día 1
- Dark/Light/Auto toggle persistente
- Sidebar colapsable persistente
- Multi-tenant opcional (workspace_id en tablas)
- Section dividers ASCII en PHP
- AUTOMATION_MODE=middleware|queue|scheduler para shared hosting

PRODUCTO REFERENCIA: MailTrixy v1.2 (aprobado en CodeCanyon).

============================================================
PREGUNTAS BUENAS para un SaaS Laravel:
============================================================

1. Multi-tenant:
   - "¿Single tenant o multi-tenant?"
   - "¿Workspace por user o equipos compartidos?"
   - "¿Scope queries por workspace_id?"

2. Pricing y suscripciones:
   - "¿Pricing tiers? ¿Cuántos planes?"
   - "¿Pago via Stripe Subscriptions, Razorpay, manual?"
   - "¿Trial gratis? ¿Cuántos días?"

3. Lógica del dominio:
   - "¿Qué entidades nuevas (no existen en Laravel base)?"
   - "¿Qué services agrupados por dominio (Mail/, Billing/, AI/)?"

4. AI/ML integration:
   - "¿OpenAI, Anthropic, Gemini o agnóstico?"
   - "¿Tokens facturados al cliente o include?"

5. Deployment:
   - "¿Shared hosting (Hostinger/Namecheap) o VPS?"
   - "¿Cron real o middleware-based scheduler?"

============================================================
PREGUNTAS MALAS:
============================================================

❌ "¿Cómo auth?" → Sanctum / sessions
❌ "¿Cómo migrations?" → artisan make:migration
❌ "¿Cómo cron?" → Scheduler
❌ "¿Cómo emails?" → Mailables
❌ "¿Cómo i18n?" → resources/lang/ + __()
❌ "¿Database?" → MySQL 8 / MariaDB con Eloquent
"""


# ─────────────────────────────────────────────────────────────────────────
# CI3 standalone (TicketYA-style)
# ─────────────────────────────────────────────────────────────────────────


CI3_CONTEXT = """\
CodeIgniter 3 standalone (NO Perfex, NO addon — producto independiente).

Stack: CI3 3.1.13 + PHP 7.4-8.4 + MySQL/MariaDB.

============================================================
CI3 STANDALONE TRAE:
============================================================

DEL FRAMEWORK CI3:
- MVC con base Controller / Model / View
- Database class con Query Builder
- Form validation
- Email library
- Sessions (filesystem o database driver)
- Pagination
- Caching (file, redis)
- CSRF protection
- Migrations (opcional)
- Hooks system
- Helpers (url, form, file, etc.)
- i18n con language/<idioma>/<file>_lang.php

LO QUE EL PRODUCTO DEBE CONSTRUIR DESDE CERO (no viene de CI3):
- Subclases de Controller (MY_Controller + Admin_Controller + etc.)
- Sistema de Auth (login/logout/register)
- Sistema de Roles + Permissions
- Installer wizard 5 pasos
- Layout base (admin + público)
- Theme system
- Asset management con cache busting
- Documentation HTML bundle
- Demo data realista

PRODUCTO REFERENCIA: TicketYA v1.0.0
Path: D:\\laragon-6.0.0\\www\\support

============================================================
PREGUNTAS BUENAS para producto CI3:
============================================================

1. Dominio del negocio:
   - "¿Qué entidades core del producto? (ej. tickets, customers, agents)"
   - "¿Cuántos roles? (super admin / admin / agent / customer)"

2. Funcionalidad clave:
   - "¿Public-facing form (sin login) o solo backend?"
   - "¿Frontend público con custom domain o solo admin?"

3. Persistencia:
   - "¿Schema.sql baseline o migrations escalables?"
   - "¿Soft deletes o hard deletes?"

4. Integraciones:
   - "¿SMTP custom o servicios (SendGrid, Mailgun)?"
   - "¿Notificaciones internas en BD o sólo email?"

5. UX:
   - "¿Dashboards por rol?"
   - "¿Search global?"
"""


# ─────────────────────────────────────────────────────────────────────────
# Node.js / Next.js (Framecast-style)
# ─────────────────────────────────────────────────────────────────────────


NODE_CONTEXT = """\
Node.js moderno: Next.js App Router + TypeScript + Supabase + Tailwind/shadcn.

Stack: Next.js 16 + React 19 + TS 5.9 strict + Supabase + next-intl + Fumadocs.

============================================================
EL STACK YA TRAE:
============================================================

NEXT.JS APP ROUTER:
- Server Components default
- Server Actions
- Route handlers (app/api/)
- Middleware (auth, i18n, rate limit)
- Streaming + Suspense
- Generation: SSG / SSR / ISR
- Built-in Image optimization
- Built-in Font optimization

SUPABASE:
- Auth con providers (Email, Google, Magic Link, etc.)
- Postgres con RLS (Row Level Security)
- Realtime subscriptions
- Storage (S3-compatible)
- Edge Functions

ECOSYSTEM:
- shadcn/ui (componentes via CLI)
- Tailwind 4 con @theme tokens
- next-intl para i18n (≥2 idiomas)
- Fumadocs para `/docs` in-product
- Zod para validation
- React Hook Form
- Vitest + Playwright para tests

PATRÓN DE PRODUCTO NODE:
- 3 entornos: Local / Vercel / Custom Server (Docker)
- TypeScript strict 100%
- Env vars validadas con Zod en lib/env.ts
- RLS en TODAS las tablas Supabase
- `import "server-only"` en lib/ con secrets
- Cero `console.log` en producción
- Documentación: README + Quick Start PDF + Fumadocs

PRODUCTO REFERENCIA: Framecast AI (Next.js 16 + Supabase + Stripe/PayPal/Razorpay/Flutterwave).

============================================================
PREGUNTAS BUENAS para producto Node:
============================================================

1. Backend de datos:
   - "¿Supabase managed o self-hosted? ¿Edge functions o solo Postgres?"
   - "¿RLS policies por tenant_id o por user_id?"

2. Pagos:
   - "¿Stripe Subscriptions, Razorpay, multi-gateway?"
   - "¿Trial gratis? ¿Webhooks signature verify?"

3. AI/ML:
   - "¿OpenAI, Anthropic, Gemini o agnóstico via Vercel AI SDK?"
   - "¿Streaming responses al UI?"

4. Deployment:
   - "¿Solo Vercel o también Docker self-hosted?"
   - "¿Custom server con cron real o solo Vercel cron?"

5. UI:
   - "¿shadcn vanilla o custom theme?"
   - "¿Dark/Light/Auto?"
"""


# ─────────────────────────────────────────────────────────────────────────
# Genérico (sin stack detectado o "Otro")
# ─────────────────────────────────────────────────────────────────────────


GENERIC_CONTEXT = """\
Stack no detectado o "Otro". El usuario probablemente sabe qué quiere construir
pero no especificó stack. Tu prioridad es entender el dominio antes que la
tecnología.

============================================================
PREGUNTAS BUENAS:
============================================================

1. Stack preferido:
   - "¿Hay restricción de stack? (PHP/Perfex, Node/Next, Laravel, WP, otro)"
   - "¿Lo va a self-hostear o vender en marketplace tipo CodeCanyon?"

2. Audiencia:
   - "¿B2B, B2C, o internal tool?"
   - "¿Tamaño de empresas target?"

3. Modelo:
   - "¿One-time sale, subscription, freemium?"
   - "¿Multi-tenant SaaS o single instance?"

4. Funcionalidad core:
   - "¿Qué entidades principales del dominio?"
   - "¿Workflows principales paso a paso?"

5. Integraciones críticas:
   - "¿Qué servicios externos imprescindibles?"
"""


# ─────────────────────────────────────────────────────────────────────────
# Mapping stack → contexto
# ─────────────────────────────────────────────────────────────────────────


STACK_CONTEXTS: dict[str, str] = {
    "Perfex": PERFEX_CONTEXT,
    "WP": WP_CONTEXT,
    "Laravel": LARAVEL_CONTEXT,
    "CI3": CI3_CONTEXT,
    "Node": NODE_CONTEXT,
    "Otro": GENERIC_CONTEXT,
}


def get_context_for_stack(stack: str | None) -> str:
    """Devuelve el contexto del stack. Fallback a GENERIC_CONTEXT."""
    if not stack:
        return GENERIC_CONTEXT
    return STACK_CONTEXTS.get(stack, GENERIC_CONTEXT)


def all_stacks() -> list[str]:
    return list(STACK_CONTEXTS.keys())
