"""FIR reference automation. MCP calls the RUNNING GUI through a queued bridge."""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
import customtkinter as ctk

from fir_bridge import GuiBridge, call_gui
from fir_core import analyze, compact, reference, tuning_preset, response_image, save_response_image


def cli_launcher(client):
    executable=shutil.which(client)
    if not executable: raise ValueError(f'{client} CLI를 찾지 못했습니다. 설치 후 GUI를 다시 여세요.')
    # npm Windows wrappers cannot be launched directly via CreateProcess.
    # Run their known JS entrypoint with node, without interpolating shell text.
    if Path(executable).suffix.lower() in ('.cmd','.bat','.ps1'):
        if client=='claude':
            native=Path(executable).parent/'node_modules'/'@anthropic-ai'/'claude-code'/'bin'/'claude.exe'
            if native.is_file(): return [str(native)]
        package='@openai/codex/bin/codex.js' if client=='codex' else '@anthropic-ai/claude-code/cli.js'
        script=Path(executable).parent/'node_modules'/package
        node=shutil.which('node')
        if not script.is_file() or not node: raise ValueError('CLI 실행 파일을 찾지 못했습니다. 터미널 등록 예시를 사용하세요.')
        return [node,str(script)]
    return [executable]


LAYOUT_LABELS={'63개 + 중앙값 + 대칭 (127 taps)':'mirror63_center',
               '64개 + 대칭 (128 taps)':'mirror64','전체 계수 직접 입력':'direct'}


class CoefficientBox(ctk.CTkTextbox):
    """Multiline input with Entry-compatible read/write methods for shared UI code."""
    def get(self,*args): return super().get(*(args or ('1.0','end-1c')))
    def delete(self,first,last=None): return super().delete('1.0' if first==0 else first,last)
    def insert(self,index,text,*args): return super().insert('1.0' if index==0 else index,text,*args)


