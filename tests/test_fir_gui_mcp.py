"""Real Tk main thread + stdio subprocess; no mocked GUI or MCP transport."""
import asyncio
import json
import queue
import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
import customtkinter as ctk
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'workshop'))
from fir_gui import FirApp
from fir_gui import cli_launcher
from verify_fir_mcp import verify


def close_test_window(app,root):
    # CTk schedules DPI/appearance callbacks; cancel this test root's timers
    # before constructing another Tk interpreter in the same test process.
    for timer in root.tk.call('after','info'):
        if timer!=app.poll_timer: root.tk.call('after','cancel',timer)
    app.close()


class LiveGuiTests(unittest.TestCase):
    def test_plot_fills_chart_at_two_window_sizes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ctk.CTk(); app = FirApp(root, folder)
            try:
                self.assertGreater(len(set(app.inputs['q_coefficients'])), 20)
                for geometry in ('1260x900', '1100x780'):
                    root.geometry(geometry)
                    for _ in range(8):
                        root.update(); time.sleep(.03)
                    app.draw_chart()
                    scale = app.chart._get_widget_scaling()
                    width, height = app.photo.cget('size')
                    self.assertAlmostEqual(width * scale, app.chart.winfo_width(), delta=2)
                    self.assertAlmostEqual(height * scale, app.chart.winfo_height(), delta=2)
            finally:
                close_test_window(app, root)

    def test_installed_cli_launchers_run_without_shell(self):
        import subprocess
        installed=[name for name in ('claude','codex') if shutil.which(name)]
        if not installed: self.skipTest('No supported CLI installed')
        for name in installed:
            result=subprocess.run(cli_launcher(name)+['mcp','add','--help'],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0)

    @unittest.skipUnless(shutil.which('claude'),'Claude CLI not installed')
    def test_connect_button_registers_and_replaces_only_local_claude_entry(self):
        # Actual installed CLI, isolated config directory; no user account config changed.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)/'day2'; work.mkdir()
            with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(Path(folder)/'claude-config')}):
                root=ctk.CTk(); root.withdraw(); app=FirApp(root,work)
                try:
                    for _ in range(2):
                        app.connect_mcp(); deadline=time.monotonic()+60
                        while app.registration_busy and time.monotonic()<deadline:
                            root.update(); time.sleep(.02)
                        self.assertFalse(app.registration_busy,'CLI registration timed out')
                        self.assertIn('등록 완료',app.connection.get())
                    config=json.loads((Path(folder)/'claude-config'/'.claude.json').read_text(encoding='utf-8'))
                    project=next(v for k,v in config['projects'].items() if Path(k).resolve()==work.resolve())
                    server=project['mcpServers']['fir-tuner']
                    self.assertIn('--runtime',server['args'])
                    self.assertIn('--mcp',server['args'])
                finally: close_test_window(app,root)

    def test_mcp_changes_live_gui_and_saves_real_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root=ctk.CTk(); root.withdraw(); app=FirApp(root,folder)
            runtime=app.prepare_bridge(); results=queue.Queue()
            def client():
                try:
                    asyncio.run(verify(sys.executable,[str(Path(__file__).resolve().parents[1]/'workshop'/'fir_mcp.py'),'--runtime',str(runtime)]))
                    results.put(None)
                except BaseException as error: results.put(error)
            thread=threading.Thread(target=client,daemon=True); thread.start()
            try:
                deadline=time.monotonic()+90
                while thread.is_alive() and time.monotonic()<deadline:
                    root.update(); time.sleep(.01)
                self.assertFalse(thread.is_alive(),'MCP/GUI integration timed out')
                error=results.get_nowait()
                if error: raise error
                self.assertTrue(app.connected)
                self.assertEqual(len(app.read_inputs()['q_coefficients']),63)
                self.assertEqual(app.layout_name.get(),'63개 + 중앙값 + 대칭 (127 taps)')
                self.assertEqual(app.entries['fft_size'].get(),'128')
                self.assertEqual(len(app.table.get_children()),4)
                self.assertTrue(any('save 완료' in message for message in app.events))
            finally: close_test_window(app,root)

if __name__=='__main__': unittest.main()
