# Attended Framework pair qualification

Run **after the cutover, with Tom present**, on strix-coordinator and
strix-worker. Do not run the load or traffic steps on the current session host.
Keep management/bootstrap on Ethernet. Neither host may be running a workload
using this driver. Nothing here reboots a host or restarts Herdr, Bluetooth or
the user manager. Hardware qualification belongs to the exact kernel, BIOS,
boot parameters, module bytes, provider and Gufo build recorded in the run.

## 1. Prepare the identical artifacts

Use the same mecattaf branch commit on both hosts. Choose **one kernel for the
pair**, normally 7.2.12 after PR #583; 7.2.10 is also build-supported. Testing
7.2.12 does not hardware-qualify 7.2.10. Do not mix kernel versions for this
qualification. These commands build only and can be run before the cutover:

```sh
git clone --branch codex/framework-fleet-kernels https://github.com/mecattaf/donnerkeule.git
cd donnerkeule
git rev-parse HEAD
bash tools/framework-desktop/build-fleet.sh 7.2.12  # use 7.2.10 if testing that kernel
nix build .#rdma-core-usb4 .#perftest
nix build --impure --file nix/gufo-qualification.nix -o result-gufo-probe --cores 8
python3 tools/framework-desktop/verify-port-source.py
```

`result-fleet-7.2.12` is the profiling-enabled candidate module. The `-1` link
is its profiling-disabled counterpart; `-2` is the source/header audit output.
The Gufo package pins neuhaus `c0beaa64361b6783b5a4894bbf96dab832c154f6`, builds
the actual TP2 batched probe and links this fork's provider. `--help` is checked
at build time; no GPU operation is run. Its all-reduce mode needs no model files
or control-token secret. This is a qualification tool, not fleet Gufo deployment.

For already built closures, copy rather than rebuilding or copying a lone
provider `.so`. From the machine holding the build, with the correct kernel:

```sh
nix copy --to ssh-ng://strix-worker \
  "$(readlink -f result-fleet-7.2.12)" \
  "$(readlink -f result-gufo-probe)" \
  "$(nix eval --raw .#rdma-core-usb4.outPath)" \
  "$(nix eval --raw .#perftest.outPath)"
```

The worker can recreate its `result-*` links by running the same build commands
after the closures arrive. Do the equivalent copy to strix-coordinator if the
build machine is elsewhere. Compare module SHA256, Gufo binary SHA256 and git
revision on the two hosts; kernel releases must also match.

## 2. Attended host checks and temporary identity

On **each** host, enter the tool environment and keep that shell for the run:

```sh
nix develop .#framework-qualification
set -euo pipefail
ulimit -l unlimited
KERNEL=$(uname -r)
case "$KERNEL" in
  7.2.10) PKGS_REV=94d35c7c05087e8b07373a403c55e97d99ff9af9 ;;
  7.2.12) PKGS_REV=dce1caf58d1a943af38b376e824a0d036ec3eea7 ;;
  *) echo "Wrong kernel: $KERNEL"; exit 1 ;;
esac
KERNEL_PACKAGE=$(nix eval --raw --impure --expr \
  "(import (builtins.getFlake \"github:NixOS/nixpkgs/$PKGS_REV\").outPath { system = \"x86_64-linux\"; }).linuxPackages_7_2.kernel.outPath")
test "$(readlink -f /run/booted-system/kernel)" = "$KERNEL_PACKAGE/bzImage"
MODULE="$PWD/result-fleet-$KERNEL/lib/modules/$KERNEL/extra/thunderbolt_ibverbs.ko"
test "$(modinfo -F vermagic "$MODULE" | cut -d' ' -f1)" = "$KERNEL"
sha256sum "$MODULE" result-gufo-probe/bin/.tbv-gufo-tp2-probe-wrapped
RUN_DIR="$HOME/donnerkeule-qualification/$(date -u +%Y%m%dT%H%M%SZ)-$(hostname)"
mkdir -p "$RUN_DIR"
git rev-parse HEAD > "$RUN_DIR/revision"
uname -a > "$RUN_DIR/uname"
cat /proc/cmdline > "$RUN_DIR/cmdline"
lspci -nnk > "$RUN_DIR/pci"
cat /sys/class/dmi/id/bios_version > "$RUN_DIR/bios"
ip -br address > "$RUN_DIR/ip-addresses"
date --iso-8601=seconds > "$RUN_DIR/start-time"
```

