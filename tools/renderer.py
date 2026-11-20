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


def finish(steps):
    """Drive the same rendering steps without a window and return their final value."""
    try:
        while True:
            next(steps)
    except StopIteration as done:
        return done.value


class Renderer:
    def __init__(self, backend, device, context=None):
        self.live = context is not None
        if self.live:
            self.ctx = context
            backend = "glfw"
        else:
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

    def release(self):
        for fbo, textures in self.targets.values():
            fbo.release()
            for texture in textures:
                texture.release()
        self.targets.clear()
        for vao in self.vaos.values():
            vao.release()
        for program in self.programs.values():
            program.release()
        if not self.live:
            self.ctx.release()

    def configure(self, case, seed):
        self.last_gpu_ns = 0
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
        if program != "scene":
            for unit, tex in enumerate(self.targets["scene"][1]):
                tex.use(unit)
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
        return finish(self.reference_steps(spp, seed))

    def reference_steps(self, spp, seed):
        if STUDY["kind"] == "water":
            self.draw("ref", "quality")
            result = self.read("quality")[..., :3], self.read("quality", 1), None
            if self.live:
                self.display("quality")
                yield ("Geometry reference", 1.0)
            return result
        streams = []
        for i, stream_seed in enumerate((seed + 101, seed + 207)):
            total = np.zeros(self.size[::-1], dtype=np.float64)
            for offset in range(0, spp, 32):
                chunk = min(32, spp - offset)
                self.draw("ref", "quality", uSeed=stream_seed, uOffset=offset, uTotal=spp, uChunk=chunk)
                total += self.read("quality")[..., 0] * chunk
                if self.live:
                    count = i * spp + offset + chunk
                    partial = total if i == 0 else streams[0].astype(np.float64) * spp + total
                    self.set_reference_signal((partial / count).astype("f4"))
                    self.display("quality")
                    yield (f"Reference rays {count} / {2 * spp}", count / (2 * spp))
            streams.append((total / spp).astype("f4"))
        shifts = np.stack(streams)
        return shifts.mean(axis=0), self.read("quality", 1), shifts

    def display(self, source, view=0, method=0, budget=8):
        self.targets[source][1][0].use(2)
        self.targets["quality"][1][1].use(3)
        self.draw("display", "display", uDisplay=view, uMethod=method, uBudget=budget)

    def image(self, path, view, method=0, budget=8):
        self.display("quality", view, method, budget)
        img = Image.frombytes("RGBA",self.size,self.targets["display"][1][0].read(alignment=1))
        img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("RGB").save(path)

    def set_reference_signal(self, signal):
        # Restore the pooled AO reference for shaded and effect-only image export.
        rgb = np.repeat(signal[...,None],3,axis=2) if signal.ndim == 2 else signal
        rgba = np.ones((*rgb.shape[:2],4),np.float32)
        rgba[...,:3] = rgb
        self.targets["quality"][1][0].write(np.ascontiguousarray(rgba[::-1]).tobytes())

    def times(self, method, budget, warmup, count):
        return finish(self.timing_steps(method, budget, warmup, count))

    def timing_steps(self, method, budget, warmup, count):
        # The window can present between batches. Only one effect draw is inside each query.
        batch = 4 if self.live else max(warmup, count, 1)
        queries = []
        for measured, size in ((False, warmup), (True, count)):
            for start in range(0, size, batch):
                stop = min(start + batch, size)
                vao = self.prepare("timed", "timed", uMethod=method, uBudget=budget)
                for _ in range(start, stop):
                    if measured:
                        q = self.ctx.query(time=True)
                        with q:
                            vao.render(vertices=3)
                        queries.append(q)
                    else:
                        vao.render(vertices=3)
                if self.live:
                    self.display("timed", method=method, budget=budget)
                    stage = "GPU samples" if measured else "Warm-up draws"
                    completed = (warmup if measured else 0) + stop
                    yield (f"{stage} {stop} / {size}", completed / (warmup + count))
            self.ctx.finish()
        samples = [int(query.elapsed) for query in queries]
        if any(t <= 0 or t == 0xffffffff for t in samples):
            raise RuntimeError("The driver returned an invalid GPU elapsed-time query")
        if self.live:
            self.last_gpu_ns = samples[-1]
            yield ("GPU samples complete", 1.0)
        return samples
