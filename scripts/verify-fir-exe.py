"""Launch the real packaged GUI and control it via the packaged stdio adapter."""
import asyncio
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workshop'))
from verify_fir_mcp import verify
from fir_bridge import call_gui

if __name__=='__main__':
    executable=ROOT/'docs/downloads/fir-tuner.exe'
    with tempfile.TemporaryDirectory() as folder:
        process=subprocess.Popen([str(executable),'--workspace',folder,'--prepare'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            runtime=Path(folder)/'.fir-runtime/runtime.json'
            deadline=time.monotonic()+60
            while not runtime.exists() and time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[1].decode(errors='replace'))
                time.sleep(.1)
            if not runtime.exists(): raise RuntimeError('Packaged GUI failed to prepare the bridge')
            startup=call_gui(runtime,'state')['analysis']
            assert startup['fft_size']==2048, 'EXE did not start with tuning preset'
            assert len(set(startup['q_coefficients']))>20, 'EXE started with trivial coefficients'
            assert startup['tap_count']==127
            asyncio.run(verify(str(executable),['--mcp','--runtime',str(runtime)]))
            print('VALID: actual packaged GUI + actual packaged MCP adapter')
        finally:
            # Onefile bootloader owns a child process; terminate the whole test tree.
            # Terminating only the parent leaves the GUI holding stdout/stderr pipes.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            try: process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate()
