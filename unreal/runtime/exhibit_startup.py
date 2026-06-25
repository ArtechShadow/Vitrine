"""Vitrine UE 5.8 single startup entry (run via -ExecCmds="py exhibit_startup.py").

UE's -ExecCmds does NOT split multiple `py` commands on ';', so we chain the
stages from one script: (1) import_usd_stage.py spawns the UsdStageActor + mirrors
v2g:* (its main() is gated on __name__=="__main__", so we inject that), then
(2) build_exhibit.py sets up Lumen lighting + framing + screenshot.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else "/tmp/vitrine-proj"


def _run(script, as_main=False):
    path = os.path.join(_HERE, script)
    try:
        src = open(path).read()
    except Exception as e:
        try:
            import unreal; unreal.log_error(f"[startup] cannot read {path}: {e}")
        except Exception:
            print(f"[startup] cannot read {path}: {e}")
        return
    ns = {"__file__": path, "__name__": "__main__" if as_main else "exhibit_startup"}
    exec(compile(src, path, "exec"), ns)


# 1) USD import + v2g mirror (its main() runs only under __name__=="__main__")
_run("import_usd_stage.py", as_main=True)
# 2) lighting + look + screenshot (build_exhibit calls main() unguarded)
_run("build_exhibit.py", as_main=False)
