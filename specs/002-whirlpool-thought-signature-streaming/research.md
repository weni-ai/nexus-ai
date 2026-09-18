# Research: Whirlpool Thought-Signature Streaming

## Release blast radius

### Decision

Neither 3.7.12 nor 3.7.13 shows evidence of breaking existing non-Whirlpool traffic.

### Evidence

- `3.7.11..3.7.12` changes only the Whirlpool model, Whirlpool translation, and Whirlpool translation tests. The custom model is selected through `resolve_custom_model(..., model_vendor=...)`; OpenAI, `aws_mantle`, and LiteLLM resolution remain outside this adapter.
- `3.7.12..3.7.13` changes only `Project.rationale_switch` from a default of false to true, its `AlterField` migration, and one project-creation test. The migration changes the database default; it does not update existing project rows.
- Sentry issue NEXUS-2WF has 70 occurrences and all 70 carry project UUID `f2c1960a-27b7-438c-8a88-5af49c9e704a`, the Whirlpool production project.
- Around the 3.7.13 commit boundary (2026-09-17 20:29:09 UTC), equal 12-hour Sentry windows excluding the Whirlpool UUID contain 5,130 production errors before and 3,288 after. The post-boundary dominant issues are established unrelated groups (content-base relation, malformed strings, model 404s, dispatch errors); no missing-thought-signature group appears outside Whirlpool.

### Qualification

3.7.13 intentionally enables rationale by default for newly created projects, so it has global future-project behavior scope. That is not evidence of a deployed regression in existing traffic and is unrelated to Whirlpool translation.

### Production rollback (operator, 2026-09-18)

Production was moved from **3.7.13** back to **3.7.11** so users stopped seeing errors. 3.7.12 was the Whirlpool thought-signature converter deploy; 3.7.13 was an outside change.

That rollback undoes **both** tags at once, so “errors stopped after leaving 3.7.13” does not uniquely prove 3.7.13 broke existing non-Whirlpool traffic:

- Runtime reads `project.rationale_switch` from the stored project row / cache (`pre_generation_service` → `CachedProjectData`). The 3.7.13 migration only `AlterField`s the **column default**; it does not `UPDATE` existing rows.
- 3.7.12 only touched Whirlpool adapter files. NEXUS-2WF (`thought_signature`) first appeared **2026-09-16**, before 3.7.12, and is still Whirlpool-only. Rolling to 3.7.11 does not remove that Gemini requirement.
- Sentry still recorded NEXUS-2WF events on 2026-09-18 (including after 13:00 UTC). Non-Whirlpool production errors continue at baseline volume after the rollback.

If a later deploy of this branch is cut from `origin/main`, it **re-includes 3.7.13**. To keep production on 3.7.11 behavior except the Whirlpool streaming fix, cherry-pick onto 3.7.11 (or 3.7.12) instead of merging current `main`.

## Stream metadata preservation

### Decision

Pass a Gemini-only converter hint from `WhirlpoolModel`, while retaining the real custom HTTP model id for tracing and provider calls.

### Rationale

The Agents SDK copies `extra_content.google.thought_signature` only when the converter model id contains `gemini`. `custom/whirlpool/generateContent` does not satisfy that gate. A local hint (`gemini-whirlpool`) activates SDK conversion without changing routing or the gateway model id.

The synthesized stream must use a tool-call delta type that can carry `extra_content`; the stock OpenAI delta drops it.

### Alternatives rejected

- Rename the Whirlpool HTTP model id to include `gemini`: mixes SDK behavior with routing identity and can affect provider selection/tracing.
- Patch the SDK globally: broadens the release and affects other model vendors.
- Bypass `Runner.run_streamed`: diverges Whirlpool from the shared manager execution path.

## Unsigned function calls

### Decision

Use base64 of `skip_thought_signature_validator` only when no real signature exists.

### Rationale

Injected context and pre-fix Redis sessions contain calls Gemini never signed. They cannot echo a real signature. The sentinel is an explicit compatibility path, not a replacement for preserving real response metadata.

## Parallel function results

### Decision

Group adjacent tool outputs from one assistant call round into one Gemini user turn.

### Rationale

Gemini expects all function-call parts followed by all corresponding function-response parts. One user turn per tool output creates an invalid interleaving for parallel calls.

## Instruction path

### Finding

The adapter does not replace project instructions. `OpenAITeamAdapter` builds the shared manager prompt and passes it as `system_instructions`; `WhirlpoolModel._complete` maps that leading system message to Gemini `systemInstruction`.

Production content still needs verification because logs may reflect configuration or preview override differences. No instruction code change is justified by the current evidence.