class FirApp(ctk.CTkFrame):
    def __init__(self,master,workspace=None):
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('dark-blue')
        super().__init__(master,fg_color='#121419',corner_radius=0)
        self.pack(fill='both',expand=True)
        self.master=master
        master.title('FIR Tuner · Q-format / FFT / MCP Connect')
        screen_w,screen_h=master.winfo_screenwidth(),master.winfo_screenheight()
        width,height=max(1040,min(1260,screen_w-80)),max(760,min(900,screen_h-110))
        master.geometry(f'{width}x{height}+{max(0,(screen_w-width)//2)}+{max(20,(screen_h-height)//2-25)}')
        master.minsize(1040,760)
        self.bridge=None; self.pending=queue.Queue(); self.events=[]; self.result=None
        self.connected=False; self.closed=False; self.registration_busy=False
        default=Path.home()/'Downloads'/'day2' if getattr(sys,'frozen',False) else Path.cwd()
        self.workspace=tk.StringVar(value=str(Path(workspace or default).resolve()))
        self.client=tk.StringVar(value='claude')
        self.server_mode=tk.StringVar(value='내장 데모')
        self.status=tk.StringVar(value='준비 완료 · 기본 Q30 FIR 분석')
        self.connection=tk.StringVar(value='MCP 대기 · 연결 준비 또는 MCP Connect를 누르세요')
        self.entries={}; self.inputs=None
        header=ctk.CTkFrame(self,fg_color='transparent'); header.pack(fill='x',padx=20,pady=(16,8))
        ctk.CTkLabel(header,text='FIR TUNER',font=('Segoe UI',26,'bold'),text_color='#ffdf00').pack(side='left')
        ctk.CTkLabel(header,text='Q 계수  →  대칭 구성  →  FFT  →  dB 응답',text_color='#9ca4b3').pack(side='left',padx=22)
        body=ctk.CTkFrame(self,fg_color='transparent'); body.pack(fill='both',expand=True,padx=20,pady=5)
        body.grid_columnconfigure(1,weight=1); body.grid_rowconfigure(0,weight=1)
        controls=ctk.CTkScrollableFrame(body,width=330,fg_color='#1c1f26',label_text='COEFFICIENTS / Q-FORMAT')
        controls.grid(row=0,column=0,sticky='nsew',padx=(0,14))
        right=ctk.CTkFrame(body,fg_color='#1c1f26'); right.grid(row=0,column=1,sticky='nsew')
        defaults=tuning_preset()
        ctk.CTkLabel(controls,text='FIR 정수 계수 · 쉼표 / 줄바꿈 구분',anchor='w').pack(fill='x',pady=(4,4))
        coefficients=CoefficientBox(controls,height=115,font=('Consolas',12),fg_color='#0d0f13')
        coefficients.insert('1.0',', '.join(map(str,defaults['q_coefficients'])))
        coefficients.pack(fill='x'); self.entries['q_coefficients']=coefficients
        ctk.CTkButton(controls,text='기본 튜닝 예제 불러오기',command=self.load_tuning_preset,fg_color='#343946').pack(fill='x',pady=(7,3))
        ctk.CTkButton(controls,text='63개 예제 불러오기 · 검증용',command=self.load_reference,fg_color='#343946').pack(fill='x',pady=(3,7))
        ctk.CTkLabel(controls,text='계수 배열 방식',anchor='w').pack(fill='x')
        self.layout_name=tk.StringVar(value=next(label for label,code in LAYOUT_LABELS.items() if code==defaults['coefficient_layout']))
        ctk.CTkOptionMenu(controls,variable=self.layout_name,values=list(LAYOUT_LABELS),fg_color='#343946').pack(fill='x',pady=(3,8))
        labels=[('center_q','중앙 정수 계수 (63개 대칭 방식)'),('word_bits','계수 폭 (32 / 64 bit)'),
                ('fractional_bits','소수부 비트 수'),('sample_rate_hz','샘플링 주파수 (Hz)'),
                ('fft_size','FFT 점 수 (128~8192, 2의 거듭제곱)'),('query_hz','조회 주파수 (Hz)')]
        for key,label in labels:
            ctk.CTkLabel(controls,text=label,anchor='w').pack(fill='x',pady=(3,0))
            entry=ctk.CTkEntry(controls,fg_color='#0d0f13'); value=defaults[key]
            entry.insert(0,', '.join(map(str,value)) if isinstance(value,list) else str(value))
            entry.pack(fill='x'); self.entries[key]=entry
        ctk.CTkButton(controls,text='FFT 분석 · 그래프 갱신',command=self.run_analysis,fg_color='#ffdf00',hover_color='#d5ba00',text_color='#111111').pack(fill='x',pady=(12,6))
        ctk.CTkButton(controls,text='PNG 이미지 저장',command=self.save_manual,fg_color='#343946').pack(fill='x',pady=(0,8))
        ctk.CTkLabel(controls,text='63 + 중앙 1 + 역순 63 = 127 taps\n128점 FFT에서는 0 한 개를 패딩\n계수 폭(bit) · tap 수 · FFT 점 수를 구분',justify='left',text_color='#9ca4b3').pack(anchor='w',pady=6)
        self.construction=tk.StringVar()
        ctk.CTkLabel(right,textvariable=self.construction,anchor='w',font=('맑은 고딕',13,'bold')).pack(fill='x',padx=14,pady=(12,6))
        self.chart=ctk.CTkLabel(right,text='',fg_color='#000000',corner_radius=8); self.chart.pack(fill='both',expand=True,padx=12,pady=4)
        self.chart_size=None
        self.chart.bind('<Configure>',lambda event:self.draw_chart())
        style=ttk.Style(master); style.theme_use('clam')
        style.configure('Fir.Treeview',background='#15171c',fieldbackground='#15171c',foreground='#e4e7ec',rowheight=24,borderwidth=0)
        style.configure('Fir.Treeview.Heading',background='#292d35',foreground='#e4e7ec',relief='flat')
        style.map('Fir.Treeview',background=[('selected','#535044')],foreground=[('selected','#ffdf00')])
        self.table=ttk.Treeview(right,columns=('hz','gain','db'),show='headings',height=4,style='Fir.Treeview')
        for key,label in [('hz','조회 주파수 (Hz)'),('gain','이득 (linear)'),('db','이득 (dB)')]: self.table.heading(key,text=label)
        self.table.pack(fill='x',padx=12,pady=(8,4))
        ctk.CTkLabel(right,textvariable=self.status,wraplength=650,justify='left',anchor='w',text_color='#9ca4b3').pack(fill='x',padx=12,pady=(0,8))
        connect=ctk.CTkFrame(self,fg_color='#1c1f26'); connect.pack(fill='x',padx=20,pady=(8,16))
        ctk.CTkLabel(connect,text='MCP CONNECT  /  Agent가 열린 프로그램을 제어합니다',anchor='w',text_color='#ffdf00').pack(fill='x',padx=12,pady=(8,3))
        row=ctk.CTkFrame(connect,fg_color='transparent'); row.pack(fill='x',padx=12,pady=3)
        ctk.CTkEntry(row,textvariable=self.workspace).pack(side='left',fill='x',expand=True)
        ctk.CTkButton(row,text='day2 폴더 선택',command=self.choose_workspace,width=120,fg_color='#343946').pack(side='left',padx=6)
        ctk.CTkOptionMenu(row,variable=self.client,values=['claude','codex'],width=90,fg_color='#343946').pack(side='left')
        ctk.CTkOptionMenu(row,variable=self.server_mode,values=['내장 데모','내가 만든 fir_server.py'],width=175,fg_color='#343946').pack(side='left',padx=6)
        self.connect_button=ctk.CTkButton(row,text='MCP Connect',command=self.connect_mcp,width=115,fg_color='#ffdf00',hover_color='#d5ba00',text_color='#111111'); self.connect_button.pack(side='left')
        ctk.CTkButton(row,text='연결 준비',command=self.prepare_only,width=90,fg_color='#343946').pack(side='left',padx=(6,0))
        ctk.CTkLabel(connect,textvariable=self.connection,anchor='w',wraplength=1120,text_color='#9ca4b3').pack(fill='x',padx=12,pady=3)
        self.log=ctk.CTkTextbox(connect,height=54,font=('Consolas',11),fg_color='#0d0f13',state='disabled')
        self.log.pack(fill='x',padx=12,pady=(0,10))
        self.run_analysis()
        self.poll_timer=master.after(30,self.poll)
        master.protocol('WM_DELETE_WINDOW',self.close)

    def choose_workspace(self):
        folder=filedialog.askdirectory(initialdir=self.workspace.get() if Path(self.workspace.get()).exists() else str(Path.home()))
        if folder: self.workspace.set(folder)

    def read_inputs(self):
        return dict(q_coefficients=[int(v) for v in re.split(r'[,;\s]+',self.entries['q_coefficients'].get().strip())],
            word_bits=int(self.entries['word_bits'].get()),fractional_bits=int(self.entries['fractional_bits'].get()),
            coefficient_layout=LAYOUT_LABELS[self.layout_name.get()],center_q=int(self.entries['center_q'].get()),
            fft_size=int(self.entries['fft_size'].get()),
            sample_rate_hz=int(self.entries['sample_rate_hz'].get()),
            query_hz=[float(v.strip()) for v in self.entries['query_hz'].get().split(',')])

    def set_inputs(self,inputs):
        for key,value in inputs.items():
            if key=='coefficient_layout':
                self.layout_name.set(next(label for label,code in LAYOUT_LABELS.items() if code==value)); continue
            self.entries[key].delete(0,'end')
            self.entries[key].insert(0,', '.join(map(str,value)) if isinstance(value,list) else str(value))

    def update_result(self,inputs,result):
        self.inputs=inputs | {key:result[key] for key in ('coefficient_layout','center_q')} | {'fft_size':result['fft']['size']}
        self.result=result
        self.set_inputs(self.inputs)
        self.chart_size=None; self.draw_chart()
        self.table.delete(*self.table.get_children())
        for row in result['frequencies']:
            db='−∞ (zero)' if row['gain_db'] is None else f"{row['gain_db']:.6f}"
            self.table.insert('','end',values=(f"{row['frequency_hz']:g}",f"{row['gain_linear']:.8f}",db))
        self.construction.set(f"입력 {result['input_count']}개 → FIR {result['tap_count']} taps → FFT {result['fft']['size']}점 (+0 패딩 {result['fft']['padding_count']}개)")
        self.status.set(f"분석 완료 · Fs {result['sample_rate_hz']} Hz · FFT 간격 {result['fft']['resolution_hz']:g} Hz · 조회는 H(f) 직접 계산")

    def draw_chart(self):
        if self.result is None or not hasattr(self,'chart'): return
        size=(self.chart.winfo_width(),self.chart.winfo_height())
        if min(size) < 200: return  # Wait for real geometry allocation.
        if self.chart_size==size: return
        self.chart_size=size
        image=response_image(self.result,*size)
        scale=self.chart._get_widget_scaling()
        logical_size=tuple(round(value/scale) for value in size)
        self.photo=ctk.CTkImage(light_image=image,dark_image=image,size=logical_size)
        self.chart.configure(image=self.photo)

    def load_reference(self):
        defaults=reference()
        self.set_inputs({k:defaults[k] for k in ('q_coefficients','word_bits','fractional_bits','sample_rate_hz','query_hz','coefficient_layout','center_q','fft_size')})
        self.run_analysis()

    def load_tuning_preset(self):
        self.set_inputs(tuning_preset())
        self.run_analysis()

    def run_analysis(self):
        try:
            inputs=self.read_inputs(); result=analyze(**inputs); self.update_result(inputs,result)
        except ValueError as error:
            self.result=None; self.inputs=None
            self.chart.configure(image=None); self.table.delete(*self.table.get_children())
            self.construction.set('입력 오류 · 분석 결과 없음')
            self.status.set(f'입력 오류: {error}')

    def require_result(self):
        if self.result is None: raise ValueError('유효한 FIR 분석 결과가 없습니다. FFT 분석을 먼저 실행하세요.')

    def output_folder(self):
        return Path(self.workspace.get()).resolve()/'workshop'/'reports'/'fir'

    def save_manual(self):
        try:
            self.require_result()
            saved=save_response_image(self.result,self.output_folder())
            self.status.set(f"PNG 저장: {saved['path']}")
        except (ValueError,OSError) as error: self.status.set(f'저장 오류: {error}')

    def record(self,message):
        self.events.append(message); self.events=self.events[-20:]
        self.log.configure(state='normal'); self.log.delete('1.0','end')
        self.log.insert('end','\n'.join(self.events[-3:])); self.log.configure(state='disabled')

    def dispatch(self,action,args):
        """HTTP worker queues work; only Tk's main thread updates this program."""
        done=threading.Event(); box={}
        self.pending.put((action,args,done,box))
        if not done.wait(12): raise ValueError('GUI did not respond. Keep the FIR window open.')
        if 'error' in box: raise ValueError(box['error'])
        return box['value']

    def execute(self,action,args):
        if action=='state': value={'analysis':compact(self.result) if self.result else None,'recent_calls':self.events[-5:]}
        elif action=='analyze':
            result=analyze(**args); self.update_result(args,result); value=compact(result)
        elif action=='query':
            self.require_result(); inputs=self.inputs | {'query_hz':args['query_hz']}
            result=analyze(**inputs); self.update_result(inputs,result); value={'frequencies':result['frequencies'],'sample_rate_hz':result['sample_rate_hz']}
        elif action=='save':
            self.require_result(); value=save_response_image(self.result,self.output_folder(),args.get('filename','fir-response.png'))
            self.status.set(f"MCP PNG 저장: {value['path']}")
        else: raise ValueError(f'Unknown GUI action: {action}')
        self.connected=True
        self.connection.set('실제 MCP/검증 요청 수신 · GUI 제어 확인 · 이 창을 유지하세요')
        self.record(f"{time.strftime('%H:%M:%S')} MCP → GUI: {action} 완료")
        return value

    def poll(self):
        if self.closed: return
        for _ in range(20):
            try: action,args,done,box=self.pending.get_nowait()
            except queue.Empty: break
            try:
                if action=='registration_result':
                    self.registration_busy=False; self.connect_button.configure(state='normal')
                    self.connection.set(args['message']); self.record(args['message']); box['value']={}
                else: box['value']=self.execute(action,args)
            except Exception as error:
                box['error']=str(error); self.record(f'MCP → GUI: {action} 오류: {error}')
            finally: done.set()
        self.poll_timer=self.master.after(30,self.poll)

    def prepare_bridge(self):
        workspace=Path(self.workspace.get()).resolve()
        if not workspace.is_dir(): raise ValueError('존재하는 day2 실습 폴더를 선택하세요.')
        runtime=workspace/'.fir-runtime'/'runtime.json'
        if self.bridge and self.bridge.path==runtime: return runtime
        if runtime.exists():
            try: call_gui(runtime,'state')
            except RuntimeError: pass
            else: raise ValueError('이 day2 폴더에 연결된 다른 FIR 창을 먼저 닫아주세요.')
        if self.bridge: self.bridge.stop()
        self.bridge=GuiBridge(runtime,self.dispatch); self.bridge.start()
        self.connection.set('GUI 연결 준비 완료 · Agent 등록/재시작 후 실제 Tool 호출을 기다립니다')
        return runtime

    def prepare_only(self):
        try: self.prepare_bridge()
        except Exception as error: self.connection.set(f'연결 준비 오류: {error}')

    def server_command(self,runtime):
        if self.server_mode.get()=='내가 만든 fir_server.py':
            workspace=Path(self.workspace.get()).resolve()
            python=workspace/'.venv'/'Scripts'/'python.exe'
            server=workspace/'workshop'/'fir_server.py'
            if not python.is_file() or not server.is_file(): raise ValueError('day2/.venv 및 workshop/fir_server.py를 먼저 준비하세요.')
            return [str(python),str(server),'--runtime',str(runtime)]
        if getattr(sys,'frozen',False): return [sys.executable,'--mcp','--runtime',str(runtime)]
        return [sys.executable,str(Path(__file__).resolve()),'--mcp','--runtime',str(runtime)]

    def connect_mcp(self):
        if self.registration_busy: return
        try:
            runtime=self.prepare_bridge(); client=self.client.get(); launcher=cli_launcher(client)
            command=launcher+(['mcp','add','--transport','stdio','--scope','local','fir-tuner','--'] if client=='claude' else ['mcp','add','fir-tuner','--'])+self.server_command(runtime)
            self.record('등록: '+subprocess.list2cmdline(command))
            self.connection.set('선택한 CLI에 fir-tuner 등록 중…')
            self.registration_busy=True; self.connect_button.configure(state='disabled')
        except Exception as error:
            self.connection.set(f'MCP Connect 오류: {error}'); return
        cwd=self.workspace.get()
        def register():
            try:
                if client=='claude':
                    # Only replace the local educational name in the chosen day2.
                    subprocess.run(launcher+['mcp','remove','--scope','local','fir-tuner'],cwd=cwd,
                        capture_output=True,timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                message='등록 완료 · 같은 day2에서 Agent를 재시작하고 Tool을 호출하세요' if result.returncode==0 else f"등록 실패: {(result.stderr or result.stdout).strip()[:450]}"
            except Exception as error: message=f'등록 오류: {error}'
            self.pending.put(('registration_result',{'message':message},threading.Event(),{}))
        threading.Thread(target=register,daemon=True).start()

    def close(self):
        self.closed=True
        self.master.after_cancel(self.poll_timer)
        if self.bridge: self.bridge.stop()
        self.master.destroy()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mcp',action='store_true'); parser.add_argument('--runtime'); parser.add_argument('--workspace')
    parser.add_argument('--prepare',action='store_true',help='Prepare the local GUI bridge without registering any CLI')
    args=parser.parse_args()
    if args.mcp:
        if not args.runtime: parser.error('--runtime is required with --mcp')
        from fir_mcp import create_server
        create_server(args.runtime).run(transport='stdio')
    else:
        ctk.set_appearance_mode('dark')
        root=ctk.CTk(); app=FirApp(root,args.workspace)
        if args.prepare: app.prepare_bridge()
        root.mainloop()

if __name__=='__main__': main()
