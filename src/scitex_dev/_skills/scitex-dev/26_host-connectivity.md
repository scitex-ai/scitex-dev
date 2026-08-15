---
description: |
  [TOPIC] Host connectivity — reaching a machine, and proving the address still points at it
  [DETAILS] `HostConnectivity` on every `HostRecord` (observed `lan` vs DHCP `reserved`, off-LAN `net` route, MAC, ssh host-key fingerprint, identity file, `last_seen`); `render_ssh_config`, `check_matrix`, `check_ssh_config`, `corroborate`; CLI `scitex-dev host generate-ssh-config / validate-matrix / validate-ssh-config / corroborate`.
tags: [scitex-dev-host-connectivity, scitex-dev-host-registry]
---

# Host connectivity — `scitex_dev.hosts`

The registry half ("where is host X, what's its `~/.scitex` root") is
[24_host-registry.md](24_host-registry.md). This file is the other half:
**how do I reach it, and how do I know that is still true?**

Each record carries a `HostConnectivity`. **Every field is optional**, so a
`hosts.yaml` written before this existed parses unchanged; `is_empty()`
distinguishes "nothing recorded" from "recorded as absent".

```yaml
scitex-compute-01:
  kind: compute
  ssh_alias: scitex-compute-01
  scitex_root: "~/.scitex"
  lan: 192.168.11.94          # OBSERVED — where it actually answered
  reserved: 192.168.11.171    # RESERVED  — where the router says it should
  mac: 70:85:c2:3a:a9:42
  host_key_fingerprint: "SHA256:..."
  reported_hostname: scitex-compute-01   # what `hostname` prints ON the box —
                                         # often NOT the key; nas-01 says WATANAS1
  ssh_user: ywatanabe
  identity_file: ~/.ssh/id_mesh
  last_seen: 2026-08-13
  net:                        # the route that LEAVES the LAN
    transport: cloudflared    # direct | cloudflared | reverse-ssh
    hostname: bastion.scitex.ai
```

## The naming rule (operator ruling, 2026-08-13)

> The **bare** canonical name is the **LAN** route.
> The **`-net`** suffix is ONLY for a route that **leaves** the LAN.
> **A bare name never carries a bastion route.**

Enforced **structurally**, not by a validator: the LAN side of
`HostConnectivity` has no `jump`/`proxy_command` field to put one in, and a
bastion can only be expressed inside `net:`, which the generator emits under
`<name>-net` and nowhere else. A bastion silently attached to a bare name
produced the 2026-08-13 mesh incident; it is now unexpressible, not merely
discouraged.

## Reserved is not observed

`lan` and `reserved` are **two fields on purpose**. Measured 2026-08-13:
three compute hosts are reserved at one address and answering at another
because their leases have not renewed. Both statements are true, and a
registry with one address field must lie about one of them.
`reservation_matches_observed` returns `None` — never `True` — when either is
missing.

## No private key material, ever

Only **public** facts are state: an address, a MAC, a host-key **fingerprint**,
the **path** of an identity file. The parser refuses a PEM header in any value
and a secret-shaped field name (`private_key`, `passphrase`, ...). This file
is read by every host in the fleet; a secret reaching it is disclosed to all
of them at once and cannot be recalled.

## Generating `~/.ssh` stanzas

```python
from scitex_dev.hosts import list_hosts, render_ssh_config, write_managed
write_managed("~/.ssh/conf.d/scitex-dev-hosts.conf", render_ssh_config(list_hosts()))
```
```bash
scitex-dev host generate-ssh-config                       # preview on stdout
scitex-dev host generate-ssh-config --write PATH          # report the plan only
scitex-dev host generate-ssh-config --write PATH -y       # apply it
```

`--write` is a **dry run until you add `-y`**: this edits a file inside
`~/.ssh`, where a surprise is expensive and not obviously reversible.

Two names per host: `<name>` (LAN) and `<name>-net` (off-LAN, only when a
`net:` route exists). `render_ssh_config` carries no timestamp, so writing it
twice changes nothing and `ManagedWrite.changed` is a real signal.

**It never deletes an entry because the host is unreachable.** Operator rule:
*unreachable ≠ delete*. An entry whose machine is off simply ages — its
`last_seen` stops advancing, and the generator renders that date into the
stanza comment. **It never touches anything outside its managed block**
either: the region is delimited by `BEGIN_MARKER` / `END_MARKER`, everything
outside is preserved byte for byte, and one marker found without its partner
is a **refusal** — the extent is unknown, and guessing would delete
hand-written stanzas.

> **Generating a correct file is only half a guarantee.** ssh takes the FIRST
> value it obtains for each keyword and expands `Include` in place. If the
> managed block sits below an `Include` that also defines these hosts, the
> included file wins and the block is inert. `validate-ssh-config` finds out.

