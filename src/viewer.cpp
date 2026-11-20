#include "catalog.hpp"
#include "viewer_api.hpp"
#include <gfx/research/application.hpp>
#include <gfx/research/fullscreen_triangle.hpp>
#include <gfx/research/screenshot.hpp>
#include <gfx/research/shader.hpp>
#include <glad/gl.h>
#include <imgui.h>
#include <GLFW/glfw3.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
namespace fs = std::filesystem;
using gfx::research::Shader;
using gfx::research::ShaderSource;
using gfx::research::ShaderStage;
namespace {
std::string source(const fs::path& path, bool diagnostics = false) {
    std::ifstream file(path);
    if (!file) throw std::runtime_error("Cannot open shader: " + path.string());
    std::ostringstream out;
    for (std::string line; std::getline(file,line);) {
        if (line.starts_with("#include \"")) {
            const auto start = line.find('"')+1;
            const auto end = line.find('"',start);
            out << source(path.parent_path() / line.substr(start,end-start));
        } else {
            out << line << '\n';
            if (diagnostics && line.starts_with("#version")) out << "#define DIAGNOSTICS 1\n";
        }
    }
    return out.str();
}
void load(Shader& shader, const char* name, bool diagnostics=false) {
    const auto dir = fs::path(study::root)/"shaders";
    std::array stages{ShaderSource{ShaderStage::Vertex,source(dir/"fullscreen.vert")},
                      ShaderSource{ShaderStage::Fragment,source(dir/name,diagnostics)}};
    if (!shader.load(stages)) throw std::runtime_error(shader.last_error());
}
struct Target {
    GLuint fbo=0;
    std::array<GLuint,2> texture{};
    void clear() {
        glDeleteFramebuffers(1,&fbo);
        glDeleteTextures(2,texture.data());
        fbo=0; texture={};
    }
    void allocate(int w,int h) {
        clear();
        glGenFramebuffers(1,&fbo);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glGenTextures(2,texture.data());
        std::array<GLenum,2> attachments{GL_COLOR_ATTACHMENT0,GL_COLOR_ATTACHMENT1};
        for (int i=0;i<2;++i) {
            glBindTexture(GL_TEXTURE_2D,texture[i]);
            glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA32F,w,h);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
            glFramebufferTexture2D(GL_FRAMEBUFFER,attachments[i],GL_TEXTURE_2D,texture[i],0);
        }
        glDrawBuffers(2,attachments.data());
        if (glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)
            throw std::runtime_error("Cannot allocate floating-point render targets");
        glBindFramebuffer(GL_FRAMEBUFFER,0);
    }
};
std::string utf8(const fs::path& path) {
    auto bytes = path.u8string();
    return {bytes.begin(), bytes.end()};
}
fs::path pathFromUtf8(const char* value) {
    const std::string_view utf8Value(value);
    return fs::path(std::u8string(utf8Value.begin(),utf8Value.end()));
}

