# The Legend of Zelda: Ocarina of Time (`0400486024DEC000`)

A Switch 2 game. Brought up on v131072, SDK 22.2.8 built for the Switch 2 (`Ounce`), NVN2. Nintendo EPD's engine (sead / agl / gsys, Phive, Havok, NPLN 1.55.1), CRIWARE, AV1 movies through SDK 22's decoder. Modules `main`, `subsdk0` (NintendoSDK_movie) and `sdk`. **Reaches the title screen and the opening's text scenes on the Mac** (M5, 16 GB): the title renders, New Game plays the intro's narration text and the opening AV1 movie decodes (9,254 pictures), and the game then runs with sound for 15 minutes under scripted input. Heavy streaming in the opening then exhausts the Mac's GPU memory (below). Not yet playable; not tested on iOS.

Packed from a [NUP container](../../../scripts/pack_nup.py) whose only package is the update v131072, taken as the whole game.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `mem_reserve 0x300000000` | [`game.tsv`](game.tsv) | `SetHeapSize` asks 0x18ce00000 (6.34 GB). The guesser's 5 GB left a 2.94 GB heap region (`SetHeapSize OOM`); 12 GB here, partitioned like Mario Kart World's, holds the request with margin. The [address-region check](../../../docs/reference/memory.md) measured the game's regions at alias +2.15 GB in its first 15 s |
| `game_env GRPC_POLL_STRATEGY=poll` | `game.tsv` | NPLN's grpc poll strategy comes from `getenv`, whose default ("all") the game's own check refuses against {head_custom, poll, none, tail_custom}: the creator aborts the game (the [NPLN offline](#npln-offline) section). "none" passes the check but trips a consistency guard in the sdk's obfuscated npln config path (sdk+0x16d1e0 aborts through main's creator guard); "poll" passes both |
| `render_cond on` | `game.tsv` | agl wraps its clears in render conditions (Donkey Kong Bananza, Splatoon Raiders, Mario Kart World) |
| `DM_ROMFS_OVERLAY` | the run command | the container's only package is the update; its RomFS lacks the base game's `npln_config.json`, which the game reads from its `_npln` mount. The [run folder's overlay](../../../docs/reference/packing.md) serves a stand-in |

## Files

- The NUP's 24.5 GB hold 186,587 RomFS files (zstd): TerrainArc (the world's terrain), Tex (8.8 GB), Sound, Bake/Probe, Model. `PreComputedCulling/` holds 35k files of precomputed culling. The file layout is the BotW/TotK lineage (`.bgyml`, `.ainb`, Phive, RSDB).
- Shaders: 42,343 in [`shader_map.tsv`](shader_map.tsv) (the largest map so far), from `Shader/*.Nin_Ounce_NVN2.bfsha.zs`, `Layout2Shader/`, `Effect/`, `agl/`, `WorldMgr/` and the movie engine's `Movie/Ndve/*.dat.zs` (21 compute programs, see [Rendering](#rendering)). 42,323 translate and compile; 20 fail (18 translation: unimplemented Ampere instructions 0x243 ×4, 0x3a9 ×4, 0x481, ISBERD mode b8 and others; 2 Metal: "bracket nesting level exceeded maximum of 256").
- The rewriter rewrites the three modules with no cut of main; the sdk build carries [one cut](../../../dm/tools/sdk_patches.py) (the play-report submission, below).

## NPLN offline

The game initializes NPLN on its `Porter` thread (save-porting; RomFS strings `SeqExecutePorterConnectToNetwork`, `QueryCheckPorterSendRupeeLimit`) and aborts at the first failure. Three things came up, in boot order:

1. **The grpc poll strategy** (`grpc_poll_strategy`, default "all"): validated against an enum the default is not in → `nn::diag` abort with empty message parts (the sdk's varargs `AbortImpl`, whose no-op the host does not hook — the sdk build implements `nndiagAbort` → `AbortImpl(fn, expr, file, line, fmt, …)` → the hooked `VAbortImpl`, all empty). The value comes from `getenv`, which [hle_os.c](../../../dm/host/hle_os.c) answers from the profile's `game_env`.
2. **grpc's wakeup fds**: NPLN's grpc builds them on `nn::socket::EventFd` / `EventFdWrite` / `EventFdRead` (SDK 22's eventfd API; grpc's `wakeup_fd_eventfd.cc` aborts when it fails). The host now [backs each descriptor with a real pipe](../../../docs/reference/services.md) (hle_net.c), and `Poll` polls the read ends for real.
3. **Play report submissions**: the movie thread's "movie ended" report and the porter's "porter_savedata" report go through `prepo::detail::PlayReportImpl::Send`, whose real `AsyncContext` makes `AsyncContext::GetCompletionEvent` abort on its error path offline. [The sdk build's cut](../../../dm/tools/sdk_patches.py) makes `Send` return a zeroed context — "nothing pending", which `GetCompletionEvent` takes as already complete — and [hle_offline.c](../../../dm/host/hle_offline.c) hooks `GetCompletionEvent` to create the event and signal it at once, so the waiter proceeds and the game's reused event storage stays clean.

The game also reads `_npln:/npln_config.json`, which the update-only RomFS does not hold; the sdk's own grpc then runs on a built-in default. The overlay's stand-in satisfies the open.

## Rendering

The title, the intro's text scenes and the opening movie draw correctly (the movie's compositor is compute; its shaders are in the movie engine's own [NDVE files](../../../docs/reference/shaders.md#the-movie-engines-ndve-files-bare-nvn2-sections-no-bnsh), which the split reads since the sentinel learned the magic). The opening's heavy texture streaming outruns the 16 GB Mac's GPU memory: 290 upload staging blocks (13.5 GB swapped out), upload command buffers dropped with `kIOGPUCommandBufferCallbackErrorOutOfMemory`, and 11,800 textures awaiting re-upload at the worst stretch. The game logic keeps running (audio rendered 180,000 frames) but the picture degrades; [Memory](#memory) has what is measured and the plan.

## Memory

Brought up on a 16 GB M5, and the guest is most of it: `SetHeapSize` asks 0x18ce00000 (6.20 GB of a 7.12 GB heap region) and the alias region is 4.375 GB of virtual address memory, mapped to +3.75 GB by the opening ([+2.15 GB in the first 15 s](../../../docs/reference/memory.md#sizing-the-pool-and-alias-region-for-virtual-address-memory)).

The split at the first `kIOGPUCommandBufferCallbackErrorOutOfMemory` (2026-11-06, the opening's scene load, from the [census the host prints there](../../../dm/gfx/nvn/nvn_mtl.m)):

| What | Objects | MB |
|---|---|---|
| textures, the deswizzled private copies | 11,546 | 6,271 |
| shared buffers, the guest's pools, zero-copy and wired | 5,980 | 6,052 (one pool 2,432) |
| private buffers | 13 | 384 |
| **the residency set** | 17,539 | **12,707**, beside Metal's recommended working set of 12,124 |

The two big rows are the same bytes twice: the game writes its streamed textures into its own GPU pools (6.05 GB then, wired in 16 MB chunks as lookups reach them) and the host keeps a deswizzled private Metal texture of each (6.27 GB, 11,546 of them; 27,000 uploaded by the time the picture stopped). On the Switch 2 there is one copy. Adding the 6.20 GB heap, a 16 GB Mac has no room for both, and the game streams into a 9 GB `app_pool` as it would on hardware.

The failure after that has no back-pressure: the upload batches that fail mark their textures unwritten, their re-uploads need new staging (181 blocks, 262 switches, 8.3 GB), GPU allocated climbs to 19,248 MB and the deferred-release queue to 182,288, frames stop presenting at 232 s and the audio stalls. Nothing stops an allocation at the working set, and the footprint watchdog (24 GB on any Mac) never fires.

Plan:

1. **The private copy as a cache** (done): a copy the game has not resolved for two frames is dropped and made again from its pool at its next resolve, held to two fifths of Metal's recommended working set — [Private texture copies held to a budget](../../../docs/reference/memory.md#private-texture-copies-held-to-a-budget). The memory line now reads `private texture copies X MB of Y MB (N dropped, M rebuilt)`, which is what the opening's burst is to be measured with.
2. **The upload back-off** (open): a failed batch marks its textures unwritten and the next one refills the staging immediately; it should stand back for a frame or two instead, and its staging should go at once.
3. **The pool wiring** (6,052 MB of shared buffers): measure what a draw reaches against what only an upload reads — the residency line's "added by source line" names the code path — with `DM_NVN_POOL_CHUNKS` as the switch.
4. **If it still does not fit:** record the floor measured above and try a smaller `app_pool` in the profile, which shrinks both the game's pool and (through `SetHeapSize`) its heap; the game's own allocator may refuse.

Done when the opening runs its length with no GPU out-of-memory error, the footprint peaks under 80% of physical memory, and `shot_p1.png`, `shot_f1.png` and `shot_mv2.png` still match.

## Open

- **GPU memory in the opening**: the private copies now have a budget and a rebuild path ([Memory](#memory)); the burst that reaches it has not been re-run, and the drop/rebuild is verified only at a forced budget (5 dropped, 5 rebuilt, the title screen unchanged).
- **Frame rate**: the 20 fps is the movie compositor. The title screen and the opening play a 1920x1080 AV1 movie through the movie engine's own NDVE compute programs: with all 22 of their keys skipped (`DM_NVN_CS_SKIP`, the whole list from the map's `Ndve` rows) the same build runs 60 fps (p99 17.1 ms) where it runs 20 (p99 53 ms, 50 ms of it GPU), and the picture then loses the movie plane. So 33 ms a frame is the NDVE composite, which started to resolve when the registered tables replaced the stale provisional ones, the same change that made the picture correct.
  A frame runs 14 dispatches and 2,912,128 threads (`DM_NVN_CSLOG=1` names them by key). The cost is not with the threads and not with the code's size: `4f41ccf2` (1,843,200 threads, threadgroup 128x1x1) costs nothing measurable, while `a8b4fb48` (2 dispatches, 46,080 threads, threadgroup 32x1x1) is 12 of the 33 ms and `49dff010` + `7f7ff0f3` (777,600 threads together) about 5. In `a8b4fb48` it is the **probe chain**, not the atomics themselves: its per-pixel body claims a slot in a 1024-entry table in `cp_s4` through nine nested compare-and-swap retry loops. Rebuilt three ways (measurements, each restored after), the scene runs
  - 53 ms as built,
  - **42.9 ms** with one atomic exchange where the retry loop was,
  - **42.4 ms** with no atomic at all.

  So one atomic a pixel is free and the tenth of a frame is spent on **failed probes**. The chain is not the game's: `cp_s3` and `cp_s4` are the host's own raw-global-memory support — the pool table (`gmem_map`) and the **write log** (`gmem_log`, [dmsh_abi.h](../../../dm/gfx/nvn/dmsh_abi.h)) — and the probe is how every raw global store marks its guest page in a 1024-slot hash set. The set fills at once (a 1080p write touches about 2,000 pages), so nearly every store walks the chain and gives up, and the compare-and-swap is what it pays for.
  **The fix, measured**: a plain load before the CAS is exactly equivalent — the CAS could only have failed on a value the load already reads — and turns a read-modify-write into a read on the path every store takes. With it on the 16 movie programs that carry a write log, the same scene runs **24.8 ms (about 40 fps) instead of 53 (20)**, the movie still drawn. The pass is [`gmem_log_fast`](../../../dm/gfx/tools/dmsh_build.py) in the shader build; the cache this machine has was patched by hand for those 16 programs, so the chain version and a full shader rebuild are still to do. The other measurements behind it: 42.9 ms with one atomic exchange instead of the retry chain, 42.4 with no atomic at all, 60 fps (17.1 ms) with all 22 `Ndve` keys skipped, and `-O3` instead of `-O1` changing nothing. `DM_NVN_CSLOG=1`, `DM_NVN_CS_SKIP=<keys>` and `DM_NVN_CS_DUMP=<key>` are host diagnostics and stay. The audio desync follows from the frame rate.
  What is left is 22 ms of movie composite against the 16.7 ms a 60 fps frame has, and **none of it is the frame around it**: emptied of the whole movie chain the frame runs 1.6 ms of GPU, so a scene without a movie is already at the display period and the movie alone is short of 60 fps. Emptying bodies is what makes this readable — a skipped dispatch breaks the chain behind it (asked to skip `49dff010` and `7f7ff0f3` the frame went to 43 ms) and a frame that falls under the display period reads 16.7–17.0 whatever it did. On the title screen:

  | emptied | GPU a frame |
  |---|---|
  | nothing | 22.3–24.8 ms |
  | the six largest movie programs | 11.0 |
  | the whole movie chain | 1.6 |

  The six hold 12.5 of the 22 ms: `d15370a3` (36,534 lines of MSL a thread), `e6be82d8` (26,385), `9442573e` (23,739, 58 `threadgroup_barrier`s), `3f18f896` (15,967), `0a56002c` and `d72077c4` (11,311 each, 15,360 threads in 120 groups of 32x4).
  **The pool-table search is not the cost**, which is where this note pointed before. `0a56002c` and `9442573e` reach it once an access through twelve steps of two dependent loads, so every step was given twelve more dependent loads over the same table (13 times the loads, the results unchanged): 25.2 ms against 25.1. `-O3 -ffast-math` over the six: 22.0–24.2 against 22.3–24.8. Neither the loads nor the arithmetic move the frame while emptying a body does, so the 22 ms is the game's own pre-unrolled straight-line code running — these programs have no loop at all, 11,000 to 36,000 lines a thread, 32 or 128 threads a threadgroup, 25.6 KB of threadgroup memory in the two 11k ones — and no host switch reaches that.
  The next thing to look at was that threadgroup memory, and it is not it either: `0a56002c` and `d72077c4` hold 29.8 KB a group (1,024 + 5,400 + 1,024 words), which leaves Metal a single group on a core against the several the Switch 2's shared memory allows, so a 1.7 ms program (`49dff010`) was given 30 KB of threadgroup memory it writes one word of: the frame stayed 22.3–24.7 ms. Neither is it the encoder or the barriers around the dispatches (`DM_NVN_DISPATCH_OWN=1`: 21.9–24.4). Per program, emptying the other five and leaving one: `e6be82d8` 5.2 ms (16.2 against 11.0 for all six empty), `9442573e` 0.4, `d72077c4` −0.3 — so the six's 12.5 ms is mostly `e6be82d8` plus the three that run came too late to read. What is not in doubt is the ceiling: 22 ms of the game's own code against 16.7, with every host-side lever measured and none of them moving it.
  The method is [the graphics guide's](../../../docs/agents/04-graphics.md#measuring-what-one-compute-program-costs), `dm/gfx/tools/shader_ablate.py`.
- The 20 failing shaders (above): the first visible artifact they cause is not yet identified.
- `nvnCommandBufferSetComputeWorkloadPriority` is unimplemented (red stub, no effect seen).
- `nn::codec` AV1: "a packet refused with 12 pictures waiting for a released buffer" appears four times while the opening decodes (the log caps it); the movie plays through.
- **Past the intro is where it stops**: the game boots to the title screen (New Game / Options / ZELDA NOTES Setting), `A` starts the intro, and the intro is several AV1 streams (one ends after 5,947 pictures, the next after 9,254) running about eight minutes with the loads. A run through it does not stop by itself — an earlier note here said the process exits at the hand-over to the first scene, and what actually happened is that the shell that started the host was reaped, which took the host with it (the same run reached frame 11,100 and kept going once it was left alone). What does stop everything is the machine: four minutes into one of those runs **the Mac panicked in the GPU driver** (`IOGPUGroupMemory.cpp:286`, the record naming `dmhost` as the panicked task at 16.7 GB resident) — [the machine panics in the GPU driver before any cap in the host fires](../../../docs/reference/memory.md#the-machine-panics-in-the-gpu-driver-before-any-cap-in-the-host-fires). The watchdog now caps the footprint at the machine's RAM less 6 GB (10 GB here) and exits when the system has under 1 GB left, so a run on this machine ends itself rather than the machine.
  Two kinds of shader are missing where the first scene begins, and they are the first thing to fix, not the frame rate: `8692b34b521225be` and `83df46a0b1b379b4` are in the registry but have no library in the cache (two of the 20 that do not build), and 11 keys are not in the registry at all — `12d009abdddbb41b`, `1c0981be91762393`, `37b6b6175f323fed`, `903e22a1e9177e65`, `a5288d0a6c4971fd`, `ca5e29acf2872384`, `d17eefaff4f0bc23`, `d4171cf9adf0504b`, `e8c667282ba7bd9b`, `f81c2abf8d1249a9`, `faff48966ce047d8` — with `DM_NVN_SHDUMP` having written each one's `<key>.ctl` (72 bytes) and `<key>.code` to `run/shdump/`.
  Those dumps say what the gap is, and it is not a reader `shader_split.py` is missing. The 72 bytes are `nvn_ctl_lens`' key width for an NVN2 section (magic `0x98761234`, `+0x30` = 0xE0, so the section itself is 224 bytes of which the key hashes the first 72), and ten of the eleven code areas start with `0x020C0C81` where the package's own records carry `0x12345678`/`0x9` — a form this game's 3,589 split records never take (their control sections are all 224 bytes). Neither the 72 control bytes nor the code areas appear anywhere in the 26 GB RomFS image or in ExeFS (a full `mmap` search for the 16 bytes at control `+0x20` and for code slices), so these shaders are **not** sitting in a container in plain form: the game either reads them out of a compressed file that `shader_split.py` does not decompress, or builds them at load time. A rescan cannot find them either way (the registry's 42,346 rows are what the same splitter sees), so the next step is finding which file the game reads just before the `not in the shader map` line: `DM_FSLOG=<file>` writes every read, and [`fslog_paths.py`](../../../dm/tools/fslog_paths.py) resolves its offsets to RomFS paths (the log itself says `?` for a read through the image, which is most of them). A run held at frame 13,500 that way was streaming `/Effect/Dm_Kokiri_0115.Nin_Ounce_NVN2.vsetb.byml.zs` — the Kokiri area's effect settings, 1.75 MB into it — so it is at that scene load that the missing keys appear, and those files are `.zs` (zstd), which is why nothing inside them answers a search of the image.
  Until then the frame rate past the opening is unmeasured, and what it should be is known: the whole scene without the movie is 1.6 ms of GPU.
- Playtesting past the opening is not reached for that reason. Input does work: `DM_CTL` key lines drive the pad (New Game, and the narration pages were seen turning under `A`).

## Driving it on the Mac

The work folder's `run/env.sh` sets the switches and `run/play.sh` boots (headless with `DM_CTL`, or `play.sh window`); screenshots and presses go through `ctl.txt` lines (`shot <path>`, `A`). The build's own run command is in its last log line. `rebuild.sh` rebuilds the host for the profile.

## Found on this game

- [The overlay on every read-only content mount](../../../docs/reference/packing.md#the-overlay-serves-every-read-only-content-mount) (a game may mount its content under several names; this one mounts its RomFS as `content` and again as `_npln`)
- [nn::socket::EventFd, the guest's wakeup descriptors](../../../docs/reference/services.md#nnsocketeventfd-the-guests-wakeup-descriptors)
- [prepo's PlayReport::Send offline](../../../docs/reference/services.md#prepos-playreportsend-offline-the-asynccontext-cut)
- [The footprint watchdog's cap is a constant on every Mac](../../../docs/reference/memory.md#the-footprint-watchdogs-cap-is-a-constant-on-every-mac)
- [Private texture copies held to a budget](../../../docs/reference/memory.md#private-texture-copies-held-to-a-budget)
- [The machine panics in the GPU driver before any cap in the host fires](../../../docs/reference/memory.md#the-machine-panics-in-the-gpu-driver-before-any-cap-in-the-host-fires)
- [The write log's compare-and-swap chain at every raw global store](../../../docs/reference/shaders.md#the-write-logs-compare-and-swap-chain-at-every-raw-global-store)
