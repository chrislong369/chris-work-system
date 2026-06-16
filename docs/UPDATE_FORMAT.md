# ChatGPT Update Packet Format

Paste one JSON object per line into `data/imports/chatgpt_updates.jsonl`. Use a unique `update_id` when possible. Only packets with `"approval_status": "approved"` affect ledger totals.

Use `customer` or `customer_name` for local/private packets. Public GitHub inbox packets should use `customer_code` and rely on the local-only `data/private_customer_map.csv` file to resolve the real customer name.

## Job Update

```json
{"update_id":"job-20260615-funfgeld","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Worked 3.25 hours for Funfgeld and spent $25 on mulch.","update_type":"job_update","customer":"Funfgeld","job_name":"Mulch and irrigation","work_date":"2026-06-15","hours":3.25,"hourly_rate":40,"expense_amount":25,"expense_description":"mulch","reimbursable":true,"work_completed_notes":"Front-right bed mulched.","remaining_task":"Buy 2-3 more small bags.","calendar_needed":false,"approval_status":"approved","notes":""}
```

## Expense

```json
{"update_id":"expense-20260615-funfgeld","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Bought $25 of mulch for Funfgeld.","update_type":"expense","customer":"Funfgeld","job_name":"Mulch and irrigation","work_date":"2026-06-15","expense_amount":25,"expense_description":"mulch","reimbursable":true,"reimbursed":false,"vendor":"","approval_status":"approved","notes":""}
```

## Payment

```json
{"update_id":"payment-20260615-funfgeld","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Funfgeld paid $155 cash.","update_type":"payment","customer":"Funfgeld","job_name":"Mulch and irrigation","work_date":"2026-06-15","payment_amount":155,"payment_method":"cash","approval_status":"approved","notes":""}
```

## Task

```json
{"update_id":"task-20260615-funfgeld","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Need 2-3 more bags of mulch for Funfgeld.","update_type":"task","customer":"Funfgeld","job_name":"Mulch and irrigation","task":"Buy 2-3 more small bags of mulch.","due_date":"","priority":"normal","approval_status":"approved","notes":""}
```

Task packets and `remaining_task` fields also create or update `data/outstanding_jobs.csv` unless the work is completed, cancelled, scheduled, or parked until a future follow-up date.

## Outstanding / Unscheduled Backlog

Use this for a mentioned job, lead, follow-up, or loose task that is not completed and not on the calendar yet.

```json
{"update_id":"backlog-20260615-example-follow-up","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"I still need to reach out to the customer about the remaining cleanup.","update_type":"backlog","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","backlog_status":"needs follow-up","backlog_priority":"medium","next_action":"Text the customer and ask what day works.","due_target":"","preferred_timing":"this week","parked_until":"","approval_status":"approved","notes":""}
```

Supported backlog statuses:

- `lead`
- `needs follow-up`
- `needs scheduling`
- `scheduled`
- `in progress`
- `blocked`
- `completed`
- `cancelled`

The importer also detects natural-language phrases in approved packets, including `I still need to`, `remind me`, `I have to reach out`, `not scheduled yet`, `potential job`, `Ken mentioned`, and `needs to get done`.

Use `parked_until` only when the item should intentionally disappear from the daily Dashboard until a future follow-up date.

## Backlog Update Actions

Use structured update packets for backlog state changes. ChatGPT can convert natural language into these packets, but the importer relies on the structured fields.

### Mark Completed

```json
{"update_id":"backlog-update-20260615-example-completed","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"mark_completed","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","completed_date":"2026-06-15","approval_status":"approved","notes":"Customer confirmed no more work is needed."}
```

### Mark Scheduled

```json
{"update_id":"backlog-update-20260615-example-scheduled","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"mark_scheduled","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","scheduled_date":"2026-06-18","calendar_event_id":"","approval_status":"approved","notes":"Scheduled on the side-work calendar."}
```

### Mark Cancelled

```json
{"update_id":"backlog-update-20260615-example-cancelled","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"mark_cancelled","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","approval_status":"approved","notes":"Customer declined the work."}
```

### Park Until Date

```json
{"update_id":"backlog-update-20260615-example-parked","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"park_until_date","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","parked_until":"2026-06-22","next_action":"Follow up after the customer returns.","approval_status":"approved","notes":""}
```

### Change Priority

```json
{"update_id":"backlog-update-20260615-example-priority","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"change_priority","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","backlog_priority":"high","approval_status":"approved","notes":"Customer asked to handle this sooner."}
```

### Add Follow-Up Note

```json
{"update_id":"backlog-update-20260615-example-note","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","update_type":"backlog_update","backlog_action":"add_follow_up_note","customer":"Example Customer","job_name":"Cleanup follow-up","task_description":"Reach out about remaining cleanup.","next_action":"Wait for customer reply.","approval_status":"approved","notes":"Texted customer and waiting on response."}
```

## Lead

Use this when the customer or details are not fully known yet.

```json
{"update_id":"lead-20260615-example-referral","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Potential job from a referral: shelf removal and rug move. Details unclear.","update_type":"lead","customer":"","job_name":"Referral shelf/rug job","task_description":"Confirm referral customer name, contact info, address, scope, and preferred timing.","backlog_status":"lead","backlog_priority":"low-medium","next_action":"Ask the referrer for customer name, contact info, address, scope, and preferred timing.","approval_status":"approved","notes":""}
```

## Schedule

```json
{"update_id":"schedule-20260616-nate","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Nate scheduled in Allentown from 8 AM to 4 PM.","update_type":"schedule","customer":"Nate","job_name":"Allentown side work","calendar_needed":true,"calendar_title":"Nate - Allentown side work","calendar_date":"2026-06-16","calendar_start_time":"08:00","calendar_end_time":"16:00","calendar_location":"Allentown, PA","calendar_event_id":"","approval_status":"approved","notes":""}
```

Include `calendar_event_id` when ChatGPT already created the Google Calendar event. Do not include Google Meet links.

## Correction

```json
{"update_id":"correction-20260615-funfgeld","created_at":"2026-06-15T18:10:00-04:00","source":"ChatGPT","raw_text":"Correction: the mulch was already reimbursed, so remove the $25 owed.","update_type":"correction","customer":"Funfgeld","job_name":"Mulch and irrigation","work_date":"2026-06-15","correction_reason":"Mulch reimbursed already","adjustment_amount":-25,"approval_status":"approved","notes":""}
```

Corrections create visible adjustment transactions. They do not delete old history.
