# Trip Safety & Compliance Audit Engine: ER & Architecture Diagrams

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
  users ||--o| employees : has
  users ||--o| drivers : has
  drivers ||--o{ trips : drives
  vehicles ||--o{ trips : used_in
  trips ||--|{ stops : has
  employees ||--o{ stops : boards
  trips ||--o{ gps_fixes : emits
  trips ||--o{ otp_events : records
  stops ||--o{ otp_events : for
  trips ||--o{ sos_events : records
  trips ||--o{ violations : raises
  violations ||--o{ notification_outbox : queues
  trips ||--o{ audit_log : tracks
```

### Table Definitions Summary
- **`users`**: System identities with RBAC roles (`ADMIN`, `APPROVER`, `DRIVER`, `EMPLOYEE`).
- **`employees`**: Employee profiles (`user_id`, `name`, `gender`, `phone`).
- **`drivers`**: Driver profiles (`user_id`, `name`, `license_no`).
- **`vehicles`**: Vehicle information (`reg_no`, `model`).
- **`trips`**: Trip master records (`planned_route`, `segment_speed_limits`, `default_speed_limit_kmph`, `status`, `escort_assigned`, `requires_escort`).
- **`stops`**: Pickups and drops per trip (`sequence`, `type`, `employee_id`, `planned_time`, `actual_time`, `lat`, `lng`, `status`, `otp_failures`).
- **`gps_fixes`**: Raw GPS pings (`trip_id`, `ts`, `lat`, `lng`, `speed_kmph`).
- **`otp_events`**: Drop OTP verification audit trail (`attempt_no`, `success`, `ts`). *No OTP values stored.*
- **`sos_events`**: Panic alarms triggered by passengers (`employee_id`, `location_source`, `lat`, `lng`, `ts`).
- **`violations`**: Immutable safety violations (`trip_id`, `type`, `severity`, `dedupe_key`, `subject_key`, `details`, lifecycle fields).
- **`notification_outbox`**: Transactional outbox records for alerts (`violation_id`, `channel`, `payload_json`, `status`).
- **`audit_log`**: Append-only tamper-evident hash-chained audit ledger (`seq`, `ts`, `actor`, `action`, `entity_type`, `prev_hash`, `entry_hash`).

---

## 2. Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Clients["Clients & Ingestion"]
        Driver["Driver / GPS Device"]
        Employee["Employee App"]
        Admin["Admin / Approver Portal"]
    end

    subgraph API["FastAPI Edge Layer"]
        AuthRoute["POST /auth/login"]
        TripRoute["POST /trips\nPOST /trips/{id}/gps\nPOST /trips/{id}/complete"]
        EventRoute["POST /trips/{id}/stops/{sid}/otp\nPOST /trips/{id}/sos"]
        AuditRoute["POST /trips/{id}/audit\nGET /audit/verify"]
        Middleware["RequestIdMiddleware + MetricsMiddleware"]
    end

    subgraph Services["Core Application Layer"]
        TripSvc["trip_service"]
        OtpSvc["otp_service"]
        SosSvc["sos_service"]
        CtxBuilder["context_builder"]
        AuditEngine["audit_engine"]
        ViolSvc["violation_service"]
        AuditLogSvc["audit_log_service"]
    end

    subgraph Caches["In-Memory Cache (TTL)"]
        RouteCache[("route_cache\n(Polyline, limits)")]
        EmpCache[("employee_cache\n(EmployeeDTO)")]
    end

    subgraph PureRules["Pure Domain Rules Engine (app/rules)"]
        NightRule["NightSafetyRule"]
        DevRule["RouteDeviationRule"]
        SpeedRule["OverSpeedRule"]
        OtpRule["OtpDropRule"]
        SosRule["SosRule"]
    end

    subgraph Actions["Action & Notification Layer"]
        ActionRouter["ActionRouter\n(Severity -> Channels)"]
        StateAction["RequireEscortAction"]
        OutboxDisp["OutboxDispatcher"]
    end

    subgraph Database["SQLite Database (WAL + Triggers)"]
        DB[(data/app.db)]
        ImmutTriggers["Immutability Triggers\n(audit_log, violations)"]
    end

    %% Flows
    Clients --> Middleware --> API
    TripRoute --> TripSvc
    EventRoute --> OtpSvc
    EventRoute --> SosSvc
    AuditRoute --> AuditEngine

    TripSvc --> DB
    AuditEngine --> CtxBuilder
    CtxBuilder <--> RouteCache
    CtxBuilder <--> EmpCache
    CtxBuilder --> PureRules
    PureRules --> ViolSvc

    OtpSvc --> ViolSvc
    SosSvc --> ViolSvc

    ViolSvc --> ActionRouter
    ActionRouter --> StateAction --> DB
    ActionRouter --> DB
    ViolSvc --> AuditLogSvc --> DB
    ViolSvc --> OutboxDisp
```
