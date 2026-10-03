# Organization workflow source fixture

This finite input contains 25 complete public workflow bodies exported with
ordinary git show. Current main is d7d96c34d68cdfbb5503a933591f7748b5aa30ee.
The three retained immutable revisions are declared in _policy_contract.py.
Every body was checked against that contract before freezing this fixture.

The gzip mtime is zero. Uncompressed JSON is 547052 bytes with SHA256
94719cb2cded91a08dd3978ce3b3b66d0fac1f4c40f887525276f1f1567376f2.
All thirteen historical bodies remain byte-identical. Current admission and
runner health are the only two changed bodies, from normal organization PR64.
The tests exercise complete source qualification through the ordinary API
adapter, including changed current/historical bytes and a moving main.
No current GitHub access, module patching or alternate authority is used.
