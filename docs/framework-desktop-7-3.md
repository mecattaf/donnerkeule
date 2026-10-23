# Framework Desktop carry-forward to Linux 7.3

Candidate branch: `codex/framework-7-3`, based on the 7.2 delivery
`fb05a7d210179fa2daaefe3e7bf45bbb4a0b7ff3`. The separate
`codex/framework-fleet-kernels` branch and dotfiles PR #610's pin stay at that
revision. Tonight's 7.2.12 qualification still uses that branch and its
[attended runbook](framework-desktop-tonight.md). Fleet adoption of 7.3 belongs
to [dotfiles #584](https://github.com/mecattaf/dotfiles/issues/584).

This candidate admits **exactly upstream 7.3 / `uname -r` 7.3.0**, x86_64,
with the audited stock nixpkgs configuration and AMD NHIs 1022:158d/158e.
7.3.1 and later releases need another audit. Builds and a controller-free VM
pass; **two-box hardware, correctness and performance remain unqualified**.

## What the fork carries forward

The complete lfthht Framework repair stack remains: completion progress through
ordinary ring workers, descriptor batching, drain/teardown, bounded caches,
direct host MR mapping, nested credit staging and the CQ-capacity repair.
Provider code, wire format, driver UAPI and all other driver C/header files
are identical to the 7.2 delivery. Only `kernel/verbs_dmabuf.c` and
`kernel/compat/framework_ring.h` change in the driver:

- Add 7.3.0 to the exact private-ABI allowlist. Preserve the descriptor size,
  offsets, flag-value assertions and existing AMD/frame/ownership/capacity
  checks. Performance options stay opt-in.
- Exclude the new `RING_FLAG_NO_INTERRUPT` rings from bulk IRQ-descriptor
  publication and from scheduling the ordinary completion worker. The check
  probes the header flag, including backports and unaudited future releases.
  This fork continues to allocate ordinary IRQ rings. It does not adopt the
  new tbstream polling transport.
- Keep the existing Kbuild service-probe signature check. The 7.3 build selects
  `tbv_service_probe_without_id()`, which recovers the matched table entry,
  preserving native lane selection and protocol version/revision matching.

Nix gains explicit `thunderbolt-ibverbs-7-3` and
`thunderbolt-ibverbs-7-3-no-profiling` packages, a source audit and a 7.3 VM
test. The normal default packages and overlay still select 7.2; the NixOS
module builds against the consuming host's `boot.kernelPackages`.
`flake.lock` is unchanged. CI adds 7.3 alongside both 7.2 kernels.

The VM exposed a packaging defect: copying a bare `.ko` omits the certificate
sidecar required by this nixpkgs' module aggregator. `nix/module.nix` now uses
`kernelModuleMakeFlags` and Kbuild `modules_install`, including nixpkgs'
deterministic signing rule. It preserves the uncompressed `extra/*.ko` path
and supplies its `.ko.cer` when signing is enabled. The 7.3 VM assembles its
NixOS module tree and boots successfully; both older kernel targets are also
rebuilt. This change exists only on the new branch.

### Packaging prerequisite for tonight's frozen 7.2 pin

The same module-tree check also exposes the missing sidecar when the frozen
`fb05a7d` module is combined with **7.2.12 at nixpkgs `dce1caf`**. Its module
build succeeds; aggregation fails with
`cat: extra/thunderbolt_ibverbs.ko.cer: No such file or directory`. PR #610's
existing toplevel receipts used its older 7.2.10 package set, so they do not
establish assembly with the new 7.2.12 set.

The 7.2 branch and #610 pin remain unchanged. A reviewed consumer-side repair
is provided in [`nix/frozen-pin-certificate-fix.nix`](../nix/frozen-pin-certificate-fix.nix).
It imports the **frozen source pin's** module, replacing only installation with
Kbuild's signing/install rule. It does not import the 7.3 driver changes.
For the integration session, copy that small expression into dotfiles and use:

```nix
hardware.thunderbolt-ibverbs.packageFor = kernelPackages:
  import ./frozen-pin-certificate-fix.nix {
    inherit (pkgs) lib;
    inherit kernelPackages;
    source = inputs.donnerkeule; # remains fb05a7d
  };
```

This exact repair was built against 7.2.12 and its module-tree aggregation
passed. Its `.text`, `.rodata`, `.data` and `.modinfo` sections match the
original frozen-pin module byte for byte. Signing changes the complete file's
hash, which must be recorded again during qualification. The integration
session must rebuild both actual toplevels after applying the packaging repair.
**The override has not been applied to dotfiles here.** This is a concrete
packaging prerequisite, separate from the pending hardware run.

## Upstream source changes: 7.2.12 → 7.3

Compared the official source archives used by the pinned nixpkgs kernels.
[The reproducible inventory](framework-desktop-7-3-source-delta.json) covers
all files in `drivers/thunderbolt`, `drivers/infiniband/core`, `include/rdma`,
`include/uapi/rdma`, and seven relevant Linux headers. It contains 200 old and
201 new files: 54 changed/added, 147 identical, none deleted. Hardware HCA
drivers under `drivers/infiniband/hw` are outside this software USB4 driver's
review scope. This is a source compatibility review, not a whole-kernel
security or behavioral certification.

| Area | Change and consequence for this fork |
|---|---|
| NHI rings | `nhi.c` adds optional interrupt-free rings, permits polling them, rejects combining that flag with `start_poll`, and skips IRQ allocation/enable/disable for them. Ordinary IRQ-ring descriptor encoding and ownership remain compatible; this fork explicitly excludes the new mode from its private fast path. |
| Ring metadata | Each ring gets a lockdep key, registered at allocation and removed on free/error. The key is appended to `tb_ring`; it has size zero with the audited configuration, preserving ring size 184. Debug/lockdep configurations are not qualified and can trip the layout assertions. |
| Service probing | `tb_service_driver.probe` drops the matched-ID argument; XDomain driver registration now rejects a missing probe. The existing compile-time adapter handles the actual 7.3 headers. `dma_test` and `stream` also adopt the new signature. |
| DMA tunnels | `tunnel.c` clamps DMA credits to 127, the Hop register's seven-bit maximum, and refactors credit calculation to unsigned values. This is relevant to the XDomain DMA tunnels used here; the fork uses the kernel's tunnel API. |
| Stream transport | ConfigFS busy-poll support, NOWAIT/nonblocking locking, and short-transfer/iterator handling changes. These apply to `tbstream`; this driver implements its own verbs transport. |
| Reset/shutdown | `pci.c`/`tb.c` track host reset and assert downstream-port reset at shutdown for Thunderbolt 3 devices, skipping USB4 routers; a port-reset helper is exposed internally. An AMD DMA-teardown reset quirk was added and then reverted during development, so it is absent in final 7.3. Do not count it as an AMD fix supplied by this port. |
| Other Thunderbolt | Debugfs buffer allocation changes to `kzalloc`/`kfree`; stream uses newer allocation helpers. `nhi.h`, `nhi_regs.h`, `ctl.c` and `quirks.c` are byte-identical. The reviewed stable XDomain/request-cancellation/HopID/DP fixes have not been undone. |
| RDMA completion counters | New completion-counter objects, device capabilities/ops, uverbs methods and QP bookkeeping. Core code initializes/destroys the new QP xarray. The fork's designated ops and `INIT_RDMA_OBJ_SIZE` compile against the new structures; it does not advertise the optional counter feature. |
| RDMA device attributes/CQ | Device capacity fields change from signed `int` to `u32`; core CQ sizing drops a redundant `min_t`. Fork limits are nonnegative and its CQ repair remains unchanged. |
| Registered memory | `umem.c` allocates its temporary page list with `kmalloc`/`kfree` and refuses DMA-BUF MR re-registration. The fork implements ordinary/pinned DMA-BUF registration, not MR re-registration. Pinned DMA-BUF attach ops become `const`; peer-to-peer allowance and pin/release logic stay intact. The enabled-config `ib_umem`/DMA-BUF entry signatures used here are unchanged; the disabled-config stub also becomes const-correct. |
| Namespace/naming | RDMA names become namespace-local in exclusive mode, with atomic move+rename, conflict handling, teardown fallback names and better netlink errors. Moving still requires exclusive mode and driver disassociation support. This fork keeps its existing host/shared-namespace path and the `usb4_rdma*` udev rename exclusion. Container/exclusive-namespace behavior is not qualified. |
| Other RDMA core/UAPI | Resource maxima and completion-counter tracking, device indexing for cgroups, ODP fault-helper refactoring, optional SRQ UMEM, a generic clock-info layout, and vendor ABI extensions. The fork does not advertise SRQ or ODP. Existing generic verbs command layouts used by its provider are retained; its UAPI and provider source are unchanged. `dma-buf.h` and `scatterlist.h` are identical; the reviewed DMA-mapping header addition is for confidential-computing allocation attributes. |

The inventory also hashes six **identical** NHI functions: `ring_work`,
`__tb_ring_enqueue`, producer/consumer MMIO writes, `tb_ring_flush` and
`tb_ring_throttling`. `ring_write_descriptors` does change for the new mode;
the audit does not treat all of `nhi.c` as unchanged.

Primary sources: [7.2.12 Thunderbolt](https://github.com/gregkh/linux/tree/v7.2.12/drivers/thunderbolt),
[7.3 Thunderbolt](https://github.com/torvalds/linux/tree/v7.3/drivers/thunderbolt),
[7.2.12 RDMA core](https://github.com/gregkh/linux/tree/v7.2.12/drivers/infiniband/core),
[7.3 RDMA core](https://github.com/torvalds/linux/tree/v7.3/drivers/infiniband/core),
[7.3 public RDMA headers](https://github.com/torvalds/linux/tree/v7.3/include/rdma),
[7.3 UAPI](https://github.com/torvalds/linux/tree/v7.3/include/uapi/rdma).
The interrupt-free ring change is [f5cb175ed728](https://github.com/gregkh/linux/commit/f5cb175ed728),
the DMA credit cap [86feaba911f2](https://github.com/gregkh/linux/commit/86feaba911f2),
and the AMD reset-quirk revert [c230bc2b926d](https://github.com/gregkh/linux/commit/c230bc2b926d).

## Evidence and reproduction

Exact artifact paths, module SHA256 values, source hashes and evidence limits
are in [the 7.3 receipt](framework-desktop-7-3-evidence.json). The
[packaged BTF output](framework-desktop-7-3-btf.txt) is preserved separately.

- Full module builds with profiling enabled and disabled for 7.3.0, plus
  regression builds for 7.2.10 and 7.2.12 with both profiling settings; assembled
  kernel/module trees pass for all three targets. CI checks assembly too.
- The source audit checks 16 critical 7.3 files and the actual build header.
  Negative checks reject changed NHI/DMA-BUF source, a different build header,
  and unaudited 7.3.1/7.4. `tb_ring_throttling` is exported.
- Packaged Thunderbolt BTF, read as a file against matching `kernel.dev`
  vmlinux: ring size 184, descriptors@32, in_flight@64, flags@124;
  descriptor size 16, metadata@8, flags@8:20/12, time@12. The appended
  lockdep key is zero bytes at 184. `tb_nhi.host_reset` is appended at 136;
  `tb_nhi` grows to 144 without shifting the fields the driver uses.
- Full production-helper/protocol/provider/sanitizer smoke suite passes.
  Posting/readiness tests cover 7.3.0, the new flag and its backport, layout
  mismatch, unsupported architectures and rejection of future releases.
- A disposable NixOS/KVM guest boots 7.3.0 with the assembled signed module
  tree, accepts all Framework parameters, checks dependencies/debugfs/trace
  events, exercises synthetic configfs link lifecycle, and performs four
  load/unload cycles. ABI support reports 1; batching and 25 µs progress are
  enabled. No BUG/WARNING/Oops/KASAN/panic appears in guest dmesg. There is
  **no USB4 controller, registered HCA, real QP traffic or DMA in this VM**.
  Signature enforcement is off in the stock configuration. The guest records
  module taint `OE` (out of tree/unverified); stock `autofs4` also logs a
  missing-key verification message during boot. The package contains a
  PKCS#7 signature and certificate sidecar, but this VM does not prove a
  trusted-certificate/Secure Boot deployment.

From this branch, builds and source comparisons do not change the live kernel:

```sh
bash tools/framework-desktop/build-fleet.sh 7.3
bash tools/framework-desktop/build-fleet.sh 7.2.10 7.2.12
nix build .#rdma-core-usb4 .#perftest .#checks.x86_64-linux.verbs-smoke-build
python3 tools/framework-desktop/verify-port-source.py
python3 tools/ci/check-syntax.py
nix shell github:NixOS/nixpkgs/dce1caf58d1a943af38b376e824a0d036ec3eea7#gcc \
  --command ~/.local/bin/runtime-test -- python3 tools/ci/run-smoke.py
~/.local/bin/runtime-test --allow-kvm -- nix build \
  .#hydraJobs.x86_64-linux.vm-smoke.nixos-7-3 --cores 8 --max-jobs 1 -L
```

`result-fleet-7.3` is the profiling module, `-1` the nonprofiling module,
and `-2` the source/header audit JSON file; `-3` is the assembled module tree.
Nix calls the source release
`7.3`, but its modules directory and vermagic are **7.3.0**. To regenerate
the complete source inventory, supply the unpacked official sources or their
tar archives:

```sh
python3 tools/framework-desktop/source-delta.py /path/to/linux-7.2.12.tar.xz \
  /path/to/linux-7.3.tar.xz > source-delta.json
diff -u docs/framework-desktop-7-3-source-delta.json source-delta.json
```

## Attended hardware qualification

Tonight stays on the original 7.2.12 branch/runbook. When both Framework hosts
are deliberately moved to 7.3, use this branch's identical commit and matched
provider on both. First reproduce the builds above and record the candidate
NixOS generation, actual booted image, source/config, BIOS, IOMMU policy and
module hashes. A version string alone does not identify the kernel. NixOS may
rebuild the image to insert external-module certificates; compare against
the prepared generation's image, not an unrelated stock `bzImage` path.

For that later 7.3 run, replace the original runbook's sections 1–2 kernel
selection/preflight with the candidate-generation check and:

```sh
test "$(uname -r)" = 7.3.0
MODULE="$PWD/result-fleet-7.3/lib/modules/7.3.0/extra/thunderbolt_ibverbs.ko"
test "$(modinfo -F vermagic "$MODULE" | cut -d' ' -f1)" = 7.3.0
sha256sum "$MODULE"
```

Then follow the same attended runbook's host identity, actual booted BTF,
four-rail readiness, baseline then Framework profiles, bidirectional perftest,
Gufo TP2 all-reduce, counter/error checks, normal QP close, cable recovery and
rollback. Use the installed fleet firewall backend and peer/interface-scoped
rules for the four documented TCP ports; the old iptables example is not an
nftables command. Do not restart the firewall or trigger global udev.

Passing requires correct payloads/GPU sums, useful traffic on all four rails,
bulk calls in the Framework pass, no new driver/kernel errors, clean ordinary
close and unload, and repeatable baseline/candidate performance comparison.
No claim of no performance loss, AMD DMA correctness, interrupt behavior,
IOMMU compatibility, dual-cable recovery or Gufo TP2 correctness on 7.3 follows
from the build/VM evidence alone. No system was activated or host module loaded
to prepare this candidate.
