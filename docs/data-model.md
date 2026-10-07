# Data Model (draft)

All tables include `id` (UUID), `created_at`, `updated_at`. Tenant-scoped tables include
`organization_id`; contract-scoped tables also include `workspace_id`.

## Tenancy & access

| Entity                  | Key fields                                                                                                | Notes                                                   |
| ----------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **Organization**        | name, kind (`company` / `holding` / `law_firm`), default_timezone, default_country, plan                  | The paying tenant                                       |
| **Workspace**           | organization_id, parent_workspace_id?, name, kind (`client` / `entity` / `department`), country, timezone | Hard access boundary; nestable (holding → subsidiaries) |
| **User**                | auth_provider_id, email, name, timezone                                                                   | Identity from Clerk                                     |
| **Membership**          | user_id, organization_id, org_role (`owner` / `admin` / `member`)                                         |                                                         |
| **WorkspaceMembership** | user_id, workspace_id, role (`admin` / `editor` / `viewer`)                                               | Ethical walls: no membership → no access                |

## Contracts & documents

| Entity             | Key fields                                                                                                                                                                                                                                | Notes                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Counterparty**   | workspace_id, name, aliases, country, notice_address, contacts                                                                                                                                                                            |                                          |
| **ContractFamily** | workspace_id, title                                                                                                                                                                                                                       | Groups master + amendments + SOWs        |
| **Contract**       | family_id, workspace_id, counterparty_id, title, type, role (`customer`/`supplier`/`other`), status (`draft`/`active`/`expired`/`terminated`), effective_date, end_date, auto_renews, governing_law, value, currency, owner_user_id, tags | Effective (post-amendment) view of terms |
| **Document**       | contract_id, kind (`original`/`amendment`/`sow`/`side_letter`/`notice`), storage_key, filename, mime, sha256, page_count, processing_status, amends_document_id?                                                                          | One contract can have many documents     |
| **Clause**         | document_id, number, heading, text, page_start, page_end, bboxes, embedding (vector)                                                                                                                                                      | Unit of citation                         |

## Extraction results

Every extracted item shares: `source_clause_ids[]`, `confidence` (0–1),
`review_status` (`ai_suggested` / `confirmed` / `edited` / `rejected`), `reviewed_by`,
`reviewed_at`, `extraction_run_id`.

| Entity             | Key fields                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Notes                                                                       |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **ExtractionRun**  | document_id, model, prompt_version, started_at, finished_at, status, token_usage                                                                                                                                                                                                                                                                                                                                                                            | Reproducibility & evals                                                     |
| **ExtractedField** | contract_id, field_key, value (JSON)                                                                                                                                                                                                                                                                                                                                                                                                                        | Metadata such as parties, governing law, liability cap                      |
| **DateRule**       | contract_id, rule_type (`expiry` / `renewal` / `notice_non_renewal` / `termination_notice` / `option_window` / `price_review` / `warranty_end` / `insurance_expiry` / `guarantee_expiry` / `lock_in_end` / `post_term_obligation` / `custom`), anchor (`fixed_date` / `term_end` / `effective_date` / other rule), offset (value + unit: days/weeks/months/years), direction (before/after), day_basis (`calendar`/`business`), holiday_country, recurrence | Machine-readable rule extracted by AI                                       |
| **Deadline**       | date_rule_id, contract_id, workspace_id, due_date, window_start?, derivation_text, owner_user_id, backup_user_id, status (`open` / `acknowledged` / `decided` / `missed` / `void`), decision (`renew` / `renegotiate` / `terminate` / `let_expire`), decision_note, evidence_document_id                                                                                                                                                                    | Concrete computed date; recomputed when rules change or the contract renews |
| **PaymentTerm**    | contract_id, direction (`receivable`/`payable`), amount, currency, frequency, payment_days, escalation (type, rate/index, date), late_interest                                                                                                                                                                                                                                                                                                              |                                                                             |
| **PaymentEvent**   | payment_term_id, kind (`invoice_issue`/`invoice_expected`/`payment_due`), due_date, amount, status                                                                                                                                                                                                                                                                                                                                                          | Generated schedule                                                          |
| **Obligation**     | contract_id, party (`us`/`counterparty`), description, recurrence, next_due_date, status                                                                                                                                                                                                                                                                                                                                                                    | Phase 2                                                                     |
| **RiskFlag**       | contract_id, category, severity, explanation                                                                                                                                                                                                                                                                                                                                                                                                                |                                                                             |

## Alerts

| Entity             | Key fields                                                                                                                            | Notes                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **ReminderPolicy** | scope (org / workspace / user), applies_to (deadline type), offsets_days[], channels[]                                                | Defaults + overrides      |
| **Reminder**       | target (deadline_id or payment_event_id), user_id, fire_at, channel, status (`scheduled`/`sent`/`snoozed`/`cancelled`), snooze_reason | Materialised by scheduler |
| **Notification**   | user_id, type, payload, read_at                                                                                                       | In-app inbox              |
| **CalendarFeed**   | user_id, secret_token, scope                                                                                                          | Private iCal URL          |

## AI chat

| Entity          | Key fields                                                                                | Notes |
| --------------- | ----------------------------------------------------------------------------------------- | ----- |
| **ChatThread**  | user_id, scope (contract / family / workspace / organization), scope_id, title            |       |
| **ChatMessage** | thread_id, role, content, citations (JSON → clause ids / page ranges), model, token_usage |       |

## Audit

| Entity         | Key fields                                                                                                             | Notes       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------- |
| **AuditEvent** | organization_id, workspace_id?, actor_user_id, action, entity_type, entity_id, before/after (JSON), ip, user_agent, at | Append-only |

## Relationships (summary)

```
Organization 1─* Workspace 1─* ContractFamily 1─* Contract 1─* Document 1─* Clause
                     │                              │
                     └─* Counterparty ──────────────┘
Contract 1─* DateRule 1─* Deadline 1─* Reminder
Contract 1─* PaymentTerm 1─* PaymentEvent 1─* Reminder
Contract 1─* ExtractedField / Obligation / RiskFlag
User *─* Workspace (WorkspaceMembership)
```

## Amendments

| Entity                    | Key fields                                                                                                                               | Notes                                                                                            |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Amendment**             | contract_id, title, effective_date, signed_date, description                                                                             | Its changes are applied to the contract, which always shows the terms in force                   |
| **AmendmentChange**       | amendment_id, target_type (`contract` / `date_rule` / `payment_term`), target_id, field (`_created` for additions), old_value, new_value | Used for the before → after history and to revert; a value changed again since is never reverted |
| **Document.amendment_id** | —                                                                                                                                        | Amendment documents are stored with the contract but not treated as its main document            |
