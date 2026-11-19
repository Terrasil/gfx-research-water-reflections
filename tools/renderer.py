from __future__ import annotations
import platform
import sys

import moderngl as gl
import numpy as np
from PIL import Image
from protocol import ROOT, STUDY


def shader(name, diagnostics=False):
    lines = []
    for line in (ROOT / "shaders" / name).read_text(encoding="utf-8").splitlines():
        if line.startswith('#include "'):
            lines.append(shader(line.split('"')[1]))
        else:
            lines.append(line)
            if diagnostics and line.startswith("#version"):
                lines.append("#define DIAGNOSTICS 1")
    return "\n".join(lines) + "\n"


class Renderer:
    def __init__(self, backend, device):
        backend = ("egl" if sys.platform.startswith("linux") else "default") if backend == "auto" else backend
        options = {} if backend == "default" else {"backend": backend}
        if device is not None:
            if backend != "egl":
                raise ValueError("--device is an EGL device index")
            options["device_index"] = device
        self.ctx = gl.create_standalone_context(require=430, **options)
        self.info = {k: self.ctx.info[k] for k in ("GL_VENDOR","GL_RENDERER","GL_VERSION")}
        self.info.update(backend=backend, device_index=device, platform=platform.platform(),
                         python=platform.python_version(), moderngl=gl.__version__, numpy=np.__version__,
                         pillow=Image.__version__)
        driver = self.info["GL_RENDERER"].lower()
        self.info["software_renderer"] = any(x in driver for x in ("llvmpipe","softpipe","swiftshader","gdi generic","software rasterizer","microsoft basic render"))
        self.programs = {}
        self.vaos = {}
        for key, file, diag in (("scene","scene.frag",False), ("quality","effect.frag",True),
                                ("timed","effect.frag",False), ("ref","reference.frag",False),
                                ("display","display.frag",False)):
            p = self.ctx.program(vertex_shader=shader("fullscreen.vert"), fragment_shader=shader(file, diag))
            self.programs[key] = p
            self.vaos[key] = self.ctx.vertex_array(p, [])
            for unit, name in enumerate(("uPosition","uNormal","uSignal","uDetails")):
                if name in p:
                    p[name].value = unit
        self.targets = {}
        self.size = None

    def configure(self, case, seed):
        size = tuple(case["size"])
        if size != self.size:
            for fbo, textures in self.targets.values():
                fbo.release()
                for tex in textures:
                    tex.release()
            self.targets = {}
            for name, count, dtype in (("scene",2,"f4"),("quality",2,"f4"),("timed",1,"f4"),("display",1,"f1")):
                textures = [self.ctx.texture(size, 4, dtype=dtype) for _ in range(count)]
                for tex in textures:
                    tex.filter = (gl.NEAREST,gl.NEAREST)
                self.targets[name] = self.ctx.framebuffer(textures), textures
            self.size = size
        self.common = dict(uSize=size, uScene=case["scene"], uView=case["view"],
                           uParameter=case["parameter"], uSeed=seed)
        self.draw("scene", "scene")
        for index, tex in enumerate(self.targets["scene"][1]):
            tex.use(index)

    def prepare(self, program, target, **uniforms):
        self.targets[target][0].use()
        self.ctx.viewport = (0,0,*self.size)
        p = self.programs[program]
        for key, value in (self.common | uniforms).items():
            if key in p:
                p[key].value = value
        return self.vaos[program]

    def draw(self, program, target, **uniforms):
        self.prepare(program, target, **uniforms).render(vertices=3)

    def read(self, target, attachment=0):
        width, height = self.size
        data = self.targets[target][1][attachment].read(alignment=1)
        image = np.frombuffer(data,dtype=np.float32).reshape(height,width,4)[::-1].copy()
        if not np.isfinite(image).all():
            raise ValueError(f"Nonfinite float in {target} attachment {attachment}")
        return image

    def reference(self, spp, seed):
        if STUDY["kind"] == "water":
            self.draw("ref", "quality")
            return self.read("quality")[...,:3], self.read("quality",1), None
        # Each pass issues at most 32 geometry rays per pixel to bound shader duration.
        streams = []
        for stream_seed in (seed+101, seed+207):
            total = np.zeros(self.size[::-1], dtype=np.float64)
            for offset in range(0,spp,32):
                chunk = min(32,spp-offset)
                self.draw("ref","quality",uSeed=stream_seed,uOffset=offset,uTotal=spp,uChunk=chunk)
                total += self.read("quality")[...,0] * chunk
            streams.append((total/spp).astype("f4"))
        shifts = np.stack(streams)
        return shifts.mean(axis=0), self.read("quality",1), shifts

    def image(self, path, view, method=0, budget=8):
        for i, tex in enumerate(self.targets["quality"][1]):
            tex.use(i+2)
        self.draw("display","display",uDisplay=view,uMethod=method,uBudget=budget)
        img = Image.frombytes("RGBA",self.size,self.targets["display"][1][0].read(alignment=1))
        img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("RGB").save(path)

    def set_reference_signal(self, signal):
        # Restore the pooled AO reference for shaded and effect-only image export.
        rgb = np.repeat(signal[...,None],3,axis=2) if signal.ndim == 2 else signal
        rgba = np.ones((*rgb.shape[:2],4),np.float32)
        rgba[...,:3] = rgb
        self.targets["quality"][1][0].write(np.ascontiguousarray(rgba[::-1]).tobytes())

    def times(self, method, budget, warmup, count):
        vao = self.prepare("timed","timed",uMethod=method,uBudget=budget)
        for _ in range(warmup):
            vao.render(vertices=3)
        self.ctx.finish()
        queries = []
        for _ in range(count):
            q = self.ctx.query(time=True)
            with q:
                vao.render(vertices=3)
            queries.append(q)
        self.ctx.finish()
        samples = [int(q.elapsed) for q in queries]
        if any(t <= 0 or t == 0xffffffff for t in samples):
            raise RuntimeError("The driver returned an invalid GPU elapsed-time query")
        return samples
