"""textureGatherOffsets with per-lane computed offsets (dmsh_build.py gather_rt_reads): a gather whose int2 offset
is not two plain integers becomes one explicit texel read per component (a gather's .w is the bilinear footprint's
origin texel, floor(uv*size + off - 0.5)); sites with constant offsets and spirv-cross's wrapper templates stay as
they were."""
import ast
from pathlib import Path
import re
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
tree = ast.parse((TOOLS / 'dmsh_build.py').read_text())
selected = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == 'gather_rt_reads')
            or (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in ('GATHER_RT', 'GATHER_RT_OFF', 'GATHER_RT_H') for t in n.targets))]
scope = {'re': re}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(TOOLS / 'dmsh_build.py'), 'exec'), scope)
gather_rt_reads = scope['gather_rt_reads']

HEAD = '''#include <metal_stdlib>
using namespace metal;
template<typename T> static inline __attribute__((always_inline)) vec<T, 4> dm_gather4(T a, T b, T c, T d) { return vec<T, 4>(a, b, c, d); }
template<typename Tex, typename... Tp>
using spvGatherReturn = decltype(declval<Tex>().gather(declval<sampler>(), declval<Tp>()...));
// Wrapper function that processes a device texture gather with a constant offset array.
template<typename Tex, typename Toff, typename... Tp>
inline spvGatherReturn<Tex, Tp...> spvGatherConstOffsets(const device Tex& t, sampler s, Toff coffsets, component c, Tp... params) METAL_CONST_ARG(c)
{
    spvGatherReturn<Tex, Tp...> rslts[4];
    for (uint i = 0; i < 4; i++)
    {
        switch (c)
        {
            case component::x: rslts[i] = t.gather(s, params..., coffsets[i], component::x); break;
        }
    }
    return spvGatherReturn<Tex, Tp...>(rslts[0].w, rslts[1].w, rslts[2].w, rslts[3].w);
}
'''
SITE_RT = 'spvDescriptorSet0.cp_t_tcb_10.gather(spvDescriptorSet0.cp_t_tcb_10Smplr, _10098, int2(_3042, _3044), component::x).w'
SITE_CONST = 'spvDescriptorSet0.cp_t_tcb_10.gather(spvDescriptorSet0.cp_t_tcb_10Smplr, select(_10145, float2(0.0), isnan(_10145)), int2(-1, 0), component::x).w'


class Rewrite(unittest.TestCase):
    def test_runtime_site_becomes_a_read(self):
        msl = HEAD + 'kernel void k() { float4 v = float4(' + SITE_RT + '); }\n'
        out = gather_rt_reads(msl)
        self.assertIn('dm_gather_rt(spvDescriptorSet0.cp_t_tcb_10, spvDescriptorSet0.cp_t_tcb_10Smplr, _10098, int2(_3042, _3044), component::x)', out)
        self.assertNotIn(SITE_RT, out)
        self.assertIn('int2 i = int2(floor(uv * float2(t.get_width(), t.get_height()) + float2(off) - 0.5));', out)

    def test_constant_site_and_wrapper_stay(self):
        msl = HEAD + 'kernel void k() { float4 v = float4(' + SITE_CONST + '); }\n'
        self.assertEqual(gather_rt_reads(msl), msl)

    def test_no_gather_no_change(self):
        msl = HEAD + 'kernel void k() { float4 v = t.read(uint2(0)); }\n'
        self.assertEqual(gather_rt_reads(msl), msl)

    def test_helper_injected_once(self):
        msl = HEAD + 'kernel void k() { float4 v = float4(' + SITE_RT + ', ' + SITE_RT + '); }\n'
        out = gather_rt_reads(msl)
        self.assertEqual(out.count('float dm_gather_rt('), 1)
        self.assertEqual(out.count('dm_gather_rt(spvDescriptorSet0.cp_t_tcb_10'), 2)

    def test_compare_form_untouched(self):
        site = 'spvDescriptorSet0.cp_t_tcb_10.gather_compare(spvDescriptorSet0.cp_t_tcb_10Smplr, _10098, int2(_3042, _3044), 0.5).w'
        msl = HEAD + 'kernel void k() { float4 v = float4(' + site + '); }\n'
        self.assertIn(site, gather_rt_reads(msl))


if __name__ == '__main__':
    unittest.main()
