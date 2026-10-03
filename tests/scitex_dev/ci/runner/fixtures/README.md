# Organization workflow source fixture

This finite input contains 25 complete public workflow bodies exported with
ordinary git show. Current main is 07c3cd6915508f8a84d1c5a9da4373f839f96416.
The three retained immutable revisions are declared in _policy_contract.py.
Every body was checked against that contract before freezing this fixture.

The gzip mtime is zero. Uncompressed JSON is 543584 bytes with SHA256
bb7809602d1d39ed3dbc9ed60043874b16c2a8da3746c0e6c75cbf710ed7854a.
The tests exercise complete source qualification through the ordinary API
adapter, including changed current/historical bytes and a moving main.
No current GitHub access, module patching or alternate authority is used.
