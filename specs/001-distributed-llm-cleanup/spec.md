# Feature Specification: Distributed LLM Inference – Cleanup & Multi-Laptop Setup

**Feature Branch**: `001-distributed-llm-cleanup`
**Created**: 2026-05-09
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 – Run a Worker on a Laptop (Priority: P1)

A team member launches the worker process on one of four laptops. They choose whether the worker should respond with stub (fake) answers for testing or use the real local LLM for production. The worker starts, announces itself, and begins accepting requests from NGINX.

**Why this priority**: Without working workers nothing else can run. This is the foundation of the whole distributed system.

**Independent Test**: Start the worker on one laptop in STUB mode, send a single HTTP POST to its `/process` endpoint, and verify a response is returned with the correct fields (worker ID, latency, result).

**Acceptance Scenarios**:

1. **Given** a laptop with the worker software installed, **When** the operator runs the worker with `LLM_MODE=stub`, **Then** the worker starts, logs its ID and port, and responds to health checks and process requests with stub answers.
2. **Given** a laptop with a local LLM installed and running, **When** the operator runs the worker with `LLM_MODE=ollama`, **Then** the worker starts and routes all inference requests to the local LLM, returning real generated responses.
3. **Given** a running worker, **When** any request is received, **Then** the worker logs the incoming request (timestamp, request ID, query) and the outgoing response (result, latency) to the console and to a persistent log file.

---

### User Story 2 – Send Requests via the Client (Priority: P1)

An operator on the client laptop starts the client. The client generates a configurable number of simulated user requests, places them into a queue, and consumer threads forward them to NGINX. NGINX distributes the requests across the four worker laptops. Every request sent and every response received is logged.

**Why this priority**: This is the core client-side flow — without it, no requests reach the workers.

**Independent Test**: Start the client against a single running worker (bypassing NGINX) and verify requests are queued, dispatched, and responses are printed with full detail.

**Acceptance Scenarios**:

1. **Given** four worker laptops are running and NGINX is configured, **When** the operator starts the client, **Then** requests are placed into the queue, consumers dequeue them, forward them to NGINX, and the client logs each request dispatched (timestamp, request ID, query text).
2. **Given** the client is running, **When** a response is received from any worker, **Then** the client logs it in the format: `RESPONDS FROM: Worker <X> | Request #<N> | Question: <Q> | Response: <R> | Latency: <L> ms` and appends the same entry to a persistent results file.
3. **Given** the client is running with 4 workers, **When** NGINX distributes requests, **Then** responses from different workers are each attributed to the correct worker ID in the log.

---

### User Story 3 – Simulate Worker Failure and Observe Recovery (Priority: P2)

An operator deliberately simulates a worker failure (either by sending a failure trigger or by stopping a worker laptop). The system logs the failure, the remaining workers continue processing, and when the failed worker comes back online it resumes normally.

**Why this priority**: Demonstrating fault tolerance is a key academic requirement and must be observable and testable.

**Independent Test**: With 4 workers running, trigger failure on one, send 10 requests, verify all succeed via the surviving workers, then revive the failed worker and verify it resumes.

**Acceptance Scenarios**:

1. **Given** 4 workers are running, **When** a failure is triggered on Worker 2 (via the `/simulate_failure` endpoint), **Then** the heartbeat monitor logs `ALERT -- Worker 2 is DOWN` and subsequent requests are routed only to the alive workers.
2. **Given** a worker is in the failed state, **When** the worker recovers and its health check returns OK, **Then** the heartbeat monitor logs `Worker 2 is back ONLINE` and requests resume routing to it.
3. **Given** all 4 workers fail simultaneously, **When** a request is sent, **Then** the client logs an error (not a crash) and records the failed request in the results file.

---

### User Story 4 – Review Complete Request-Response Log File (Priority: P2)

After a test run, an operator opens the results log file and finds every request and response recorded in a structured, human-readable format for review or submission.

**Why this priority**: Required for academic demonstration and reproducibility of results.

**Independent Test**: After a short run (10 requests), open the results file and verify all 10 entries are present with correct fields.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the operator opens the results file, **Then** each entry contains: responding worker ID, request number, original question, response text, and latency in milliseconds.
2. **Given** a run with failed requests, **When** the operator reviews the log, **Then** failed requests are also recorded with their failure reason (TIMEOUT, ERROR, WORKER DOWN).

---

### Edge Cases

