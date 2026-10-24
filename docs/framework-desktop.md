# Framework Desktop: the tested two-cable setup

This page records **lfthht's original 7.2.6 measurements and setup**. The
mecattaf carry-forward has separate [kernel evidence](framework-desktop-kernels.md)
and [attended qualification commands](framework-desktop-tonight.md). The
original source manifest and binary identity below do not describe the port.

This branch carries the changes measured on **two Framework Desktop motherboards**
with Ryzen AI Max+ 395 APUs and Radeon 8060S GPUs. Each board has 128 GB of unified
memory at 8000 MT/s. The boards report FRANMFCP06 revision A6 and BIOS 03.04.
The tested OS was Ubuntu 26.04.1 LTS, kernel `7.2.6-070206-generic`, x86_64.

The source is based on Donnerkeule
[`e4039b6778aee5625c0dddf13e3c6477ff9597ce`](https://github.com/neuhaus/donnerkeule/commit/e4039b6778aee5625c0dddf13e3c6477ff9597ce).
Donnerkeule itself builds on [Hellas AI's thunderbolt-ibverbs](https://github.com/hellas-ai/thunderbolt-ibverbs).
Their authors retain credit for the original driver, verbs provider, and rail
pooling/striping. The original research-driver status and license still apply.

## Scope and measurements

Two USB4 cables negotiated **40 Gb/s each**, reported as 20 Gb/s per lane and
two lanes in each direction. Two controllers each supplied two payload rails.
One QP pooled all four rails.

The final short, host-memory, 16 MiB WRITE preflight measured **51.67 Gb/s
forward and 50.20 Gb/s reverse**. These are separate one-direction observations,
not rates to add together. The combined 80 Gb/s negotiated rate describes link
capacity; 60–80 Gb/s payload has not been demonstrated by these changes. The
remaining controller/DMA completion limitation is unresolved, and its firmware
or hardware origin has not been established.

The [measured Gufo comparison](../bench/results/2026-10-21-framework-desktop/README.md)
contains five paired repetitions at 16K, 32K, 64K and 128K input depths, with 256
output tokens. Gufo used GPU DMA-BUF windows on both ranks. The host-memory
preflight rates describe a different workload from GPU inference.

## Changes in this branch

1. **Completion progress:** an opt-in timer schedules ordinary data and XDomain
   control-ring workers instead of repeatedly waiting for the DMA watchdog.
   The ordinary workers retain descriptor and callback ownership.
2. **Bulk publication:** opt-in AMD-specific descriptor batching reduces MMIO
   writes and starts sibling rails before filling an entire ring. Contiguous
   host staging copies can be coalesced.
3. **Normal QP close:** stop accepting new local posts, drain accepted work, and
   wait for a bounded quiet period before cancellation. Unavailable or
   quarantined rails are excluded from selection and exposed in debugfs.
   Genuine interrupted raw streams retain quarantine.
4. **Bounded reuse:** opt-in descriptor/staging caches hold one maximum batch
   per rail and direction. Reuse follows callback draining; abort, disconnect,
   and unload invalidate allocations. Staging is bounded to 2 MiB per direction
   per rail, 16 MiB across four rails, plus metadata.
5. **Direct host DMA:** eligible aligned pinned host MRs map directly to the
   actual NHI DMA device. Short, unaligned or unsupported transfers retain
   staging; GPU DMA-BUF mappings remain direct. MR access/bounds and remote
   placement completion are preserved.
6. **Nested credit staging:** an internal credit-release filler gets private
   temporary storage instead of borrowing the outer transfer's cache lease.
7. **Timer ownership and descriptor readiness:** serialize start/forward/stop
   ownership and avoid postponing an existing progress deadline. Schedule the
   ordinary worker when its next descriptor is complete, including wraparound
   and partial groups. The reference interval remains 25 microseconds.
8. **CQ capacity compatibility:** the userspace provider reports the requested
   CQ capacity when a successful older-kernel response leaves `ibv_cq.cqe` zero.
   A nonzero kernel-reported capacity is preserved. Packaged rdma-core provider
   patches contain the same fix.

The performance parameters are opt-in. Lifecycle repairs apply when the driver
is used. Wire structures and provider/kernel interfaces are unchanged. The
alternative spin, high-priority, single-rail SEND, and demand-polling experiments
are excluded from this branch.

## Build and source verification

```sh
git clone --branch codex/framework-desktop https://github.com/lfthht/donnerkeule.git
cd donnerkeule
python3 tools/framework-desktop/verify-tested-source.py
python3 tools/ci/framework-desktop-smoke.py
python3 tools/ci/run-smoke.py
make -j8 KVER=7.2.6-070206-generic
modinfo kernel/thunderbolt_ibverbs.ko
```

Build on Linux with the matching kernel headers and compiler. The bulk helper
targets the exact tested **Linux 7.2.6 x86_64 Thunderbolt ring ABI** and AMD NHI
PCI devices **`1022:158d` / `1022:158e`**. Its build assertions check ring size and
offsets. Other kernel versions, controller types or changed layouts require a
port and new qualification before enabling the helper.

Before loading on each host, inspect the running module's BTF as well as the
matching headers, for example with a recent `pahole`:

```sh
pahole --btf_base=/sys/kernel/btf/vmlinux -C tb_ring /sys/kernel/btf/thunderbolt
pahole --btf_base=/sys/kernel/btf/vmlinux -C ring_desc /sys/kernel/btf/thunderbolt
```

The measured layout has `sizeof(tb_ring)=184`, `descriptors` at byte 32,
`in_flight` at byte 64, and a 16-byte `ring_desc`, with completion flags starting
at byte 8, bit 20. Resolve missing or incompatible BTF/tool output before using
direct descriptor publication.

The tested machines booted with `amd_iommu=off amdgpu.gttsize=126976
ttm.pages_limit=32505856`. These are recorded environment details, not changes
made by this fork. IOMMU-enabled operation and other memory policies were not
qualified in this run.

`docs/framework-desktop-tested-source.json` records all 48 kernel/protocol/header
source hashes and the provider source hash. The October 21 measured module had
srcversion `57FE5E2439711FB49D9723A`; its provenance is retained under
`october_21_measurement_baseline`. The October 24 capability correction has
srcversion `BBDB140372B8EC1C925667B`. Module binary hashes can differ because
build paths and profiling options differ. Build once for matching hosts and
copy identical module bytes to both.

### DMA-BUF port capabilities and QP1 messages

With `dmabuf_verbs=1`, QP creation supports RC data queues only. Previously the
port still advertised kernel MAD and IB connection-management capabilities.
Linux consequently attempted a GSI management queue and logged
`Couldn't create ib_mad QP1`, followed by `Couldn't open port 1`, once per rail
at registration. The latter message describes management initialization.

The October 24 correction clears `RDMA_CORE_CAP_IB_MAD` and
`RDMA_CORE_CAP_IB_CM` and reports `max_mad_size=0` only in DMA-BUF mode. RoCE v2,
GID table sizes, addressing, manual RC setup and the transfer path are retained.
The non-DMA-BUF mode retains its existing management capabilities. No kernel log
filter or console-level change is used.

The corrected build was loaded on both hosts and retained for automatic startup.
All four rails became active on each host, with no new QP1/open-port messages.
Host/GPU SEND and WRITE payloads, guards and two-round MR/QP recreation passed
in both directions. Short bandwidth results and their limits are recorded in
[the capability-fix validation](../bench/results/2026-10-24-port-capabilities/validation.json).
The earlier inference measurements remain the October 21 baseline; inference
performance was not remeasured for this capability correction.

### Userspace provider

The measured provider used **rdma-core 61.0, provider ABI 59**. Build against the
rdma-core ABI used by the application, including its container if applicable.
Keep the original provider available for restoration.

The fork's `userspace/usb4_rdma/` and
`packaging/rdma-core-patches/` are synchronized. To use a clean matching
rdma-core source tree, apply the complete three-patch series, then build:

```sh
export DONNERKEULE_SRC="$PWD"
export RDMA_SRC=/absolute/path/to/clean/matching/rdma-core
cd "$RDMA_SRC"
while IFS= read -r patch; do
  patch -p1 < "$DONNERKEULE_SRC/packaging/rdma-core-patches/$patch"
done < "$DONNERKEULE_SRC/packaging/rdma-core-patches/series"
cmake -S . -B build-usb4 -DNO_PYVERBS=1
cmake --build build-usb4 -j8
```

The resulting `libusb4_rdma-rdmav*.so` and `usb4_rdma.driver` must be available
to the application alongside its normal providers. A Gufo container needs the
correct provider inside the image. The engine images and model weights used
for the measurements are identified by hashes but are not distributed here.

## Temporary two-cable profile

Use an independent management/control connection. Capture the existing module
options, netdev configuration, provider files and startup settings before a
test. Keep the installed driver intact. The measurements used temporary module
loading and restored the existing configuration afterward.

Ensure `thunderbolt_net` is not claiming the data rings during the native test;
see the upstream README for ring allocation and module-loading details. These
controllers had one control ring pair and two available payload ring pairs.
Keep **`lanes=2` per controller**.

Create a dummy netdev for GID metadata if one does not already exist. These are
documentation-only example addresses; choose an unused subnet for the real
setup. On the other host use the other address:

```sh
sudo ip link add tbv0 type dummy
sudo ip address add 192.0.2.1/30 dev tbv0  # 192.0.2.2/30 on the peer
sudo ip link set tbv0 up
```

After stopping jobs using the existing driver, unload it normally, load the new
module's dependencies, and load the candidate explicitly:

```sh
sudo modprobe -r thunderbolt_ibverbs
modinfo -F depends kernel/thunderbolt_ibverbs.ko | tr ',' '\n' | xargs -r sudo modprobe -a
sudo insmod kernel/thunderbolt_ibverbs.ko \
  profile=linux_perf tbnet=prefer_rdma lanes=2 bind_services=1 \
  allocate_rings=1 start_rings=1 negotiate_native=1 enable_tunnels=1 \
  register_verbs=1 roce_netdev=tbv0 native_domain_mask=3 \
  native_write_striping=1 dmabuf_verbs=1 dmabuf_push_done=1 dmabuf_credits=1 \
  nhi_interrupt_throttle_ns=0 \
  dmabuf_poll_us=25 dmabuf_poll_control=1 \
  dmabuf_batch_doorbell=1 dmabuf_post_burst=128 dmabuf_coalesce_copy=1 \
  dmabuf_reuse_buffers=1 dmabuf_host_direct=1
```

`native_domain_mask=3` selects domains 0 and 1 on these hosts. For a one-cable
check, match the same physical link at both ends using the reciprocal XDomain
UUIDs, then select each host's corresponding domain bit. Domain numbers need
not match between hosts. Device names can also differ after reload.

Verify the negotiated speeds, selected HCA/GID, peer generation, pushed-DONE
readiness and all four data rails before posting work:

```sh
ibv_devices
ibv_devinfo -d usb4_rdma0 -v
sudo cat /sys/kernel/debug/thunderbolt_ibverbs/peers
sudo cat /sys/kernel/debug/thunderbolt_ibverbs/summary
```

Every selected rail must report `descriptor_ready=1 quarantined=0` as well as
active, service/data ready, negotiated and remote ready. `IB/RoCE` labels in
verbs metadata describe the exposed interface. This path uses native USB4
hardware DMA, not an RXE/Soft-RoCE device. Bootstrap/control TCP can stay on a
separate network while the selected GID contains the dummy netdev address.

## Three-second bandwidth and lifecycle checks

Select the actual active native HCA and IPv4 RoCE-v2 GID index on each host.
The measured GID index was 1; verify it on the current setup. Run the receiver
first, using the same settings on the sender. The sender's final argument is
the receiver's reachable **control-network** address:

```sh
# Receiver; use the locally verified HCA and GID index.
timeout 15s taskset -c 0 ib_write_bw \
  -d usb4_rdma0 -i 1 -x 1 -s 16777216 -p 19123 -I 0 -F \
  --tclass 96 --use_old_post_send --report_gbits -D 3 -f 1 -q 1 -t 32 -Q 1

# Sender, in a separate terminal on the other host.
timeout 15s taskset -c 0 ib_write_bw \
  -d usb4_rdma0 -i 1 -x 1 -s 16777216 -p 19123 -I 0 -F \
  --tclass 96 --use_old_post_send --report_gbits -D 3 -f 1 -q 1 -t 32 -Q 1 \
  peer-control-hostname
```

These are three-second runs; `-f 1` leaves a central one-second reporting
interval. Counter deltas must prove payload on all four rails, with no loss,
completion or access errors. Check both directions without reloading between
them, then test each cable separately. Finite `-n` runs are useful for draining
submitted work and recreating MRs/QPs; an intentional interrupted raw stream
can require coordinated recovery. Do not clear a quarantine flag to reuse it.
Use the upstream GPU verifier for SEND/WRITE payload, guard, access-rejection,
and GPU DMA-BUF checks before drawing application conclusions.

The recorded setup also marked TCP bootstrap sockets with traffic class 96.
Optional diagnostic shims are included as source:

```sh
cc -O2 -fPIC -shared tools/framework-desktop/tcp-control-tclass.c \
  -o /tmp/tcp-control-tclass.so -ldl -pthread
cc -O2 -fPIC -shared tools/framework-desktop/verbs-diagnostic.c \
  -o /tmp/verbs-diagnostic.so -ldl -pthread
```

`LD_PRELOAD=/tmp/tcp-control-tclass.so` marks TCP socket traffic, not verbs
payload. The second shim records numeric post-send errors. Its optional
`TBV_DIAG_FLUSH_MR=1` cache-eviction experiment was disabled for the reported
preflight. Neither shim is required to expose the native RDMA device.

## Recovery and limits

After stopping the test jobs, unload the temporary module normally and restore
the captured driver, providers, netdev and startup settings. Remove only dummy
interfaces or temporary configuration files created for the test. Confirm
management access, original networking and a GPU smoke check on both hosts.
No automatic persistent startup is provided by this Framework profile.

The original investigation exercised ten forward/reverse QP/MR recreation
cycles without per-direction reloads, finite and timed transfers, idle,
interruption recovery, host/GPU correctness, guards, unaligned host tails and
access rejection. The published source tests exercise real production
functions with hardware mocks; they complement hardware qualification and do
not simulate concurrent physical DMA. Fresh hardware/configurations still
need the short correctness, counter, lifecycle and recovery checks.

The benchmark and publication build left the original machines on their
captured Mellanox defaults. Publishing the fork did not restart inference or
the full benchmark.
