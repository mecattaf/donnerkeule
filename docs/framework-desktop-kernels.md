# Framework Desktop carry-forward: Linux 7.2.10 and 7.2.12

Historical 7.2 delivery evidence, preserved for tonight's `fb05a7d` pin.
The separate `codex/framework-7-3` candidate adds a
[7.3 source review and evidence receipt](framework-desktop-7-3.md).

The mecattaf fork preserves lfthht's Framework repair stack at
`9330fb786a882b8ace61bf330478ee2612048d3b` and ports its opt-in descriptor
batching to the fleet's **7.2.10 and 7.2.12** kernels. A downgrade to 7.2.6 is
unnecessary for building this candidate. **Neither fleet kernel is hardware
qualified by this work yet.** Follow the [attended runbook](framework-desktop-tonight.md).

## What changed

- One shared allowlist in `kernel/compat/framework_ring.h` admits x86_64
  7.2.6, 7.2.10 and 7.2.12. Other releases still reject
  `dmabuf_verbs=1 dmabuf_batch_doorbell=1` with `-EOPNOTSUPP` at initialization.
  They also refuse bulk publication and skip private descriptor readiness
  inspection. This is deliberately not an open-ended `>=7.2.6` promise.
- The original ring size/offset assertions remain on admitted kernels; descriptor
  offsets and descriptor flag values are checked too. Unsupported kernels no
  longer inherit these private-layout assertions when using the base driver.
  AMD PCI IDs `1022:158d` / `1022:158e`, frame mode, interrupt-worker ownership,
  available capacity, running state and control-ring exclusion remain checked.
  `dmabuf_batch_abi_supported` in debugfs reports the build-time allowlist result.
- Completion timers, ordinary-worker ownership, callback draining, bounded
  caches, nested credit staging, host-direct DMA and provider CQ-capacity
  repairs remain intact. Their algorithms and opt-in defaults are unchanged.
  The wire format and provider/kernel UAPI are unchanged.
- The flake lock now uses the same nixpkgs revision as dotfiles PR #583
  (`dce1caf58d1a943af38b376e824a0d036ec3eea7`, Linux 7.2.12).
  `build-fleet.sh` additionally tests the current fleet's revision
  `94d35c7c05087e8b07373a403c55e97d99ff9af9` (7.2.10).
- The Nix rdma-core package excludes `usb4_rdma*` from its persistent-naming
  rule. Its existing three provider patches and provider source are unchanged.
  NixOS consumers must inspect their effective system rules; putting a package
  in a shell does not replace the system's udev rules.
- Added a matching-provider perftest environment, a read-only hardware-state
  evidence helper, and a pinned Gufo TP2 probe package. They do not install a
  system configuration or load a module.

The newer neuhaus main (`b01ca117` at the audit) removes the exclusive
`gpu_direct` pool and changes GPU credit/loss handling. Those are separate
transport/lifecycle changes, outside this kernel port. This branch remains on
the measured Framework lineage instead of combining two unqualified stacks.
No changes were sent to lfthht, neuhaus or Hellas.

## Source and layout evidence, 2026-10-23

The following official stable source files have identical SHA256 values in
**all three** releases. `audit-kernel.py` checks these bytes from a source
directory or tar archive, and optionally the actual build headers.

| File | SHA256 |
|---|---|
| `drivers/thunderbolt/nhi.c` | `b8b78b1a524844c1487dbd2b1ef696610ebc8720caf13a2d2d8ccecfd4c989b4` |
| `drivers/thunderbolt/nhi.h` | `f0026407a0005510e34cb331dba9b4a360bb93bdb5c63cd0cec0f2273fdc1e5c` |
| `drivers/thunderbolt/nhi_regs.h` | `e98150dae51b46c1d83d92c0de0fe2b925e61e220a1a14d8cd200a153fc81e45` |
| `include/linux/thunderbolt.h` | `e883a1c144eb50ea09313631d845400a1bcd47a57334cf24eb19a97cde5c66ee` |

