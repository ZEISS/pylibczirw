# Test Fixture Policy

The fixture manifest lists the exact bytes used by the tests. Every active
asset has a size, SHA256 digest, repository-relative path and case assignments.
The test session checks the inventory before collection. Git LFS stores CZI,
NumPy and reference-array assets; hashed JSON evidence and XML text references
use LF line endings.

## Scope

Existing checked-in fixtures are reused as regression inputs. Their original
acquisition history is not reconstructed by successful tests. Synthetic
fixtures have explicit pixel, coordinate, XML, mask and attachment expectations.
Reference comparisons do not establish an implementation pass, full support
certification, redistribution clearance or publication rights for other data.

The published reference JSON files are labeled publication projections of
retained historical evidence, not the original machine-specific receipts.
Local machine locations and internal approval records are omitted. Embedded
helper paths are made repository-relative and their public-text hashes are
recomputed; the original source hashes remain identified separately. Embedded
helpers are historical reference material, not newly executed validation.

The projections preserve factual case assignments, generated-asset identities,
pixel/XML expectations and the distinction between verified values and unknown
provenance. No failed, unknown or blocked reference is promoted to a pass by
curation. The tests verify the projected records' integrity and those boundaries.

## Local Data

Acquisition files not present in the manifest are not included in this corpus.
The local-data demos require user-supplied files and fixture-appropriate
selectors. Do not add acquisition data or generated output to the repository
without a separate rights and privacy review.

## Runtime Checks

Run tests against the intended installed wheel and verify module origins when
checking packaging behavior. Live URL reads, certificate handling, resource
measurements and graphical display require their own appropriately provisioned
checks; a fixture inventory or reference projection does not certify them.