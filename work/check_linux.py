"""只读检查 Linux 运行条件，不启动桌宠或 Codex。"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from linux_support import diagnostics

def inspect(root=None):
    return diagnostics(root or Path(__file__).resolve().parents[1])

def main():
    report=inspect();print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ready_for_gui_test'] else 2

if __name__=='__main__':sys.exit(main())