- What happens when a worker laptop is not reachable at startup? The client should warn and either wait or skip.
- What happens when the queue backs up because workers are slow? Requests waiting beyond the timeout should be logged as TIMEOUT and not block new requests.
- What happens if the results file cannot be written (permissions, disk full)? The system should log a warning to console and continue running.
- What happens when NGINX is not running? The client should detect the connection failure immediately and report a clear error instead of hanging.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The worker process MUST support two operating modes, selectable at startup: stub mode (returns a canned response without LLM) and real-inference mode (forwards queries to a locally running LLM).
- **FR-002**: The worker process MUST expose health-check, statistics, process, simulate-failure, and reset endpoints over HTTP so NGINX and the client can communicate with it.
- **FR-003**: Every request received by a worker MUST be logged immediately (before processing) with: timestamp, worker ID, request ID, and query text.
- **FR-004**: Every response dispatched by a worker MUST be logged with: timestamp, worker ID, request ID, result text, and processing latency.
- **FR-005**: The client MUST maintain a queue into which all outgoing requests are placed. Consumer threads MUST dequeue requests and forward them to NGINX — the client MUST NOT send requests to workers directly.
- **FR-006**: Every request the client dispatches MUST be logged with: timestamp, request ID, and query text.
- **FR-007**: Every response the client receives MUST be logged in the structured format: `RESPONDS FROM: Worker <X> | Request #<N> | Question: <text> | Response: <text> | Latency: <N> ms`.
- **FR-008**: The client MUST append all response log entries to a persistent file (one file per run, named with timestamp) in addition to printing to console.
- **FR-009**: Worker failure MUST be triggerable on demand via an HTTP endpoint (`/simulate_failure`) without stopping the worker process.
- **FR-010**: The heartbeat monitor MUST detect when a worker goes offline and log an alert; it MUST also log when a worker comes back online.
- **FR-011**: The NGINX configuration MUST list all four worker laptops by their IP addresses and ports, and route requests using a configurable load-balancing strategy (round-robin by default).
- **FR-012**: The project MUST contain only files relevant to the distributed workflow (worker, client, NGINX config, shared modules). Unused scripts, test harnesses, and in-process-only files MUST be removed or clearly isolated.
- **FR-013**: The worker MUST be startable with a single command that accepts the worker ID and LLM mode as parameters.
- **FR-014**: The client MUST be startable with a single command and MUST read worker addresses from environment variables or a configuration file so no code changes are needed per-laptop.

### Key Entities

- **Worker**: A process running on one laptop, identified by an integer ID and a port. Has operating mode (stub/ollama), alive status, active request count, total request count, failed request count, and average latency.
- **Request**: Has a unique integer ID, query text, and timestamp of when it was enqueued by the client.
- **Response**: Has the originating request ID, worker ID, result text, processing latency (ms), and queue wait time (ms). Also carries a status (SUCCESS, TIMEOUT, ERROR, FAILED).
- **Log Entry**: A structured record written to both console and file for each request dispatched and each response received.
- **Run Results File**: A timestamped text file written by the client that accumulates all log entries for a single execution run.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four worker laptops can be started independently and confirmed ready within 30 seconds of launch.
- **SC-002**: The client successfully sends and receives responses for at least 90% of requests when all four workers are healthy.
- **SC-003**: Every request dispatched by the client appears in the results log file with all required fields within 5 seconds of the run completing.
- **SC-004**: A simulated worker failure is detected and logged by the heartbeat monitor within 5 seconds of the failure being triggered.
- **SC-005**: After a worker is revived, it resumes receiving requests without any client-side restart, confirmed by log entries showing its worker ID on new responses.
- **SC-006**: When a worker fails mid-run, the system continues processing remaining requests via surviving workers with zero crashes or hangs.
- **SC-007**: Switching between stub and real-inference mode requires only a change to the startup command (no code edits).
- **SC-008**: A run of 1000 requests distributed across 4 healthy workers completes within 30 minutes (1800 seconds) total wall-clock time. The client reports PASS or FAIL against this threshold in the end-of-run summary and results file.

---

## Assumptions

- All five laptops (4 workers + 1 client) are on the same local network and can reach each other by IP address.
- NGINX runs on the same laptop as the client, or on a known fixed IP reachable by the client.
- Worker IP addresses and ports are known before starting the client and can be set via environment variables.
- The local LLM (for real-inference mode) is already installed and running on each worker laptop before the worker process is started; the worker does not install or manage the LLM.
- Each worker laptop runs only one worker process (one worker ID per laptop).
- Failure simulation is done via the HTTP endpoint, not by physically unplugging a laptop (physical failure testing is out of scope for the demo).
- Log files are written to a `logs/` directory in the project root; directory creation is handled automatically.
- The number of simulated users / concurrent requests is configurable via an environment variable before the run.
- File cleanup (removing unused code) targets files that are only relevant to the old single-machine in-process mode and are not needed for the multi-laptop distributed workflow.
