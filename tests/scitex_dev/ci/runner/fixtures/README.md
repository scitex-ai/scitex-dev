# Organization workflow source fixture

This finite input contains 25 complete public workflow bodies exported with
ordinary git show. Current main is e7821bb86fdbd8279fe404770693a856dbf4c59a.
The three retained immutable revisions are declared in _policy_contract.py.
Every body was checked against that contract before freezing this fixture.

The gzip mtime is zero. Uncompressed JSON is 552588 bytes with SHA256
90dcffc996ddf64ccff9b0a2de4662d09d9baf1b050dd4e3be35a6484e2b7f29.
All thirteen historical bodies remain byte-identical to the preceding fixture.
Only the current SIF body changed from d7d96c34d68cdfbb5503a933591f7748b5aa30ee,
through normal organization PR66. Its complete 47383-byte body matches the
GitHub contents API and Git blob 9e7d167524c94785847e1140297301875b293783.
The e09a immutable SIF body retains its independent original hash, so a
current-main hash update cannot authorize changed historical bytes.
The tests exercise complete source qualification through the ordinary API
adapter, including changed current/historical bytes and a moving main.
No current GitHub access, module patching or alternate authority is used.