Both AMD NHIs must be `1022:158d` / `1022:158e`, bound to `thunderbolt`.
The kernel store-path comparison above must pass too: matching version text
alone is insufficient if the new hosts boot a differently configured kernel.
Stop and build against that actual kernel rather than bypassing the check.

Record the IOMMU and memory policy; the original measurement used `amd_iommu=off`.
An enabled IOMMU is a new test condition, not proven by the original numbers.
Verify `ip route get PEER_ETHERNET_IP` uses Ethernet before removing
`thunderbolt_net`. Save the existing module options and system setup if there
is already a driver installed; stop its consumers through their normal controls.

Inspect every effective `60-rdma-persistent-naming.rules` in
`/etc/udev/rules.d`, `/run/udev/rules.d` and `/usr/lib/udev/rules.d` if present.
There must be **no active rule renaming `usb4_rdma*`**. The candidate package's
rule includes `KERNEL!="usb4_rdma*"`; a `nix develop` shell cannot alter the
system's rules. If an existing rule lacks the exclusion, arrange that NixOS
rule correction before loading the candidate. Do not trigger udev on devices
that have already registered or silently accept a renamed HCA. On the original
live host this rule was absent; re-check the newly installed hosts.

Create `tbv0` only if it does not already exist. First verify the example
documentation subnet `192.0.2.0/30` is unused on the hosts. Choose a different
unused subnet if needed and record it. On strix-coordinator:

```sh
sudo ip link add tbv0 type dummy
sudo ip address add 192.0.2.1/30 dev tbv0
sudo ip link set tbv0 up
```

On strix-worker use `192.0.2.2/30`. If `tbv0` already exists, verify its type
and address instead of recreating it. This netdev provides GID metadata;
management TCP continues over Ethernet.

## 3. Load the baseline, then the Framework profile

Start with `PROFILE=baseline`. After completing sections 4–6, stop the probes,
unload normally on **both** hosts and repeat with `PROFILE=framework`. The two
`.params` files differ only in the opt-in Framework performance knobs. Both
use DMA-BUF verbs, pushed-DONE and SEND credits; neither enables the retired
exclusive `gpu_direct` pool. Never force an unload.

```sh
PROFILE=baseline  # second pass: framework
# Only after all driver users have exited, if the module is already loaded:
# sudo modprobe -r thunderbolt_ibverbs
if grep -q '^thunderbolt_net ' /proc/modules; then
  sudo modprobe -r thunderbolt_net  # Ethernet management already verified
fi
sudo modprobe -a ib_core ib_uverbs configfs thunderbolt
pahole --btf_base=/sys/kernel/btf/vmlinux -C tb_ring /sys/kernel/btf/thunderbolt \
  | tee "$RUN_DIR/tb-ring.txt"
pahole --btf_base=/sys/kernel/btf/vmlinux -C ring_desc /sys/kernel/btf/thunderbolt \
  | tee "$RUN_DIR/ring-desc.txt"
```

Before enabling the Framework profile, the booted BTF must show the
[audited layout](framework-desktop-kernels.md): ring size 184, descriptors@32,
in_flight@64, descriptor size 16, flags@8:20/12 and time@12. Resolve absent or
different BTF before proceeding; do not treat the allowlist as a BTF check.

Connect both cables. Confirm the domains to use from sysfs. On these hosts
the expected domains are 0 and 1 (`MASK=3`); if enumeration differs, set the
mask independently per host from the actual two domains. Domain numbering
need not match between hosts. Then, on both hosts:

```sh
MASK=3
read -r -a OPTIONS < "tools/framework-desktop/$PROFILE.params"
sudo insmod "$MODULE" "${OPTIONS[@]}" roce_netdev=tbv0 native_domain_mask="$MASK"
sudo "$(command -v python3)" tools/framework-desktop/qualification-state.py wait --timeout 300
ibv_devices | tee "$RUN_DIR/$PROFILE-devices.txt"
```

