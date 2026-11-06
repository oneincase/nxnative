#!/usr/bin/env python3
# Empty the kernel body of chosen programs in a built shader cache, to measure what each one costs a frame, and put them back.
# Usage: shader_ablate.py empty <cache dir> <key>...     (16 hex digits, the file name before _b.metal)
#        shader_ablate.py restore <cache dir> [<key>...] (no key = every backup this tool holds in that cache)
#        shader_ablate.py list <cache dir>
#
# Why emptying and not DM_NVN_CS_SKIP: a skipped dispatch is not encoded, so whatever reads its output waits for something that never
# runs (Ocarina of Time's movie chain stalls the game) and the frame is no longer the frame being measured. An emptied body keeps the
# dispatch, its bindings, its threadgroup size and every barrier around it, and only the work goes: the picture is wrong afterwards,
# the timing is the one wanted.
# Two other traps, both measured on the Ocarina of Time movie (dm/games/0400486024DEC000):
#   - a frame whose GPU time falls under the display period reads the period (16.7-17.0 ms at 60 Hz) whatever it did, so emptying one
#     program of a 23 ms frame cannot say how much it saved; only a set whose total stays above the period can be read, so bisect sets;
#   - the cost of a program is not its thread count, its arithmetic or its loads (Ocarina of Time's movie: 288 more dependent loads in
#     the pool-table search changed nothing, -O3 -ffast-math changed nothing, emptying the body took 2 of the 23 ms), so measure the body.
#
# The .metal is truncated at the kernel's opening brace (the body is what runs; the helper functions before it stay compiled) and the
# metallib is rebuilt with the build's own flags (dmsh_build.py: -O1 -fpreserve-invariance). The original pair is kept in <cache dir>/
# .ablate/ and restore puts it back; a cache rebuilt from source makes the backups moot, so run restore before a build.
import os, re, shutil, subprocess, sys

CACHE = '.ablate'   # inside the cache directory: <key>_b.metal / <key>_b.metallib as they were
METAL = ['xcrun', '-sdk', 'macosx', 'metal', '-c', '-O1', '-fpreserve-invariance']
LIB = ['xcrun', '-sdk', 'macosx', 'metallib']


def path(cache, key, ext): return os.path.join(cache, '%s_b.%s' % (key, ext))


def backup(cache):
    d = os.path.join(cache, CACHE)
    os.makedirs(d, exist_ok=True)
    return d

def kept(cache):   # the keys this tool has emptied in this cache and not yet restored
    return sorted(f[:-len('_b.metal')] for f in os.listdir(backup(cache)) if f.endswith('_b.metal'))


def empty(cache, keys):
    d = backup(cache)
    for key in keys:
        mt, lib = path(cache, key, 'metal'), path(cache, key, 'metallib')
        if not os.path.exists(mt): print('[RED] %s: no %s' % (key, mt)); continue
        if not os.path.exists(os.path.join(d, os.path.basename(mt))):   # keep the first backup: emptying twice keeps the original
            shutil.copy2(mt, d)
            if os.path.exists(lib): shutil.copy2(lib, d)
        src = open(mt).read()
        m = re.search(r'kernel\s+void\s+main0\s*\(', src)
        if not m: print('[RED] %s: no kernel main0' % key); continue
        i = m.end(); depth = 1                                            # the parameter list holds attributes with parentheses
        while depth:
            depth += {'(': 1, ')': -1}.get(src[i], 0); i += 1
        brace = src.index('{', i)
        open(mt, 'w').write(src[:brace] + '{ }\n')
        air = os.path.join(d, key + '.air')
        r = subprocess.run(METAL + [mt, '-o', air], capture_output=True)
        if r.returncode:
            shutil.copy2(os.path.join(d, os.path.basename(mt)), mt)
            print('[RED] %s: %s' % (key, r.stderr.decode()[:400])); continue
        r = subprocess.run(LIB + [air, '-o', lib], capture_output=True)
        os.remove(air)
        if r.returncode:
            shutil.copy2(os.path.join(d, os.path.basename(mt)), mt)
            shutil.copy2(os.path.join(d, os.path.basename(lib)), lib)
            print('[RED] %s: %s' % (key, r.stderr.decode()[:400])); continue
        print('%s: empty (%s lines removed)' % (key, src.count('\n') - src[:brace].count('\n')))


def restore(cache, keys):
    d = backup(cache)
    for key in keys or kept(cache):
        for ext in ('metal', 'metallib'):
            b = os.path.join(d, '%s_b.%s' % (key, ext))
            if os.path.exists(b): shutil.copy2(b, path(cache, key, ext))
        print('%s: restored' % key)


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('empty', 'restore', 'list'):
        sys.exit(__doc__ if __doc__ else 'usage: shader_ablate.py empty|restore|list <cache dir> [<key>...]')
    what, cache, keys = sys.argv[1], sys.argv[2], [k.lower() for k in sys.argv[3:]]
    if not os.path.isdir(cache): sys.exit('[RED] no cache directory %s' % cache)
    if what == 'empty': empty(cache, keys or sys.exit('[RED] empty takes the keys to empty'))
    elif what == 'restore': restore(cache, keys)
    else:
        for k in kept(cache): print('%s: emptied, backup in %s' % (k, os.path.join(cache, CACHE)))
