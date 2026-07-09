# Research: Project Guardrails Category Configuration

## R1 — Naming: category, not topic or instruction

**Decision**: Domain term **guardrail category**. Settings: `GUARDRAIL_CATEGORY_CATALOG`. Persistence: `category_states`. API/runtime: `categories`.

**Rationale**:

- **Topic** is taken: `Topics` model + `lambda_conversation_topics` classify *conversation content*, user-defined per project.
- **Instruction** is taken: content-base instructions, agent instructions, formatter instructions.
- **Category** matches FDD intent (fixed sensitive *subject categories*) without overloading existing nouns.

**Rejected**: `guardrails_instructions` — reads as prompt text, not a taxonomy of blocked subjects.

---

## R2 — i18n (backend scope)

**Decision**: **No i18n layer in Nexus for this feature.**

- Catalog `name`/`description`: English strings in settings constant.
- Default blocking message: `settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` (single string).
- Custom blocking message: stored as submitted.
- Remove `Accept-Language` from admin API contract.

**Rationale**: Label localization is a presentation concern for API consumers outside this backend scope. Customer-facing default message localization at inference time is owned by Models/runtime contract if needed later — not admin GET i18n.

**Rejected**: T002 locale module task — frontend/i18n pipeline pattern, not Nexus backend responsibility.

---

## R3 — Admin writes, lazy init, runtime (unchanged logic)

See prior decisions: moderator-only PATCH, deploy timestamp defaults, extend `GuardrailsUsecase` with `categories` + `blocking_message`, cache invalidation on PATCH, `confirm_disable` contract (`disable_category` | `disable_all`).
