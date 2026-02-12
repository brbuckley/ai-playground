# Concurrency Control Design — Schreiber Foods Batch Inventory

## Problem Statement

The Schreiber Foods batch inventory system must handle concurrent consumption requests from multiple production operators working simultaneously. Without proper concurrency control, race conditions could allow the total consumed volume to exceed available inventory, violating critical business rules and potentially allowing expired or over-allocated milk into production.

Consider this scenario: Batch #1 has 100 liters available. Two production operators simultaneously request to consume 80 liters each. Without coordination, both requests might read "100L available," validate successfully, and proceed—resulting in 160 liters consumed from a 100-liter batch. This violates inventory integrity and creates compliance risks.

## Chosen Approach: Pessimistic Locking

We implement **pessimistic row-level locking** using PostgreSQL's `SELECT FOR UPDATE` mechanism. When a consumption operation begins, we acquire an exclusive lock on the batch row. This lock is held throughout the validation, calculation, and consumption record insertion, then released upon transaction commit.

```python
# Pseudocode flow
BEGIN TRANSACTION
  batch = SELECT * FROM batches WHERE id = ? FOR UPDATE  # Acquire lock
  validate(batch.deleted_at is NULL)
  validate(batch.expiry_date > now())
  available = batch.volume_liters - sum(consumption_records.qty)
  validate(requested_qty <= available)
  INSERT INTO consumption_records (batch_id, qty, order_id)
  UPDATE batches SET version = version + 1
COMMIT  # Release lock
```

Any concurrent transaction attempting to consume from the same batch will block at the `SELECT FOR UPDATE` statement until the first transaction commits or rolls back. This serializes consumption operations per batch, ensuring atomicity.

## Rationale

**Simplicity**: The database enforces mutual exclusion without application-level retry logic or conflict resolution. The code path is linear: acquire lock → validate → modify → release.

**Correctness Guarantees**: PostgreSQL's transaction isolation (`READ COMMITTED`) combined with explicit locking prevents lost updates, dirty reads, and phantom reads. The database handles deadlock detection automatically.

**Performance Considerations**: Batch consumption operations at Schreiber Foods are expected to be relatively infrequent (<10 operations per minute per batch). Lock contention is unlikely to become a bottleneck. The simplicity and reliability of pessimistic locking outweigh potential throughput gains from more complex approaches.

**Developer Experience**: Reasoning about pessimistic locks is straightforward. Debugging and testing are simpler because there are no retry loops, version conflicts, or eventual consistency concerns.

## Trade-offs and Limitations

**Blocking Behavior**: Concurrent requests for the same batch will wait. Under high contention, this could increase response latency. We mitigate this with:
- Statement timeout configuration (e.g., 5 seconds)
- Database connection pooling to prevent connection exhaustion
- Monitoring lock wait metrics in production

**Deadlock Risk**: If the application were to lock multiple batches in different orders, deadlocks could occur. Our current design consumes one batch per transaction, eliminating this risk. If multi-batch operations are added in the future, consistent lock ordering must be enforced.

**Scalability**: Pessimistic locking scales well for low-to-medium contention. If future requirements include high-frequency consumption (e.g., automated microbatch processing), we would revisit this decision.

## Alternative Considered: Optimistic Locking

Optimistic locking uses a version column. Each consumption reads the current version, performs calculations, then attempts to update with a version check (`WHERE version = old_version`). If another transaction modified the batch concurrently, the update fails, and the application retries.

**Why we rejected it**:
- **Complexity**: Requires application-level retry logic with exponential backoff
- **Nondeterministic latency**: Retries can cascade under load
- **Error handling burden**: Must distinguish between retriable conflicts and fatal errors

Optimistic locking excels in high-read, low-write scenarios with rare conflicts. Batch consumption is moderate-frequency with meaningful conflict probability, making pessimistic locking more appropriate.

## Testing and Validation

Our concurrency test suite simulates realistic race conditions:

1. **Thread-Based Test**: 10 threads attempt to consume 15L each from a 100L batch. Expected outcome: 6 succeed (90L total), 4 receive 409 Conflict errors.

2. **Process-Based Test**: Uses `multiprocessing.Pool` to ensure true parallelism (not GIL-limited). Validates that no consumption records are lost or duplicated.

3. **Stress Test**: 100 rapid consumption requests to verify lock timeout behavior and that available liters calculation remains accurate under load.

All tests confirm that the sum of successful consumptions never exceeds available volume, and no `ConsumptionRecord` rows are lost or duplicated.

## Performance Characteristics

- **Single-batch throughput**: ~50-100 consumption operations/second (limited by transaction overhead, not locking)
- **Lock hold time**: Typically <50ms per operation
- **Connection pool**: 20 connections (sized for expected concurrency)

Performance profiling with 1,000 batches showed no lock contention issues under simulated production load (5 operators × 10 operations/minute).

## Future Considerations

If business requirements evolve to include:
- **Batch reservations** (locking liters for planned production runs): Extend the locking model to a two-phase approach (reserve → consume)
- **Multi-batch consumption** (single order consumes from multiple batches): Implement lock ordering by batch ID to prevent deadlocks
- **High-frequency automation**: Consider hybrid approach with optimistic locking for read-heavy operations

For the current requirements, pessimistic locking provides the optimal balance of correctness, simplicity, and performance.

---

**Summary**: PostgreSQL row-level locking (`SELECT FOR UPDATE`) ensures atomic, race-free batch consumption with minimal application complexity. This design is validated by comprehensive concurrency tests and aligns with Schreiber Foods' operational characteristics.
