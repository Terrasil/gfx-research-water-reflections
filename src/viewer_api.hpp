#pragma once

// Wire format shared with tools/viewer.py. The calling thread owns the GLFW context.
enum class StudyCommand : int { start, advance, stop, resume };
enum class StudyState : int { failed = -1, running, complete, stopped };
struct BenchmarkFrame {
    int number, count, scene, view, method, budget, width, height;
    double parameter, fraction, gpuMilliseconds;
    unsigned int framebuffer;
    char stage[192];
    char detail[768];
};
using StudyCallback = StudyState (*)(StudyCommand, const char*, const char*, BenchmarkFrame*);
#if defined(_WIN32)
#define STUDY_EXPORT __declspec(dllexport)
#else
#define STUDY_EXPORT __attribute__((visibility("default")))
#endif
extern "C" STUDY_EXPORT int gfx_run_viewer(StudyCallback callback, const char* profile,
                                            const char* output, const char* capture, int resume);
