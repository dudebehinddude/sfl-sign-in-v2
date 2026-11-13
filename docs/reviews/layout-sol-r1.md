# Station/UI primary Sol round 1

VERDICT: CHANGES

Snapshot e11fe2cfaa10040c7785ed01f0983414e224dfe2dbe62f8de9be83864cde7483. Task suffix sfl-layout-sol-20261109-r1. GPT-6.1 Sol, high reasoning. No score or usage returned.

S1, should — frontend/src/features/occupancy/filter.ts:36. The occupancy sidebar retains old catalog icons/order after an admin training edit because usePublicLive refreshes occupancy but not the catalog. Invalidate publicKeys.trainingTypes() on changed public snapshots and reconnects, and add a cached-catalog regression.

Reviewer independently reproduced stale sidebar output from frozen trainingCounts, confirmed no catalog invalidation, verified all340 manifest hashes, parsed64 Python files and passed44 label tests. Screenshots inspected. Full suites/builds/migration/browser/S3 evidence supplied, not rerun. No other blocker/should.
