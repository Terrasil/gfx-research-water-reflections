"""Host the native GLFW viewer and drive the study on its current GL context."""
import argparse
import ctypes as c
from pathlib import Path
import sys
import traceback

from study import StudyStopped, run_steps


class Frame(c.Structure):
    _fields_ = [(name, c.c_int) for name in
                ("number", "count", "scene", "view", "method", "budget", "width", "height")] + [
        ("parameter", c.c_double), ("fraction", c.c_double), ("gpu_ms", c.c_double), ("framebuffer", c.c_uint),
        ("stage", c.c_char * 192), ("detail", c.c_char * 768)]


Callback = c.CFUNCTYPE(c.c_int, c.c_int, c.c_char_p, c.c_char_p, c.POINTER(Frame))
START, NEXT, STOP, RESUME = range(4)
FAILED, RUNNING, COMPLETE, STOPPED = -1, 0, 1, 2


class Session:
    def __init__(self):
        self.context = None
        self.steps = None

    def __call__(self, command, profile, output, result):
        frame = result.contents
        try:
            if command in (START, RESUME):
                import moderngl
                if self.context is None:
                    # GLFW has already made the window's native context current on this thread.
                    self.context = moderngl.get_context()
                if self.context.version_code < 430:
                    raise RuntimeError("The benchmark requires desktop OpenGL 4.3 or later")
                path = Path(output.decode("utf-8"))
                args = argparse.Namespace(out=path, resume=command == RESUME,
                         profile=profile.decode("ascii"), backend="auto", device=None,
                         expect_renderer=None, hardware_note="")
                self.steps = run_steps(args, self.context)
            if command == STOP:
                if self.steps is not None:
                    self.steps.throw(StudyStopped("Stopped by user"))
                return STOPPED
            phase, number, count, case, work, framebuffer, gpu_ns = next(self.steps)
            frame.number, frame.count = number, count
            frame.scene, frame.view = case["scene"], case["view"]
            frame.method, frame.budget = work.method, work.budget
            frame.width, frame.height = case["size"]
            frame.parameter = case["parameter"]
            frame.fraction = (number - 1 + work.fraction) / count
            frame.gpu_ms = gpu_ns / 1e6
            frame.framebuffer = framebuffer
            frame.stage = f"{phase.capitalize()}  |  {work.stage}".encode("utf-8")
            frame.detail = case["id"].encode("utf-8")[:767]
            return RUNNING
        except StopIteration:
            self.steps = None
            return COMPLETE
        except StudyStopped:
            self.steps = None
            return STOPPED
        except Exception as error:
            self.steps = None
            frame.detail = str(error).encode("utf-8", errors="replace")[:767]
            traceback.print_exc()
            return FAILED


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--profile", choices=("smoke","quick","paper"), default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--capture", default="")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    viewer = c.CDLL(str(args.library.resolve()))
    viewer.gfx_run_viewer.argtypes = [Callback, c.c_char_p, c.c_char_p, c.c_char_p, c.c_int]
    viewer.gfx_run_viewer.restype = c.c_int
    return viewer.gfx_run_viewer(Callback(Session()), args.profile.encode(), args.out.encode(),
                                 args.capture.encode(), args.resume)


if __name__ == "__main__":
    sys.exit(main())