class Viewer final: public gfx::research::Application {
    Shader sceneShader,effectShader,refShader,displayShader;
    gfx::research::FullscreenTriangle tri;
    Target gbuffer,output;
    int width=0,height=0,scene=0,view=0,method=study::candidate,budgetIndex=1,parameterIndex=1,display=0;
    bool reference=false,save=false,visible=true;
    fs::path captureDir, runDir;
    std::string status;
    StudyCallback step;
    BenchmarkFrame frame{};
    std::string profile, gpuName;
    bool active=false, firstStep=false, resume=false, canResume=false;
    bool automatic=false, selectTests=false, fullscreen=false;
    int exitCode=0, winX=0, winY=0, winW=0, winH=0;

public:
    Viewer(StudyCallback callback, const char* initialProfile, fs::path out, fs::path capture, bool retry):
        Application({.title=study::title,.width=1280,.height=720,.vsync=true,
                     .debug_context=false,.docking=false}), captureDir(std::move(capture)), step(callback) {
        if (*initialProfile) {
            automatic=true;
            startSuite(initialProfile, std::move(out), retry);
        }
    }
    int outcome() const { return exitCode; }

private:
    static void configureGui() {
        auto& style=ImGui::GetStyle();
        style.WindowPadding={9,8}; style.FramePadding={5,3}; style.ItemSpacing={7,4};
        style.WindowRounding=2; style.FrameRounding=1; style.GrabRounding=1;
        style.WindowBorderSize=1; style.FrameBorderSize=0; style.ScrollbarSize=11;
        style.Colors[ImGuiCol_WindowBg]={0.035f,0.043f,0.055f,0.97f};
        style.Colors[ImGuiCol_TitleBg]={0.09f,0.16f,0.25f,1};
        style.Colors[ImGuiCol_TitleBgActive]={0.16f,0.28f,0.43f,1};
        style.Colors[ImGuiCol_FrameBg]={0.10f,0.16f,0.24f,1};
        style.Colors[ImGuiCol_FrameBgHovered]={0.16f,0.26f,0.38f,1};
        style.Colors[ImGuiCol_FrameBgActive]={0.20f,0.33f,0.49f,1};
        style.Colors[ImGuiCol_SliderGrab]={0.24f,0.53f,0.85f,1};
        style.Colors[ImGuiCol_CheckMark]={0.40f,0.72f,1,1};
        style.Colors[ImGuiCol_Header]={0.12f,0.23f,0.36f,1};
        style.Colors[ImGuiCol_HeaderHovered]={0.20f,0.36f,0.54f,1};
    }
    bool on_init() override {
        load(sceneShader,"scene.frag"); load(effectShader,"effect.frag",true);
        load(refShader,"reference.frag"); load(displayShader,"display.frag");
        ImGui::GetIO().IniFilename=nullptr;
        gpuName=reinterpret_cast<const char*>(glGetString(GL_RENDERER));
        configureGui();
        return true;
    }
    void pass(Shader& s, GLuint target) {
        glBindFramebuffer(GL_FRAMEBUFFER,target);
        glViewport(0,0,width,height);
        s.bind();
        glUniform2i(glGetUniformLocation(s.id(),"uSize"),width,height);
        s.set_int("uScene",scene); s.set_int("uView",view); s.set_int("uMethod",method);
        s.set_int("uDisplay",reference && display==2?1:display); s.set_int("uBudget",study::budgets[budgetIndex]);
        s.set_int("uSeed",17); s.set_float("uParameter",float(study::parameters[parameterIndex]));
        s.set_int("uPosition",0); s.set_int("uNormal",1);
        s.set_int("uSignal",2); s.set_int("uDetails",3);
        s.set_int("uOffset",0); s.set_int("uTotal",32); s.set_int("uChunk",32);
        tri.draw();
    }
    void startSuite(std::string name, fs::path out={}, bool retry=false) {
        profile=std::move(name);
        if (out.empty()) {
            const auto stamp=std::chrono::system_clock::now().time_since_epoch().count();
            out=fs::path(study::root)/"results"/"publication"/(profile+"-"+std::to_string(stamp));
        }
        runDir=fs::absolute(out);
        active=true; firstStep=true; resume=retry; canResume=false; selectTests=true; save=false;
        status.clear(); frame={};
    }

    void advance(StudyCommand command) {
        auto result=step(command,profile.c_str(),utf8(runDir).c_str(),&frame);
        if (result==StudyState::running) return;
        active=false; frame.framebuffer=0;
        if (result==StudyState::complete) {
            status="Benchmark complete. Report saved to "+utf8(runDir/"report");
        } else if (result==StudyState::stopped) {
            status="Benchmark stopped. Completed cases are in "+utf8(runDir);
            canResume=fs::is_regular_file(runDir/"manifest.json");
            if (automatic) exitCode=130;
        } else {
            status=std::string("Benchmark failed. ")+frame.detail;
            if (automatic) exitCode=1;
            std::cerr<<status<<'\n';
        }
        if (automatic) close();
    }

