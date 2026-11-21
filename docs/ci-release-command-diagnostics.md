# Disposable release-command diagnostics

`tests/integration/_release_command.py` retains the existing five-second
subprocess deadline and command behavior. On timeout it reports the bounded
owned Git trace and candidate observations, plus a correlation result from
`_release_trace_correlation.py`.

The correlation accepts one matching command-start event and one version event
for the same session, restricted to Git 2.43.0 trace format v3. Git's
[versioned SID implementation](https://github.com/git/git/blob/v2.43.0/trace2/tr2_sid.c)
encodes the low 32 bits of its process ID in the final session component.
The helper requires that value to match every observed candidate PID and a
consistent birth tick. It reports only a numeric value, a sample count and
constant labels; it does not echo arguments, session IDs or paths.

This is a positive correlation within retained evidence. It is not authenticated
process identity, proof of what caused a delay or evidence of progress after
the last sample. The original observer's ownership and sampling limits remain.
Missing observations, unsupported Git versions, incomplete or malformed traces,
multiple matching starts and inconsistent identities remain unknown. Trace input
is limited to 8,192 characters and candidate lists to 24 samples. A truncated
tail may therefore be unknown even if a relevant event was emitted.

The parser controls use structured trace data and an inert real Git version
command with its actual process ID. Existing timeout/cleanup/privacy controls
remain in `tests/integration/test_ci_release_command_diagnostics.py`. Run selected
controls together with the mandatory audit gate; do not replay a held failed
release fixture merely to obtain a cleaner result.
