#include "catalog.hpp"
#include <gfx/research/application.hpp>
#include <gfx/research/fullscreen_triangle.hpp>
#include <gfx/research/screenshot.hpp>
#include <gfx/research/shader.hpp>
#include <glad/gl.h>
#include <imgui.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <process.h>
#else
#include <spawn.h>
extern char** environ;
#endif

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
bool launch(const std::vector<std::string>& args) {
#ifdef _WIN32
    // Windows passes one command line to Python. Quote arguments containing spaces.
    std::vector<std::string> quoted(args);
    std::vector<const char*> argv;
    for(auto& arg:quoted) {
        if(arg.find_first_of(" \t")!=std::string::npos) arg='"'+arg+'"';
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    return _spawnv(_P_NOWAIT,args.front().c_str(),argv.data())!=-1;
#else
    std::vector<char*> native;
    for (const auto& a:args) native.push_back(const_cast<char*>(a.c_str()));
    native.push_back(nullptr);
    pid_t pid{};
    return posix_spawn(&pid,native[0],nullptr,nullptr,native.data(),environ)==0;
#endif
}
class Viewer final: public gfx::research::Application {
    Shader sceneShader,effectShader,refShader,displayShader;
    gfx::research::FullscreenTriangle tri;
    Target gbuffer,output;
    int width=0,height=0,scene=0,view=0,method=study::candidate,budgetIndex=1,parameterIndex=1,display=0;
    bool reference=false,save=false,visible=true;
    fs::path captureDir;
    std::string status;
public:
    explicit Viewer(fs::path capture): Application({.title=study::title,.width=1280,.height=720,.vsync=true,
            .debug_context=false,.docking=false}),captureDir(std::move(capture)) {}
private:
    bool on_init() override {
        load(sceneShader,"scene.frag"); load(effectShader,"effect.frag",true);
        load(refShader,"reference.frag"); load(displayShader,"display.frag");
        ImGui::GetIO().IniFilename=nullptr;
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
    void on_frame(const gfx::research::FrameInfo& f) override {
        if(width!=f.width || height!=f.height) {
            width=f.width; height=f.height;
            gbuffer.allocate(width,height); output.allocate(width,height);
        }
        glDisable(GL_DEPTH_TEST); glDisable(GL_BLEND); glDisable(GL_SCISSOR_TEST);
        glDisable(GL_FRAMEBUFFER_SRGB);
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
            status=file.string(); save=false;
            if(oneShot) close();
        }
    }
    void on_gui(const gfx::research::FrameInfo&) override {
        if(ImGui::IsKeyPressed(ImGuiKey_F1,false)) visible=!visible;
        if(ImGui::IsKeyPressed(ImGuiKey_F9,false)) save=true;
        if(!visible) return;
        ImGui::SetNextWindowPos({16,16},ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowSize({420,258},ImGuiCond_FirstUseEver);
        if(ImGui::Begin(study::title)) {
            ImGui::Text("%d x %d  |  %.0f FPS",width,height,fps());
            if(ImGui::BeginTabBar("study-tabs")) {
                if(ImGui::BeginTabItem("Experiment")) {
                    if(ImGui::BeginTable("methods",2,ImGuiTableFlags_SizingStretchProp)) {
                        ImGui::TableSetupColumn("Labels",ImGuiTableColumnFlags_WidthFixed,117);
                        ImGui::TableSetupColumn("Values");
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
                if(ImGui::BeginTabItem("Capture")) {
                    if(ImGui::Button("Save clean PNG (F9)")) save=true;
                    ImGui::TextWrapped("Start a suite to close this preview and give the measurement process the GPU.");
                    if(ImGui::Button("Run smoke test")) startSuite("smoke");
                    if(ImGui::Button("Run publication suite")) startSuite("paper");
                    if(!status.empty()) ImGui::TextWrapped("%s",status.c_str());
                    ImGui::EndTabItem();
                }
                ImGui::EndTabBar();
            }
        }
        ImGui::End();
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
    void startSuite(const char* profile) {
        const auto root=fs::path(study::root);
        const auto stamp=std::chrono::system_clock::now().time_since_epoch().count();
        const auto dest=(root/"runs"/(std::string(profile)+"-"+std::to_string(stamp))).string();
        if(launch({study::python,(root/"tools/study.py").string(),"run","--profile",profile,"--out",dest})) close();
        else status="Could not launch the configured Python interpreter.";
    }
    void on_shutdown() override { gbuffer.clear(); output.clear(); }
};
}
int main(int argc,char** argv) {
    try {
        if(argc==1) return Viewer({}).run();
        if(argc==3 && std::string(argv[1])=="--capture") return Viewer(argv[2]).run();
        std::cerr<<"Usage: "<<study::id<<" [--capture DIRECTORY]\n"; return 2;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
