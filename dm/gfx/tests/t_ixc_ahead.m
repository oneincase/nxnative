// Indirect draws converted ahead (ixc_run): the look-ahead goes past a uniform update that writes no record it took, so a later indirect draw in the
// same render pass finds its conversion and the pass stays whole (Ocarina of Time's grass: an update between each indirect mesh draw split 5 passes a
// frame), and past an indirect mesh draw whose writes go to a storage buffer that holds no record (ixc_writes_spare). An update that writes a later draw's record still stops it: that draw is converted after the update and draws what the update wrote (its pass ends to land
// the update first, ubd_hits)
#import <Foundation/Foundation.h>
#define nvn_game_fps nvn_game_fps_mtl_default
#include "../nvn/nvn_mtl.m"
#undef nvn_game_fps
#define g_ft g_ft_hle
#include "../nvn/hle_nvn.c"
#undef g_ft
uint64_t g_t0_ns;
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod;
int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }

enum { PIXELS = 8, QUADS = 7, TRIANGLES = 4 };
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s (line %d)\n", label, __LINE__); } } while (0)
static _Alignas(16) uint8_t storage[4096];

// Two indirect quad draws with a uniform update between them. overlap: the update writes the second draw's count (4: the quad covers the target);
// otherwise it writes elsewhere and the CPU gave the second record 4. The first record draws nothing. Returns the centre pixel's red
static unsigned run_(prog_t *pg, uint8_t *pool, int overlap, int opener, uint64_t *splits, unsigned *all_red);
static unsigned run(prog_t *pg, uint8_t *pool, int overlap, uint64_t *splits) { unsigned all; return run_(pg, pool, overlap, 0, splits, &all); }
// opener: an ordinary triangle draw (half the target) opens the pass, then the indirect quad of the second record (the whole target) follows, with nothing between: the quad's
// conversion is made before the pass opens (ixc_prepass), not by splitting it. *all_red: every pixel red, the quad drew
static unsigned run_(prog_t *pg, uint8_t *pool, int overlap, int opener, uint64_t *splits, unsigned *all_red) {
    uint32_t *first = (uint32_t *)(pool + 256), *second = (uint32_t *)(pool + 512);   // {count, instances, first, base instance}
    first[0] = 0; first[1] = 1; first[2] = 0; first[3] = 0;
    second[0] = overlap ? 0 : 4; second[1] = 1; second[2] = 0; second[3] = 0;
    uint32_t four = 4;
    NVNcommandBuffer cb = {0};
    CB(&cb)->cur = storage; CB(&cb)->end = storage + sizeof storage;
    h_nvnCommandBufferBeginRecording(&cb);
    h_nvnCommandBufferBindProgram(&cb, (const NVNprogram *)pg, 3);   // recorded, as a game binds it: a pass replayed from the stream (g_defer) takes it from there
    if (opener) {
        h_nvnCommandBufferDrawArrays(&cb, (NVNdrawPrimitive)TRIANGLES, 0, 3);
        h_nvnCommandBufferDrawArraysIndirect(&cb, (NVNdrawPrimitive)QUADS, (uint64_t)(uintptr_t)second);
    } else {
    h_nvnCommandBufferDrawArraysIndirect(&cb, (NVNdrawPrimitive)QUADS, (uint64_t)(uintptr_t)first);
    h_nvnCommandBufferUpdateUniformBuffer(&cb, (uint64_t)(uintptr_t)(overlap ? (uint8_t *)second : pool + 1024), sizeof four, 0, sizeof four, &four);
    h_nvnCommandBufferDrawArraysIndirect(&cb, (NVNdrawPrimitive)QUADS, (uint64_t)(uintptr_t)second);
    }
    NVNcommandHandle handle = h_nvnCommandBufferEndRecording(&cb);

    static tex_t keep_rt; static __strong id<MTLTexture> keep_out;   // the opener runs draw into one target, as a game's main pass does frame after frame (ixc_learn keys on it)
    tex_t rt = {.magic = MAGIC('T', 'E', 'X', 0), .serial = opener && keep_rt.serial ? keep_rt.serial : nvn_new_serial()};
    rt.d = (nvn_texdesc){.target = NVN_TEXTURE_TARGET_2D, .format = NVN_FORMAT_RGBA8, .width = PIXELS, .height = PIXELS, .depth = 1, .levels = 1, .samples = 1};
    rt.mem = pool + (opener ? 0x2000 : 0x3000);   // where the target lives: the opener's is the one a split is learned for (ixc_learn keys on storage)
    MTLTextureDescriptor *td = tex_desc(&rt, 0); td.storageMode = MTLStorageModeShared;
    id<MTLTexture> out = opener && keep_out ? keep_out : [g_dev newTextureWithDescriptor:td];
    if (!(opener && keep_out)) { res_add(out); mtl_tex_init(&rt); serial_put(rt.serial, out); }
    if (opener) { keep_rt = rt; keep_out = out; }
    uint8_t pixels[PIXELS * PIXELS * 4] = {0};
    [out replaceRegion:MTLRegionMake2D(0, 0, PIXELS, PIXELS) mipmapLevel:0 withBytes:pixels bytesPerRow:PIXELS * 4];
    state_reset(); memset(&R, 0, sizeof R);
    atomic_fetch_add(&g_cur_frame, 1);   // each run is a frame of its own (ixc_pass_opened counts passes per frame)
    mtl_sub_begin(); mtl_sub_index(&handle, 1);
    R.has_rt = 1; R.rt.n = 1; R.rt.color[0] = &rt;
    S.ds.dt = S.ds.dw = S.ds.st = 0; S.poly.cull = 0; S.color.blend_en = 0; S.chmask.mask = 0xffff;
    uint64_t s0 = g_ixc_splits;
    mtl_exec((const uint8_t *)(uintptr_t)handle);
    CHECK(mtl_wait(mtl_sub_commit(), 10000000000ull) && !mtl_last_commit_error(), "the submission completes");
    *splits = g_ixc_splits - s0;   // after the commit: a pass may be deferred and encoded there (g_defer)
    [out getBytes:pixels bytesPerRow:PIXELS * 4 fromRegion:MTLRegionMake2D(0, 0, PIXELS, PIXELS) mipmapLevel:0];
    if (!opener) mtl_tex_release(&rt);
    *all_red = 1; for (int i = 0; i < PIXELS * PIXELS; i++) *all_red &= pixels[i * 4] == 255;
    return pixels[((PIXELS / 2) * PIXELS + PIXELS / 2) * 4];
}

