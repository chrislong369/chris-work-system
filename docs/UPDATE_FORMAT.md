# ChatGPT Update Packet Format

Paste one JSON object per line into `data/imports/chatgpt_updates.jsonl`. Use a unique `update_id` when possible. Only packets with `"approval_status": "approved"` affect ledger totals.

## Job Update

```json
{"update_id":"job-20260615-funkel","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Worked 3.25 hours for Funkel and spent $25 on mulch.","update_type":"job_update","customer":"Funkel","job_name":"Mulch and irrigation","work_date":"2026-06-15","hours":3.25,"hourly_rate":40,"expense_amount":25,"expense_description":"mulch","reimbursable":true,"work_completed_notes":"Front-right bed mulched.","remaining_task":"Buy 2-3 more small bags.","calendar_needed":false,"approval_status":"approved","notes":""}
```

## Expense

```json
{"update_id":"expense-20260615-funkel","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Bought $25 of mulch for Funkel.","update_type":"expense","customer":"Funkel","job_name":"Mulch and irrigation","work_date":"2026-06-15","expense_amount":25,"expense_description":"mulch","reimbursable":true,"reimbursed":false,"vendor":"","approval_status":"approved","notes":""}
```

## Payment

```json
{"update_id":"payment-20260615-funkel","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Funkel paid $155 cash.","update_type":"payment","customer":"Funkel","job_name":"Mulch and irrigation","work_date":"2026-06-15","payment_amount":155,"payment_method":"cash","approval_status":"approved","notes":""}
```

## Task

```json
{"update_id":"task-20260615-funkel","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Need 2-3 more bags of mulch for Funkel.","update_type":"task","customer":"Funkel","job_name":"Mulch and irrigation","task":"Buy 2-3 more small bags of mulch.","due_date":"","priority":"normal","approval_status":"approved","notes":""}
```

## Schedule

```json
{"update_id":"schedule-20260616-nate","created_at":"2026-06-15T18:00:00-04:00","source":"ChatGPT","raw_text":"Nate scheduled in Allentown from 8 AM to 4 PM.","update_type":"schedule","customer":"Nate","job_name":"Allentown side work","calendar_needed":true,"calendar_title":"Nate - Allentown side work","calendar_date":"2026-06-16","calendar_start_time":"08:00","calendar_end_time":"16:00","calendar_location":"Allentown, PA","calendar_event_id":"","approval_status":"approved","notes":""}
```

Include `calendar_event_id` when ChatGPT already created the Google Calendar event. Do not include Google Meet links.

## Correction

```json
{"update_id":"correction-20260615-funkel","created_at":"2026-06-15T18:10:00-04:00","source":"ChatGPT","raw_text":"Correction: the mulch was already reimbursed, so remove the $25 owed.","update_type":"correction","customer":"Funkel","job_name":"Mulch and irrigation","work_date":"2026-06-15","correction_reason":"Mulch reimbursed already","adjustment_amount":-25,"approval_status":"approved","notes":""}
```

Corrections create visible adjustment transactions. They do not delete old history.