Readiness waits for an ACTIVE `usb4_rdma` port, exactly four usable native
rails, no quarantine and pushed-DONE readiness on each peer. A timeout is a
failure to investigate, not a reason to continue. Choose one actual ACTIVE
native HCA and its IPv4 **RoCE v2** GID for `tbv0` independently on each host:

```sh
HCA=usb4_rdma0  # replace with the verified local ACTIVE HCA
ibv_devinfo -d "$HCA" -i 1 -v | tee "$RUN_DIR/$PROFILE-devinfo.txt"
cat "/sys/class/infiniband/$HCA/ports/1/state"
grep -H . "/sys/class/infiniband/$HCA/ports/1/gids/"*
grep -H . "/sys/class/infiniband/$HCA/ports/1/gid_attrs/types/"*
GID=1  # replace with the local IPv4 RoCE-v2 index just inspected
grep -H . /sys/bus/thunderbolt/devices/*/{rx_speed,tx_speed,rx_lanes,tx_lanes} \
  | tee "$RUN_DIR/$PROFILE-links.txt"
```

Each cable must report **20 Gb/s per lane, two RX and two TX lanes**. Record
reciprocal XDomain `unique_id`/`remote_uuid` and domain mappings in the log.
The HCA/GID choices may differ between hosts. Do not infer readiness from a
fixed sleep or from the HCA's presence alone.

## 4. Both-direction payload, latency and normal QP close

Use three repetitions per profile and direction. The examples below are the
first forward run: worker receives, coordinator sends. On **both** hosts:

```sh
LABEL="$PROFILE-dual-forward-1"
sudo "$(command -v python3)" tools/framework-desktop/qualification-state.py snapshot "$RUN_DIR/$LABEL-before.json"
```

Start on strix-worker first:

```sh
timeout 30s taskset -c 0 ib_write_bw -d "$HCA" -i 1 -x "$GID" \
  -s 16777216 -p 19123 -I 0 -F --tclass 96 --use_old_post_send \
  --report_gbits -D 3 -f 1 -q 1 -t 32 -Q 1 2>&1 | tee "$RUN_DIR/$LABEL-bw.log"
```

Immediately run on strix-coordinator, with the worker's **Ethernet** address:

```sh
timeout 30s taskset -c 0 ib_write_bw -d "$HCA" -i 1 -x "$GID" \
  -s 16777216 -p 19123 -I 0 -F --tclass 96 --use_old_post_send \
  --report_gbits -D 3 -f 1 -q 1 -t 32 -Q 1 strix-worker \
  2>&1 | tee "$RUN_DIR/$LABEL-bw.log"
```

Both commands must exit zero. Without unloading, on each host capture after
the processes have exited normally:

```sh
sudo "$(command -v python3)" tools/framework-desktop/qualification-state.py snapshot "$RUN_DIR/$LABEL-after.json"
# coordinator: --traffic tx; worker: --traffic rx
python3 tools/framework-desktop/qualification-state.py compare \
  "$RUN_DIR/$LABEL-before.json" "$RUN_DIR/$LABEL-after.json" --traffic tx \
  > "$RUN_DIR/$LABEL-delta.json"
# Add --bulk to compare in the framework pass; worker uses --traffic rx.
```

The comparison fails on errors, reset counters, changed rails or missing
payload completion on any of the four rails. `--bulk` also requires actual
bulk-call/frame increments and the supported/enabled ABI flags. Review the
raw summary/peers embedded in the snapshots too. Confirm host-direct/cache
counters increase on eligible large transfers. Perftest proves the host path,
not GPU DMA-BUF correctness.

For reverse runs swap the server/client roles and use `strix-coordinator`
as the client argument. Change `LABEL` to `...-reverse-1`, then `...-2` and
`...-3` for each direction. Do not reload between these runs: repeated normal
QP close must leave the same rails ready and unquarantined.

Also run a finite validated write and 64-byte latency check each direction.
Use the same command on both hosts, receiver first, adding its Ethernet
hostname only to the sender:

```sh
timeout 30s ib_write_bw -d "$HCA" -i 1 -x "$GID" -s 4096 -n 128 \
  -p 19124 -I 0 -F --tclass 96 --use_old_post_send \
  -q 1 -t 32 -Q 1 --data_validation
timeout 30s ib_write_lat -d "$HCA" -i 1 -x "$GID" -s 64 -n 1000 \
  -p 19125 -I 0 -F --tclass 96 --use_old_post_send
```