Sources: [v7.2.6](https://github.com/gregkh/linux/tree/v7.2.6/drivers/thunderbolt),
[v7.2.10](https://github.com/gregkh/linux/tree/v7.2.10/drivers/thunderbolt),
[v7.2.12](https://github.com/gregkh/linux/tree/v7.2.12/drivers/thunderbolt).
This establishes the descriptor bitfields, MMIO addressing, enqueue locking,
head/tail/list ordering and the ordinary completion/cancellation worker's
implementation; it does not establish DMA or IRQ behavior on a particular box.
The RX doorbell uses offset `0x8000 + hop*16 + 8`; TX uses `hop*16 + 8`, with
the producer in bits 31:16. Descriptor flags begin at byte 8, bit 20.

| Kernel | Evidence for this candidate | Hardware evidence |
|---|---|---|
| 7.2.6 | Official four-file source comparison; posting/readiness C harnesses exercise the admitted ABI | lfthht's **original** Ubuntu Framework pair measurements; this port was not rebuilt or run on 7.2.6 |
| 7.2.10 | Full Nix module builds with profiling on and off; source archive and actual `kernel.dev` header audit; exported `tb_ring_throttling` in `Module.symvers`; live Thunderbolt BTF read without loading anything | Candidate module never loaded; two-box DMA/performance unproven |
| 7.2.12 | Full Nix module builds with profiling on and off; source archive and actual `kernel.dev` header audit; exported `tb_ring_throttling`; BTF read from the packaged Thunderbolt module against its matching `kernel.dev` vmlinux | Candidate module never loaded; two-box DMA/performance unproven |

Both BTF inspections show `sizeof(tb_ring)=184`, `descriptors@32`,
`in_flight@64`, and `sizeof(ring_desc)=16`, with `length@8:0/12`,
`eof@8:12/4`, `sof@8:16/4`, `flags@8:20/12`, `time@12`.
The exact local outputs and artifact hashes are recorded in
[`framework-desktop-kernel-evidence.json`](framework-desktop-kernel-evidence.json).
The packaged 7.2.12 module was inspected as a file, not loaded.

## Reproduce the build checks

```sh
bash tools/framework-desktop/build-fleet.sh  # both kernels, both profiling modes
nix build .#rdma-core-usb4 .#perftest .#checks.x86_64-linux.verbs-smoke-build
python3 tools/framework-desktop/verify-port-source.py
python3 tools/ci/check-syntax.py
```

For the production-helper and protocol tests on Tom's hosts:

```sh
nix shell github:NixOS/nixpkgs/dce1caf58d1a943af38b376e824a0d036ec3eea7#gcc \
  --command ~/.local/bin/runtime-test -- python3 tools/ci/run-smoke.py
```

The suite passes protocol/state tests, sanitizer-backed smoke programs,
provider patch regeneration and production C helpers. Bulk posting and
readiness run on all admitted release macros, reject unaudited releases and
other architectures, and verify that a changed ring size fails compilation.
The hardware evidence parser rejects absent/quarantined rails, missing ACTIVE
ports, missing pushed-DONE readiness, errors, reset counters and missing payload
or batching increments. The Nix provider build passes its udev rule validation;
the matching perftest and verbs smoke programs compile successfully.

`docs/framework-desktop-tested-source.json` remains the original measurement
record. `verify-tested-source.py` intentionally reports a difference on this
port. Use `verify-port-source.py`, which checks every original driver/provider
file plus the two explicitly recorded source changes in
`framework-desktop-port-source.json`. Do not attribute lfthht's binary hash,
srcversion or 51.67/50.20 Gb/s rates to the new modules. These Nix kernels do
not emit a module srcversion; compare module SHA256 and vermagic instead.

## Qualification boundary and future kernels

Unproven: both-cable enumeration, every rail carrying payload, native control
behavior with stable-kernel fixes, IOMMU/BIOS differences, GPU DMA-BUF mapping,
correct Gufo GPU sums, normal repeated QP teardown, reconnect behavior and
performance on Tom's pair. No VM/no-controller module load can prove these.
No hardware, GPU execution, module load, system switch or reboot was performed.

For another kernel: compare the four sources and completion/locking semantics,
inspect its built BTF including bitfields, update the allowlist and audited
hashes, build against its exact configured headers, exercise rejection and
layout tests, then repeat the attended pair qualification. Equal version
numbers alone do not qualify vendor patches or a different configured layout.
Keep `kernel.useProjectKernel = false` for the stock fleet kernel. Wiring this
fork into dotfiles and changing its boot/activation policy is a separate task.
