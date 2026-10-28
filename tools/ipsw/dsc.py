#!/usr/bin/env python3
"""Read images out of a split dyld shared cache (the main file and its subcaches) without extracting it.

usage: dsc.py CACHE_DIR deps NAME...   the install path and linked dylibs of each image whose path ends with NAME
       dsc.py CACHE_DIR gl             QuartzCore's links and how often GLSL markers occur in its __TEXT

CACHE_DIR holds dyld_shared_cache_arm64* (System/Library/Caches/com.apple.dyld of a mounted SystemOS).
The second form is how the OpenGL ES renderer of CoreAnimation was looked for in newer systems
(docs/plan/2026-10-26-roadmap.md, section 3).
"""
import glob
import os
import struct
import sys

LOAD_DYLIBS = (0xc, 0x80000018, 0x8000001f, 0x80000023)
GL_MARKERS = (b'texture2D', b'GL_EXT_shader_framebuffer_fetch', b'gl_LastFragData', b'#extension', b'EAGLContext')

directory = sys.argv[1]
files = sorted(f for f in glob.glob(os.path.join(directory, 'dyld_shared_cache_arm64*'))
               if not f.endswith(('.symbols', '.map', '.atlas')))
data = {f: open(f, 'rb').read() for f in files}
maps = []
for f, b in data.items():
    if not b.startswith(b'dyld_v1'):
        continue
    mapping_offset, mapping_count = struct.unpack_from('<II', b, 0x10)
    for i in range(mapping_count):
        address, size, offset, _, _ = struct.unpack_from('<QQQII', b, mapping_offset + 32 * i)
        maps.append((address, size, offset, f))
main = data[min((f for f in files if '.' not in os.path.basename(f)), key=len)]
images_offset, images_count = struct.unpack_from('<II', main, 0x1c0)
if images_count == 0:
    images_offset, images_count = struct.unpack_from('<II', main, 0x18)


def at(address, n):
    for a, s, o, f in maps:
        if a <= address < a + s:
            return data[f][o + address - a:o + address - a + n]
    raise KeyError(hex(address))


def images():
    for i in range(images_count):
        address, _, _, path_offset, _ = struct.unpack_from('<QQQII', main, images_offset + 32 * i)
        yield address, main[path_offset:main.index(b'\0', path_offset)].decode()


def commands(address):
    ncmds, sizeofcmds = struct.unpack_from('<II', at(address, 32), 16)
    cmds = at(address + 32, sizeofcmds)
    p = 0
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', cmds, p)
        yield cmd, cmds[p:p + size]
        p += size


def dylibs(address):
    for cmd, body in commands(address):
        if cmd in LOAD_DYLIBS:
            name_offset, = struct.unpack_from('<I', body, 8)
            yield body[name_offset:body.index(b'\0', name_offset)].decode()


def text(address):
    for cmd, body in commands(address):
        if cmd == 0x19 and body[8:24].rstrip(b'\0') == b'__TEXT':
            vmaddr, vmsize = struct.unpack_from('<QQ', body, 24)
            return at(vmaddr, vmsize)
    return b''


if sys.argv[2] == 'deps':
    for address, path in images():
        if any(path.endswith(n) for n in sys.argv[3:]):
            print(path)
            for dylib in dylibs(address):
                print('   ', dylib)
elif sys.argv[2] == 'gl':
    for address, path in images():
        if path.endswith('/QuartzCore'):
            print(path, 'in', os.path.basename(min(files, key=len)))
            for dylib in dylibs(address):
                if 'OpenGLES' in dylib or dylib.endswith('/Metal'):
                    print('   links', dylib)
            body = text(address)
            for marker in GL_MARKERS:
                print(f'    {marker.decode():34s} {body.count(marker)}')
            break
else:
    sys.exit(__doc__)