Save stdout/stderr and exit codes with unique labels as above. Counter
snapshots bracket each check; keep all unexpected errors. Omit `--bulk` from
the comparisons for these 4 KiB/64-byte checks: a single descriptor correctly
uses the ordinary posting fallback. Require bulk increments for the large
16 MiB WRITE and Gufo collective instead. A perftest option
or validation failure is a failed check, not permission to silently remove it.

## 5. Gufo TP2 GPU sums, no model files

On both hosts snapshot before. Start coordinator rank 0 first; start worker
rank 1 within 30 seconds. Run twice with fresh log/snapshot names, without
unloading between runs:

```sh
# strix-coordinator
timeout 180s result-gufo-probe/bin/tbv-gufo-tp2-probe \
  --tp-rank 0 --tp-rdma-device "$HCA" --tp-gid-index "$GID" \
  --tp-bootstrap-port 18515 --allreduce-bench 1000 \
  2>&1 | tee "$RUN_DIR/$PROFILE-gufo-1.log"

# strix-worker (its own verified HCA/GID)
timeout 180s result-gufo-probe/bin/tbv-gufo-tp2-probe \
  --tp-rank 1 --tp-bootstrap-host strix-coordinator \
  --tp-rdma-device "$HCA" --tp-gid-index "$GID" \
  --tp-bootstrap-port 18515 --allreduce-bench 1000 \
  2>&1 | tee "$RUN_DIR/$PROFILE-gufo-1.log"
```

Each rank must exit zero, log `windows=gpu_send`, and report `verified=1`
for **1, 2, 8 and 512 rows**. `windows=host_write` is a GPU-window
qualification failure even if sums match: preserve its fallback reason.
The probe checks every GPU sum exactly and reports latency distributions.
Snapshot after and compare with `--traffic both` (and `--bulk` for the
Framework profile), then wait for all four rails again. This tests the
actual Gufo collective, but does not qualify full-model output hashes,
MTP, serving concurrency or long-context capacity.

## 6. Each cable, then the complete pair again

After all consumers exit, unload normally on both hosts. Disconnect cable B,
reload the same profile with the recorded domain mask, and wait using
`qualification-state.py wait --rails 2 --timeout 300`. Re-select the active
HCA/GID. Run the forward/reverse bandwidth and validated-write checks with
unique `single-A` labels and `compare --rails 2`. Unload normally, swap to
cable B alone and repeat with `single-B`. Do this for both profiles.

Restore both cables with consumers stopped, reload and repeat the four-rail
readiness, one forward/reverse bandwidth pair and the no-model Gufo probe.
This tests orderly disconnect/reconnect; in-flight cable loss and forced
process-death recovery are separate, unqualified experiments.

Finally save kernel logs since the recorded start time on both hosts:

```sh
sudo journalctl -k --since "$(cat "$RUN_DIR/start-time")" > "$RUN_DIR/kernel.log"
```

Review for WARN/Oops, IOMMU/DMA faults, timeouts, CQ errors, rail quarantine,
stuck unloads and coredumps. Do not suppress or clear them. A timeout or stuck
module is a failed run: retain diagnostics; no force unload or service-manager
restart. Do not restart Herdr or reboot as a repair action.

## Acceptance and rollback

All checks must pass, including real bulk counter increments on the Framework
pass, four-rail payload, repeated normal closes, single-cable operation and
GPU sums. Compare the three host-bandwidth runs and Gufo latency distributions
against the baseline on the same hardware/BIOS/kernel. A repeatable performance
regression needs investigation. The inherited 51.67/50.20 Gb/s numbers are
another person's observations, not a pass threshold for this pair.

On failure, stop only the qualification processes normally. Save evidence,
unload `thunderbolt_ibverbs` normally when unused, and either leave it unloaded
or reload `baseline.params` with the same known-good module/identity. Restore
any pre-test dummy-netdev, module/provider, naming-rule and thunderbolt-net
state from the saved configuration; never remove a pre-existing `tbv0`. For a
newly created test-only `tbv0`, delete it only after the driver is unloaded.
No boot configuration is changed by these temporary loads. Persistent NixOS
integration and full Gufo serving qualification remain separate work.
