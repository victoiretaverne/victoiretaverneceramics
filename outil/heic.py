"""Décodeur HEIC minimal : grille de tuiles HEVC décodées par ffmpeg."""
import struct, subprocess, sys, os, tempfile
from PIL import Image
def boxes(b, off, end):
    while off < end:
        size, typ = struct.unpack(">I4s", b[off:off+8]); hdr = 8
        if size == 1: size = struct.unpack(">Q", b[off+8:off+16])[0]; hdr = 16
        elif size == 0: size = end - off
        yield typ.decode("latin1"), off+hdr, off+size
        off += size
def lire(path):
    b = open(path, "rb").read()
    meta = next((s, e) for t, s, e in boxes(b, 0, len(b)) if t == "meta")
    m = {t: (s, e) for t, s, e in boxes(b, meta[0]+4, meta[1])}
    pitm = struct.unpack(">H", b[m["pitm"][0]+4:m["pitm"][0]+6])[0]
    # iinf
    s, e = m["iinf"]; v = b[s]; s += 4; n = struct.unpack(">H" if v == 0 else ">I", b[s:s+(2 if v == 0 else 4)])[0]; s += 2 if v == 0 else 4
    types = {}
    for t, cs, ce in boxes(b, s, e):
        ver = b[cs]; p = cs+4
        if ver >= 2:
            iid = struct.unpack(">H" if ver == 2 else ">I", b[p:p+(2 if ver == 2 else 4)])[0]; p += 2 if ver == 2 else 4
            p += 2; types[iid] = b[p:p+4].decode("latin1")
    # iloc
    s, e = m["iloc"]; ver = b[s]; p = s+4
    a = b[p]; c = b[p+1]; os_, ls, bo = a >> 4, a & 15, c >> 4; ix = c & 15 if ver in (1, 2) else 0; p += 2
    cnt = struct.unpack(">H" if ver < 2 else ">I", b[p:p+(2 if ver < 2 else 4)])[0]; p += 2 if ver < 2 else 4
    def rd(n):
        nonlocal p
        if n == 0: return 0
        v = int.from_bytes(b[p:p+n], "big"); p += n; return v
    loc = {}
    for _ in range(cnt):
        iid = rd(2 if ver < 2 else 4); meth = 0
        if ver in (1, 2): meth = rd(2) & 15
        rd(2); base = rd(bo); ne = rd(2); ext = []
        for _ in range(ne):
            if ix: rd(ix)
            eo = rd(os_); el = rd(ls); ext.append((base+eo, el))
        loc[iid] = (meth, ext)
    idat = m.get("idat")
    def data(iid):
        meth, ext = loc[iid]
        src = b[idat[0]:idat[1]] if meth == 1 else b
        return b"".join(src[o:o+l] for o, l in ext)
    # iprp : ipco + ipma
    iprp = {t: (s2, e2) for t, s2, e2 in boxes(b, *m["iprp"])}
    props = [(t, s2, e2) for t, s2, e2 in boxes(b, *iprp["ipco"])]
    s, e = iprp["ipma"]; ver = b[s]; fl = int.from_bytes(b[s+1:s+4], "big"); p = s+4
    n = struct.unpack(">I", b[p:p+4])[0]; p += 4; assoc = {}
    for _ in range(n):
        iid = struct.unpack(">H" if ver < 1 else ">I", b[p:p+(2 if ver < 1 else 4)])[0]; p += 2 if ver < 1 else 4
        k = b[p]; p += 1; L = []
        for _ in range(k):
            if fl & 1: v2 = struct.unpack(">H", b[p:p+2])[0] & 0x7fff; p += 2
            else: v2 = b[p] & 0x7f; p += 1
            L.append(v2)
        assoc[iid] = L
    def prop(iid, typ):
        for ix2 in assoc.get(iid, []):
            t, s2, e2 = props[ix2-1]
            if t == typ: return b[s2:e2]
    # iref dimg
    dimg = {}
    if "iref" in m:
        s, e = m["iref"]; ver = b[s]
        for t, cs, ce in boxes(b, s+4, e):
            q = cs; w = 2 if ver == 0 else 4
            fr = int.from_bytes(b[q:q+w], "big"); q += w; nr = struct.unpack(">H", b[q:q+2])[0]; q += 2
            to = [int.from_bytes(b[q+i*w:q+(i+1)*w], "big") for i in range(nr)]
            if t == "dimg": dimg[fr] = to
    def hvcc_annexb(h):
        out = b""; q = 22; na = h[q]; q += 1
        for _ in range(na):
            q += 1; nn = struct.unpack(">H", h[q:q+2])[0]; q += 2
            for _ in range(nn):
                l = struct.unpack(">H", h[q:q+2])[0]; q += 2; out += b"\0\0\0\1" + h[q:q+l]; q += l
        return out
    def nal_annexb(d):
        out = b""; q = 0
        while q < len(d):
            l = struct.unpack(">I", d[q:q+4])[0]; q += 4; out += b"\0\0\0\1" + d[q:q+l]; q += l
        return out
    def decode_hvc1(iid):
        bs = hvcc_annexb(prop(iid, "hvcC")) + nal_annexb(data(iid))
        with tempfile.NamedTemporaryFile(suffix=".hevc", delete=False) as f: f.write(bs)
        out = f.name + ".png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "hevc", "-i", f.name, "-frames:v", "1", out], check=True)
        im = Image.open(out).convert("RGB"); im.load(); os.remove(f.name); os.remove(out); return im
    def rendre(iid):
        if types[iid] == "hvc1": im = decode_hvc1(iid)
        elif types[iid] == "grid":
            g = data(iid); flags = g[1]; rows, cols = g[2]+1, g[3]+1; w4 = 4 if flags & 1 else 2
            W = int.from_bytes(g[4:4+w4], "big"); H = int.from_bytes(g[4+w4:4+2*w4], "big")
            tiles = [decode_hvc1(t) for t in dimg[iid]]; tw, th = tiles[0].size
            im = Image.new("RGB", (cols*tw, rows*th))
            for i, t in enumerate(tiles): im.paste(t, ((i % cols)*tw, (i//cols)*th))
            im = im.crop((0, 0, W, H))
        else: raise SystemExit("type non géré: " + types[iid])
        irot = prop(iid, "irot")
        if irot: im = im.rotate(90*(irot[0] & 3), expand=True)
        imir = prop(iid, "imir")
        if imir: im = im.transpose(Image.FLIP_LEFT_RIGHT if imir[0] & 1 else Image.FLIP_TOP_BOTTOM)
        return im
    return rendre(pitm)
if __name__ == "__main__":
    lire(sys.argv[1]).save(sys.argv[2], quality=92); print("ok", sys.argv[2])