// A draw's storage writes and the conversions (ixc_writes_spare): an indirect mesh draw whose mesh stage adds to a counter in a bound storage buffer
static void writes_spare(void) {
    NvProg *pr = [NvProg new]; NvShader *ms = [NvShader new]; pr->sh[4] = ms;
    ms->rf.nb = 1; ms->rf.b[0] = (nvn_rbind){.kind = NVN_RB_SBUFP, .rw = 1, .reg = 3};
    state_reset();
    S.ssbo[4][3] = (p_bind_buf){.addr = 0x10000, .size = 64};
    g_ixc_n = 1; g_ixc[0] = (ixc_ent){.ind = 0x20000, .prim = DM_PRIM_MESH_TASKS, .itype = -1};
    CHECK(ixc_writes_spare(pr), "a storage buffer away from the records leaves the conversions standing");
    S.ssbo[4][3] = (p_bind_buf){.addr = 0x20000 - 32, .size = 40};
    CHECK(!ixc_writes_spare(pr), "a storage buffer over a record drops them");
    S.ssbo[4][3] = (p_bind_buf){.addr = 0x10000, .size = 64}; ms->rf.b[0].kind = NVN_RB_GMEM;
    CHECK(!ixc_writes_spare(pr), "a raw-memory write drops them");
    ms->rf.b[0].kind = NVN_RB_SBUFP; g_ixc_n = 2; g_ixc[1] = (ixc_ent){.ind = 0x30000, .ibuf = 0x40000, .prim = 4, .itype = 0};
    CHECK(!ixc_writes_spare(pr), "an indexed expansion among the conversions drops them");
    g_ixc_n = 0; state_reset();
}

