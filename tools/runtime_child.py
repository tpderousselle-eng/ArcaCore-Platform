"""Trusted bootstrap used to hold generated imports behind containment setup."""

from pathlib import Path
import sys
import time


def main():
    if len(sys.argv)!=3 or not sys.argv[2].isdigit(): return 2
    ready=Path(sys.argv[1]).resolve(); workspace=Path.cwd().resolve()
    if ready.parent!=workspace or ready.name!=".arcacore-runtime-ready": return 2
    port=int(sys.argv[2])
    if not 1<=port<=65535: return 2
    deadline=time.monotonic()+30
    while not ready.is_file():
        if time.monotonic()>=deadline: return 3
        time.sleep(.01)
    import uvicorn
    uvicorn.run("app.main:app",host="127.0.0.1",port=port,log_level="warning")
    return 0


if __name__=="__main__": raise SystemExit(main())