## `validate-ssh-config` — declared vs what ssh actually obeys

```bash
scitex-dev host validate-ssh-config                        # this machine
scitex-dev host validate-ssh-config --on scitex-compute-01 # that host's own config
```

Answers two questions no amount of reading a config file can:

1. **Does the stanza that WINS say what the registry says?** Measured
   2026-08-13: `~/.ssh/config` began with `Include conf.d/*/*.conf`, an
   included stanza silently beat every stanza below it, and the file people
   read was not the file ssh obeyed. `ssh -G` is the only honest reader — it
   is ssh answering about itself. Reproduced as a test.

2. **Does the key the stanza NAMES actually exist here?** The single real
   mesh failure of that day: scitex-compute-01's stanza named
   `~/.ssh/id_rsa`, absent on that machine, so ssh offered **no key at all**
   and the far end answered `Permission denied` — while its `id_mesh` key was
   already authorised there. Every layer looked correct; the error named
   neither.

   Telling a *declared* key from ssh's seven built-in candidates is subtler
   than it looks: subtracting the default set is **wrong**, because
   `~/.ssh/id_rsa` is itself a default and subtraction erases exactly the
   compute-01 case. The working discriminator (measured, OpenSSH 9.6) is
   **replacement** — a stanza declaring any `IdentityFile` makes `ssh -G`
   report only the declared ones (1 line) instead of all 7 — so the test is
   list inequality against ssh's config-free set (`ssh -G -F /dev/null`).

`ssh -G` resolves and exits without connecting, so a switched-off host is
still checkable. An alias it would not answer about is **not checked**, and
the verdict is `incomplete`, never `pass`.

## `validate-matrix` — ordered pairs, with the denominator

```bash
scitex-dev host validate-matrix                      # lan + net
scitex-dev host validate-matrix --transport lan --json
```

A mesh is **N*(N-1) ordered pairs per transport**, not "can I reach
everything": A→B succeeding says nothing about B→A — different keys,
different `authorized_keys`, often different routes. A probe from a
non-local source runs *through* that source, so it measures the source's own
config rather than ours. The result carries `expected` (a complete sweep's
size), `attempted` (what really ran), and every skip with its reason.
**`verdict == "pass"` requires both that nothing failed AND that the sweep
was complete**; 40 skips and 2 passes is `incomplete`. A bare pass count
cannot be told apart from "and thirty were never attempted".

## `corroborate` — three signals before an address is rewritten

```bash
scitex-dev host corroborate scitex-nas-01
scitex-dev host corroborate scitex-compute-01 --address 192.168.11.171
```

Encodes the manual procedure that made the 2026-08-13 address rewrite safe.
Three **independent** signals — the router's view, the machine's persistent
identity, and its running configuration:

| signal | source | question |
|---|---|---|
| `mac-reservation` | `ip neigh` / `arp` | is the NIC at this address the one we recorded? |
| `host-key-continuity` | `ssh-keyscan` | is this the SAME machine, readdressed? |
| `live-hostname` | `ssh <addr> hostname` | what does the machine call itself? |

Host-key continuity is the strongest and the one that actually settled it:
a machine that moves keeps its host key, so ssh itself reports *"This host
key is known by the following other names/addresses: … 192.168.11.161"*. No
amount of connecting successfully can establish that — a different box
answering at the old address connects fine too.

**The rule:**

- **all three available and agreeing** → `corroborated`, `may_rewrite=True`;
- **any available signal disagreeing** → `conflict`. Do not rewrite; it is
  recorded and escalated to a human. A machine can *detect* disagreement but
  cannot decide which source is true, and picking a winner silently is how a
  wrong address gets baked in and propagated to every host by the generator;
- **fewer than three available** → `insufficient`, **not** a pass. *"No
  contradiction found" is not "corroborated."* The verdict is computed from
  the count of signals that actually ran, and the missing ones are named in
  the output. (`ip`/`arp` are absent in the agent containers, so this is the
  ordinary case there.)

An unrenewed lease (`reserved` ≠ `lan`) is a **note**, never a conflict: it is
not a disagreement about *which machine* is at the observed address.

`may_rewrite` is the decision; the automatic rewriter is **not shipped yet**
— `hosts.yaml` is ~2/3 comments carrying the fleet's operational memory, and
a YAML round-trip deletes all of it silently. The gate today is the exit
code: run `corroborate` before editing an address, and honour it.

## Exit codes

Every `validate-*` verb exits `0` only on `pass`; `incomplete` exits `1` and
`fail` exits `2`. A cron entry or CI step reads the exit code and nothing
else, and a check that could not run must not hand it the same `0` a healthy
fleet does. `corroborate` exits `0` only when `may_rewrite` is true.
