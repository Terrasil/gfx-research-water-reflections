#include "catalog.hpp"
#include "publication.hpp"
#include <filesystem>
#include <iostream>
#include <vector>
namespace fs=std::filesystem;

namespace {
int usage(std::ostream& out,int code) {
    out << "Usage: " << study::id << " [--capture DIRECTORY]\n"
        << "       " << study::id << " --publication-{smoke,quick,suite} [--publication-output=DIRECTORY] [--publication-resume]\n"
        << "       " << study::id << " --study {plan,run,analyze} [arguments]\n";
    return code;
}

int dispatch(const std::vector<fs::path>& args) {
    std::vector<fs::path> viewer{fs::path(STUDY_VIEWER_PATH)};
    if(args.empty()) return publication::runScript("viewer.py",viewer);
    if(args.size()==1 && args[0]=="--help") return usage(std::cout,0);
    if(args[0]=="--study")
        return publication::runScript("study.py",{args.begin()+1,args.end()});
    if(args.size()==2 && args[0]=="--capture" && !args[1].empty()) {
        viewer.insert(viewer.end(),{"--capture",args[1]});
        return publication::runScript("viewer.py",viewer);
    }
    if(args[0]=="--publication-smoke") viewer.insert(viewer.end(),{"--profile","smoke"});
    else if(args[0]=="--publication-quick") viewer.insert(viewer.end(),{"--profile","quick"});
    else if(args[0]=="--publication-suite") viewer.insert(viewer.end(),{"--profile","paper"});
    else return usage(std::cerr,2);
    const auto prefix=fs::path("--publication-output=").native();
    fs::path output;
    bool resume=false;
    for(std::size_t i=1;i<args.size();++i) {
        if(args[i]=="--publication-output" && i+1<args.size() && output.empty() && !args[i+1].empty())
            output=args[++i];
        else if(args[i].native().starts_with(prefix) && args[i].native().size()>prefix.size() && output.empty())
            output=args[i].native().substr(prefix.size());
        else if(args[i]=="--publication-resume" && !resume) resume=true;
        else return usage(std::cerr,2);
    }
    if(resume && output.empty()) return usage(std::cerr,2);
    if(!output.empty()) viewer.insert(viewer.end(),{"--out",output});
    if(resume) viewer.emplace_back("--resume");
    return publication::runScript("viewer.py",viewer);
}
}

#ifdef _WIN32
int wmain(int argc,wchar_t** argv) {
#else
int main(int argc,char** argv) {
#endif
    try {
        return dispatch({argv+1,argv+argc});
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