    void present(const gfx::research::FrameInfo& f) {
        glBindFramebuffer(GL_FRAMEBUFFER,0);
        glDrawBuffer(GL_BACK);
        glViewport(0,0,f.width,f.height);
        glClearColor(0.028f,0.034f,0.043f,1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        const double scale=std::min(double(f.width)/frame.width,double(f.height)/frame.height);
        const int w=std::max(1,int(frame.width*scale+0.5)), h=std::max(1,int(frame.height*scale+0.5));
        const int x=(f.width-w)/2, y=(f.height-h)/2;
        glBlitNamedFramebuffer(frame.framebuffer,0,0,0,frame.width,frame.height,
                               x,y,x+w,y+h,GL_COLOR_BUFFER_BIT,GL_LINEAR);
    }

    void on_frame(const gfx::research::FrameInfo& f) override {
        glDisable(GL_DEPTH_TEST); glDisable(GL_BLEND); glDisable(GL_SCISSOR_TEST);
        glDisable(GL_FRAMEBUFFER_SRGB);
        if(active) {
            const auto command=firstStep ? (resume ? StudyCommand::resume : StudyCommand::start) : StudyCommand::advance;
            firstStep=false;
            advance(command);
            if (active) { present(f); return; }
        }
        if(width!=f.width || height!=f.height) {
            width=f.width; height=f.height;
            gbuffer.allocate(width,height); output.allocate(width,height);
        }
        for(int i=0;i<4;++i) glBindTextureUnit(i,0);
        pass(sceneShader,gbuffer.fbo);
        for(int i=0;i<2;++i) glBindTextureUnit(i,gbuffer.texture[i]);
        pass(reference?refShader:effectShader,output.fbo);
        for(int i=0;i<2;++i) glBindTextureUnit(i+2,output.texture[i]);
        pass(displayShader,0);
        if(save || !captureDir.empty()) {
            const bool oneShot=!captureDir.empty();
            const auto dir=oneShot?captureDir:fs::path("captures");
            const auto stamp=std::chrono::system_clock::now().time_since_epoch().count();
            const auto file=dir/(std::string(study::sceneIds[scene])+"-"+study::viewLabels[view]+"-"+
                (reference?"reference":study::methodIds[method])+"-b"+std::to_string(study::budgets[budgetIndex])+
                "-p"+std::to_string(study::parameters[parameterIndex])+"-v"+std::to_string(reference && display==2?1:display)+"-"+std::to_string(stamp)+".png");
            glReadBuffer(GL_BACK);
            if(!gfx::research::save_framebuffer_png(file,width,height)) throw std::runtime_error("Screenshot write failed");
            status=utf8(file); save=false;
            if(oneShot) close();
        }
    }
    void shortcuts() {
        const auto& io=ImGui::GetIO();
        if(io.WantTextInput) return;
        if(ImGui::IsKeyPressed(ImGuiKey_F1,false) || (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_H,false)))
            visible=!visible;
        if(!active && ImGui::IsKeyPressed(ImGuiKey_F9,false)) save=true;
        if(io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_F,false)) {
            if(fullscreen) {
                glfwSetWindowMonitor(window(),nullptr,winX,winY,winW,winH,0);
                fullscreen=false;
            } else if(auto* monitor=glfwGetPrimaryMonitor()) {
                if(const auto* mode=glfwGetVideoMode(monitor)) {
                    glfwGetWindowPos(window(),&winX,&winY); glfwGetWindowSize(window(),&winW,&winH);
                    glfwSetWindowMonitor(window(),monitor,0,0,mode->width,mode->height,mode->refreshRate);
                    fullscreen=true;
                }
            }
        }
    }
    void testButtons() {
        if(ImGui::Button("Run smoke test")) startSuite("smoke");
        ImGui::SameLine();
        if(ImGui::Button("Run quick test")) startSuite("quick");
        if(ImGui::Button("Run publication suite",{-1,0})) startSuite("paper");
        if(canResume && ImGui::Button("Resume benchmark",{-1,0})) startSuite(profile,runDir,true);
    }
    void on_gui(const gfx::research::FrameInfo& f) override {
        shortcuts();
        if(!visible) return;
        const auto* vp=ImGui::GetMainViewport();
        ImGui::SetNextWindowPos({vp->WorkPos.x+12,vp->WorkPos.y+12},ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowSize({448,0},ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowSizeConstraints({std::min(448.0f,std::max(260.0f,vp->WorkSize.x-24)),0},{680,std::max(180.0f,vp->WorkSize.y-24)});
        if(!ImGui::Begin(study::title,nullptr,ImGuiWindowFlags_AlwaysAutoResize)) {ImGui::End();return;}
        if(table("status")) {
            field("GPU",[&]{ImGui::TextWrapped("%s",gpuName.c_str());});
            field("Frame rate",[&]{ImGui::Text("%.0f FPS (%.2f ms)",fps(),cpu_frame_milliseconds());});
            field("Render target",[&]{ImGui::Text("%d x %d",active?frame.width:f.width,active?frame.height:f.height);});
            if(active) field("Last GPU sample",[&]{
                if(frame.gpuMilliseconds>0.0) ImGui::Text("%.3f ms",frame.gpuMilliseconds);
                else ImGui::TextDisabled("Pending");
            });
            ImGui::EndTable();
        }
        if(active && frame.count) {
            ImGui::SeparatorText("Benchmark running");
            ImGui::Text("Case %d / %d",frame.number,frame.count); ImGui::SameLine();
            ImGui::TextDisabled("%s",profile.c_str());
            ImGui::TextWrapped("%s",frame.detail);
            if(table("case")) {
                field("Scene",[&]{ ImGui::TextUnformatted(study::sceneLabels[frame.scene]); });
                field("Camera",[&]{ ImGui::TextUnformatted(study::viewLabels[frame.view]); });
                field("Method",[&]{ ImGui::TextWrapped("%s",frame.method<0?"Geometry reference":study::methodLabels[frame.method]); });
                field(study::parameter,[&]{ ImGui::Text("%.3g",frame.parameter); });
                field("Budget",[&]{
                    if(frame.budget>0) ImGui::Text("%d",frame.budget);
                    else ImGui::TextDisabled("Reference");
                });
                ImGui::EndTable();
            }
            ImGui::TextWrapped("%s",frame.stage);
            ImGui::ProgressBar(float(frame.fraction),{-1,0});
            if(ImGui::Button("Stop benchmark",{-1,0})) advance(StudyCommand::stop);
        }
        if(!status.empty()) ImGui::TextWrapped("%s",status.c_str());
        if(!runDir.empty() && ImGui::SmallButton("Copy output path")) ImGui::SetClipboardText(utf8(runDir).c_str());
        ImGui::BeginDisabled(active);
        if(ImGui::BeginTabBar("study-tabs")) {
            if(ImGui::BeginTabItem("Experiment")) {
                if(table("methods")) {
                    field("Method",[&]{ ImGui::Combo("##method",&method,study::methodLabels,int(std::size(study::methodLabels))); });
                    const char* budgets[]={budgetText(0),budgetText(1)};
                    field("Budget",[&]{ ImGui::Combo("##budget",&budgetIndex,budgets,2); });
                    std::string p0=parameterLabel(0),p1=parameterLabel(1);
                    const char* values[]={p0.c_str(),p1.c_str()};
                    field(study::parameter,[&]{ ImGui::Combo("##parameter",&parameterIndex,values,2); });
                    ImGui::EndTable();
                }
                ImGui::Checkbox("Geometry reference",&reference);
                ImGui::EndTabItem();
            }
            if(ImGui::BeginTabItem("Scene")) {
                ImGui::Combo("Scene",&scene,study::sceneLabels,int(std::size(study::sceneLabels)));
                ImGui::Combo("Camera",&view,study::viewLabels,int(std::size(study::viewLabels)));
                const char* modes[]={"Shaded scene","Effect only","Traversal work"};
                ImGui::Combo("View",&display,modes,reference?2:3);
                if(reference && display==2) display=1;
                ImGui::EndTabItem();
            }
            if(ImGui::BeginTabItem("Tests",nullptr,selectTests?ImGuiTabItemFlags_SetSelected:0)) {
                testButtons(); ImGui::EndTabItem();
            }
            selectTests=false;
            if(ImGui::BeginTabItem("Capture")) {
                if(ImGui::Button("Save clean PNG (F9)")) save=true;
                testButtons(); ImGui::EndTabItem();
            }
            ImGui::EndTabBar();
        }
        ImGui::EndDisabled();
        ImGui::End();
    }
    static bool table(const char* id) {
        if(!ImGui::BeginTable(id,2,ImGuiTableFlags_SizingStretchProp)) return false;
        ImGui::TableSetupColumn("Parameter",ImGuiTableColumnFlags_WidthFixed,158);
        ImGui::TableSetupColumn("Value");
        return true;
    }
    template<class Control> static void field(const char* label, Control&& control) {
        ImGui::TableNextRow(); ImGui::TableNextColumn();
        ImGui::AlignTextToFramePadding(); ImGui::TextUnformatted(label);
        ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1);
        control();
    }
    static const char* budgetText(int index) {
        static const std::array<std::string,2> labels{std::to_string(study::budgets[0]),std::to_string(study::budgets[1])};
        return labels[index].c_str();
    }
    static std::string parameterLabel(int index) {
        std::ostringstream s; s<<study::parameters[index]; return s.str();
    }
    void on_shutdown() override {
        if(active) advance(StudyCommand::stop);
        gbuffer.clear(); output.clear();
    }
};
}
extern "C" STUDY_EXPORT int gfx_run_viewer(StudyCallback callback,const char* profile,const char* output,
                                            const char* capture,int resume) {
    try {
        Viewer viewer(callback,profile,pathFromUtf8(output),pathFromUtf8(capture),resume!=0);
        const int code=viewer.run();
        return code==0?viewer.outcome():code;
    } catch(const std::exception& e) {
        std::cerr<<e.what()<<'\n';
        return 1;
    }
}
