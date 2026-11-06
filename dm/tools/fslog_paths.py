#!/usr/bin/env python3
# Resolve the offsets in a DM_FSLOG file to paths in the game's RomFS image: which file the game was reading, and how much of it.
# Usage: fslog_paths.py <fslog> <RomFS image> [count]
#   DM_FSLOG=path host …       writes: seconds <tab> path <tab> offset <tab> bytes <tab> buffer (path is "?" for a read through the
#                              RomFS image, which is most of them — that is what this resolves)
#   fslog_paths.py fslog.tsv extract/v131072/RomFS.img [12]
#                              prints the files by how many reads touched them, then the last reads with their file and offset in it
#
# The funny-business case it was written for: Ocarina of Time reaches the first scene, logs `[RED] shader <key> is not in the shader map`,
# and the shaders are nowhere in the RomFS image in plain form — so the question is which file the game had just been streaming. At the
# end of that run it was /Effect/Dm_Kokiri_0115.Nin_Ounce_NVN2.vsetb.byml.zs, the Kokiri area's effect settings, i.e. the scene load.
# A .zs file is zstd-compressed, so nothing inside it answers a plain search of the image.
import bisect, collections, os, sys


def files_of(image):
    """(start, end, path) of every file in the image, sorted by where it sits."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from romfs import Image
    img = Image(image)
    out = []

    def walk(k, prefix):
        for name, j in img.children(k):
            a, b, _, _, is_file, _ = img.entry(j)
            if is_file: out.append((a, a + b, prefix + '/' + name))
            else: walk(j, prefix + '/' + name)
    walk(0, '')
    out.sort()
    return out


def main():
    if len(sys.argv) < 3: sys.exit(__doc__ or 'usage: fslog_paths.py <fslog> <RomFS image> [count]')
    log, image = sys.argv[1], sys.argv[2]
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    files = files_of(image)
    starts = [f[0] for f in files]

    def who(off):
        i = bisect.bisect_right(starts, off) - 1
        if i >= 0 and files[i][0] <= off < files[i][1]:
            a, b, p = files[i]
            return '%s (+%d)' % (p, off - a)
        return '?   (outside every file: the image header or the entry table)'
    counts = collections.Counter()
    rows = []
    for line in open(log, errors='replace'):
        c = line.rstrip('\n').split('\t')
        if len(c) < 4: continue
        try: off = int(c[2])
        except ValueError: continue
        who_ = c[1] if c[1] != '?' else who(off)
        counts[who_] += 1
        rows.append((c[0], off, c[3], who_))
    print('%d reads, %d files in the image' % (len(rows), len(files)))
    for p, n in counts.most_common(top): print('%7d  %s' % (n, p))
    print('--- the last %d reads ---' % min(top, len(rows)))
    for r in rows[-top:]: print('%10s  %-9s %6s B  %s' % (r[0], hex(r[1]), r[2], r[3]))


if __name__ == '__main__': main()
