# Changelog

Sigue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) y [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-06-05

### Added — Fase 0: bridge mínimo

- `telegram-bot/bot.py` — bridge Telegram → `claude -p` → respuesta
- Whitelist por `user_id`
- Comandos `/start` y `/estado`
- Split de respuestas largas (chunks de 4000 chars)
- Timeout configurable (default 300s)
- Logging estructurado
- `.env.example` con todas las variables documentadas
- `.gitignore` cubre secrets, venv, IDE
- README con arquitectura + plan de fases
- `docs/fase-0-bridge.md` con instalación paso a paso
- `scripts/install-mac.sh` instalador idempotente para Mac
