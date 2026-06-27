# Graph Report - .  (2026-06-23)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 176 nodes · 327 edges · 14 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `09c1a303`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Frontline Operations Portal|Frontline Operations Portal]]
- [[_COMMUNITY_Invoice Management Flow|Invoice Management Flow]]
- [[_COMMUNITY_Guard Payroll & Roles|Guard Payroll & Roles]]
- [[_COMMUNITY_User Authentication & MFA|User Authentication & MFA]]
- [[_COMMUNITY_Roster Scheduling Management|Roster Scheduling Management]]
- [[_COMMUNITY_Site Shift Management|Site Shift Management]]
- [[_COMMUNITY_Dashboard UI Templates|Dashboard UI Templates]]
- [[_COMMUNITY_Base UI & Guard Templates|Base UI & Guard Templates]]
- [[_COMMUNITY_App Config & Metrics|App Config & Metrics]]
- [[_COMMUNITY_Guard Profile Management|Guard Profile Management]]
- [[_COMMUNITY_Auth UI & Theme Toggle|Auth UI & Theme Toggle]]
- [[_COMMUNITY_Frontline Portal Templates|Frontline Portal Templates]]
- [[_COMMUNITY_Payroll Overview UI|Payroll Overview UI]]

## God Nodes (most connected - your core abstractions)
1. `base.html template` - 29 edges
2. `Shift` - 12 edges
3. `User` - 12 edges
4. `Guard` - 11 edges
5. `index.html (Dashboard)` - 11 edges
6. `Site` - 9 edges
7. `frontline/portal.html template` - 9 edges
8. `guards/detail.html template` - 9 edges
9. `_current_site()` - 8 edges
10. `icon_check_circle macro` - 8 edges

## Surprising Connections (you probably didn't know these)
- `new_guard()` --calls--> `Guard`  [EXTRACTED]
  blueprints/guards.py → models.py
- `new_site()` --calls--> `Site`  [EXTRACTED]
  blueprints/sites.py → models.py
- `assign_roster()` --calls--> `Shift`  [EXTRACTED]
  blueprints/sites.py → models.py
- `create_app()` --calls--> `translate()`  [EXTRACTED]
  app.py → i18n.py
- `clock_in()` --calls--> `AttendanceRecord`  [EXTRACTED]
  blueprints/frontline.py → models.py

## Import Cycles
- None detected.

## Communities (14 total, 0 thin omitted)

### Community 0 - "Frontline Operations Portal"
Cohesion: 0.10
Nodes (22): clock_in(), _current_site(), incident_report(), key_issue(), maintenance_log(), parcel_log(), portal(), visitor_sign_in() (+14 more)

### Community 1 - "Invoice Management Flow"
Cohesion: 0.15
Nodes (10): _build_invoice_pdf(), download(), generate(), _next_invoice_number(), _parse_date(), preview(), JSON endpoint: un-invoiced, approved shift hours/total for a site & period., Shift-to-Invoice: Owners and Ops Managers only.      HR/Compliance and all front (+2 more)

### Community 2 - "Guard Payroll & Roles"
Cohesion: 0.19
Nodes (10): approve_payout(), _eligible_shifts(), overview(), _parse_date(), Payroll: Owners and HR/Compliance only., _restrict_to_payroll_roles(), Guard, PayrollPayout (+2 more)

### Community 3 - "User Authentication & MFA"
Cohesion: 0.17
Nodes (6): _complete_login(), login(), mfa(), _post_login_redirect(), User, UserMixin

### Community 4 - "Roster Scheduling Management"
Cohesion: 0.19
Nodes (10): assign(), master(), _parse_date(), _parse_time(), Master Roster: Owners, Ops Managers, and Supervisors only., All staff eligible for the Master Roster grid, tagged by category., _restrict_to_site_management_roles(), _staff_roster() (+2 more)

### Community 5 - "Site Shift Management"
Cohesion: 0.16
Nodes (7): assign_roster(), new_site(), _parse_date(), _parse_time(), Your Sites hub: Owners, Ops Managers, and Supervisors only., _restrict_to_site_management_roles(), Site

### Community 6 - "Dashboard UI Templates"
Cohesion: 0.23
Nodes (14): icon_alert_triangle macro, icon_building macro, icon_calendar macro, icon_plus macro, icon_scale macro, icon_trending_up macro, icon_wallet macro, icon_x_circle macro (+6 more)

### Community 7 - "Base UI & Guard Templates"
Cohesion: 0.28
Nodes (13): icon_arrow_left macro, icon_invoice macro, icon_layout macro, icon_log_out macro, icon_user_check macro, icon_users macro, base.html template, SecOps Hub Application (+5 more)

### Community 8 - "App Config & Metrics"
Cohesion: 0.27
Nodes (8): create_app(), _current_week_range(), _executive_metrics(), Revenue, payroll, profit and weekly staffing snapshot for the executive dashboar, Config, _load(), Tiny JSON-backed i18n helper.  Translation dictionaries live in translations/<la, translate()

### Community 9 - "Guard Profile Management"
Cohesion: 0.31
Nodes (8): edit_guard(), new_guard(), _parse_date(), Guard Profile Vault: HR/Compliance, Ops Managers, and Owners only.      GDPR dat, Save an uploaded guard document, returning its stored filename or None., _restrict_to_hr_roles(), _save_upload(), _validate()

### Community 10 - "Auth UI & Theme Toggle"
Cohesion: 0.29
Nodes (8): icon_moon macro, icon_shield macro, icon_sun macro, auth/_auth_base.html template, auth/login.html template, auth/mfa.html template, Lucide Icon Style (24x24, stroke-width 2, currentColor), Dark/Light Theme Toggle

### Community 11 - "Frontline Portal Templates"
Cohesion: 0.29
Nodes (7): icon_alert_octagon macro, icon_clipboard_check macro, icon_globe macro, icon_key macro, icon_package macro, errors/error.html template, frontline/portal.html template

### Community 12 - "Payroll Overview UI"
Cohesion: 0.67
Nodes (3): icon_check_circle macro, icon_clock macro, payroll/overview.html template

## Knowledge Gaps
- **11 isolated node(s):** `icon_layout macro`, `icon_log_out macro`, `icon_globe macro`, `icon_key macro`, `icon_package macro` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User Authentication & MFA` to `App Config & Metrics`, `Guard Payroll & Roles`, `Roster Scheduling Management`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `Shift` connect `Roster Scheduling Management` to `App Config & Metrics`, `Invoice Management Flow`, `Guard Payroll & Roles`, `Site Shift Management`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `base.html template` connect `Base UI & Guard Templates` to `Auth UI & Theme Toggle`, `Frontline Portal Templates`, `Payroll Overview UI`, `Dashboard UI Templates`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **What connects `Revenue, payroll, profit and weekly staffing snapshot for the executive dashboar`, `Guard Profile Vault: HR/Compliance, Ops Managers, and Owners only.      GDPR dat`, `Save an uploaded guard document, returning its stored filename or None.` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontline Operations Portal` be split into smaller, more focused modules?**
  _Cohesion score 0.10344827586206896 - nodes in this community are weakly interconnected._