int main(void) { @autoreleasepool {
    mtl_init();
    writes_spare();
    NSError *err = nil;
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:@"#include <metal_stdlib>\nusing namespace metal;\n"
                                                      "vertex float4 v(uint i [[vertex_id]]){const float2 p[4]={float2(-1,-1),float2(1,-1),float2(1,1),float2(-1,1)};return float4(p[i%4],0,1);}\n"
                                                      "fragment float4 f(){return float4(1,0,0,1);}" options:nil error:&err];
    if (!lib) { fprintf(stderr, "%s\n", err.localizedDescription.UTF8String); return 2; }
    size_t bytes = 64 * 1024;
    uint8_t *pool = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (pool == MAP_FAILED) return 2;
    NVNmemoryPool physical; pool_builder_t builder = {.mem = pool, .size = bytes, .flags = 0x24};
    if (!h_nvnMemoryPoolInitialize(&physical, (const NVNmemoryPoolBuilder *)&builder)) return 2;
    NvProg *pr = [NvProg new];
    pr->sh[0] = [NvShader new]; pr->sh[1] = [NvShader new];
    pr->sh[0]->fn = [lib newFunctionWithName:@"v"]; pr->sh[1]->fn = [lib newFunctionWithName:@"f"];
    pr->sh[1]->stage = 1; pr->sh[1]->rf.color_known = 1; pr->sh[1]->rf.color_mask = 1;
    prog_t pg = {.serial = nvn_new_serial()};
    serial_put(pg.serial, pr);   // NOLINT(clang-analyzer-osx.cocoa.RetainCount): g_by_serial holds pr until serial_del
    uint64_t splits = 0;
    unsigned red = run(&pg, pool, 0, &splits);
    CHECK(red == 255, "an update elsewhere: the second draw draws its record's 4 vertices");
    CHECK(splits == 0, "an update elsewhere: the second draw was converted with the first, the pass is not split");
    red = run(&pg, pool, 1, &splits);
    CHECK(red == 255, "an update of the second record: the second draw draws what the update wrote");
    unsigned all = 0;
    run_(&pg, pool, 0, 1, &splits, &all);
    CHECK(all && splits == 1, "an indirect quad after the draw that opened its pass: the first time it splits the pass, which the host learns (ixc_learn), and draws its record");
    uint64_t runs0 = g_ixc_runs, pre0 = g_ixc_pre;
    run_(&pg, pool, 0, 1, &splits, &all);
    CHECK(all, "the next time it draws its record too");
    CHECK(splits == 0 && g_ixc_runs > runs0 && g_ixc_pre > pre0, "and its conversion is made before the pass opens (ixc_prepass): the pass is not split");
    g_ixc_pre_off = 1;   // DM_NVN_IXC_PRE=0: converted at its place, the pass split as before
    run_(&pg, pool, 0, 1, &splits, &all);
    CHECK(all && splits == 1, "with DM_NVN_IXC_PRE=0 the same quad splits its pass and still draws");
    g_ixc_pre_off = 0;
    { uint64_t sc0 = g_ixc_pre_scans; run(&pg, pool, 0, &splits); CHECK(g_ixc_pre_scans == sc0, "a pass no split has met is not scanned"); }
    h_nvnMemoryPoolFinalize(&physical);
    serial_del(pg.serial);
    mtl_drain(); munmap(pool, bytes);
    printf("t_ixc_ahead: %d checks, %d failed\n", checks, failed);
    return failed != 0;
} }
