# misoyeon_11_server17.py
import json
import os.path
import random
import sys
import threading
import tkinter as tk
import winsound

from dataclasses import dataclass
from datetime import datetime
from socket import *
from time import sleep
from tkinter import messagebox as tkmbox
from tkinter import ttk, scrolledtext

@dataclass
class SoundConfig:
    sound: int
    sound_height: int  
    sound_length: int  

def time_tag():
    return datetime.now().strftime("%H:%M")

# =========================================================
#                  Chat Server (OOP)
# =========================================================
class ChatServer: # xprint 사용
    def __init__(self, print_callback, disconnected_callback):
        self.print_callback = print_callback
        self.set_controls = disconnected_callback
        self.BUFSIZE = 1024
        self.server_sock = None
        self.client_sock = None
        self.running = False # 서버 thread marker 

        self.broadcast_running = False # broadcasting thread marker
        self.broadcast_sock = None
        self.broadcast_thread = None

        self.sound_config: SoundConfig | None = None 

        self.server_ip = self.seek_server_ip()     # 자동 server ip 찾기
        self.server_port = self.seek_server_port() # 자동 server port 찾기
        if self.server_ip == None or self.server_port == None:
            tkmbox.showerror(
                "서버 초기화 실패",
                "네트워크 상태를 확인한후 다시 실행하세요."
                )
            self.win.destroy()
            sys.exit(1)

        #self.broadcasting()

    def server_addr_to_GUI(self): # GUI로 addr 보내줌.
        return self.server_ip, self.server_port

    # ==========================
    #    자동으로 ip/port 찾기
    # ==========================
    def seek_server_ip(self):
        print('* ChatServerGUI: seek_server_ip')

        xinterval = 0.5 #초
        max_count = 5
        count = 0
        while True:
            try:
                s = socket(AF_INET, SOCK_DGRAM)
                s.connect(("8.8.8.8",80))
                ip = s.getsockname()[0]
                print(f'Seeked IP: {ip}')
                return ip 

            except Exception:
                count += 1
                if count >= max_count:
                    return None
                sleep(xinterval)
            finally:
                if s:
                    s.close()
        return None
    
    def seek_server_port(self):
        print('* ChatServerGUI: seek_server_port')

        start_port = random.randint(9015, 50000)
        scan_range = 20

        for port in range(start_port, start_port+scan_range):
            try:
                s = socket(AF_INET, SOCK_STREAM)
                s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                s.bind(('', port))
                print(f'Seeked Port: {port}')
                return port 

            except OSError:
                continue
            finally:
                if s:
                    s.close()
        return None 

    def xprint(self, msg):
        self.print_callback(msg)

    ### 알림음 설정 연결 ###
    def set_config(self, config: SoundConfig):
        self.sound_config = config 

        self.sound        = config.sound 
        self.sound_height = config.sound_height
        self.sound_length = config.sound_length       
        
    ### 알림음 선택 출력 ###
    def exe_alarm(self, xsound=1, _height=500, _length=500):
        if xsound == 1:
            threading.Thread(
                target=winsound.Beep, 
                args=(_height, _length), 
                daemon=True
            ).start()
        elif xsound == 2:
            threading.Thread(
                target=winsound.MessageBeep, 
                args=(winsound.MB_ICONHAND,), 
                daemon=True
            ).start()
        else:
            print(f'* 알림음 선택 에러: {xsound=}, {type(xsound)=}')
            return 

    ### 서버 정지 ###
    def _close_all_sockets(self):
        print('* ChatServer: _close_all_sockets\n')        

        self.running = False

        # 리스닝 소켓 종료 #
        if self.server_sock:
            self.server_sock.close()
            self.server_sock = None

        # 클라이언트 소켓 종료 #
        if self.client_sock: # None일때를 체크. 즉, 중복 종료를 발생시키지 않는다.
            try:
                self.client_sock.shutdown(SHUT_RDWR)
            except:
                pass
            self.client_sock.close()
            self.client_sock=None 

        # 브로드캐스트 소켓 종료
        self.broadcast_running = False

    # =====================================================
    #    클라이언트의  ip/port(서버) 요청을 수신 -> 보내줌.
    # =====================================================
    def broadcasting(self):
        print('* ChatServerGUI: broadcasting')     

        if self.broadcast_running: # 중복실행 방지.
            return

        self.broadcast_running = True   
        self.broadcast_thread = threading.Thread(target=self.broadcast_addr, daemon=True)
        self.broadcast_thread.start()

    def broadcast_addr(self):
        print('* ChatServerGUI: broadcast_addr')        

        BROADCAST_PORT = 50100 # 클라이언트와 사전 약속된 포트를 사용해야 함.

        sock = None
        try:
            sock = socket(AF_INET, SOCK_DGRAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            sock.settimeout(1.0) # block 방지.
            sock.bind(('', BROADCAST_PORT))

            self.broadcast_sock = sock
            print("Discovery server listening...")

            while self.broadcast_running:
                try:
                    data, addr = sock.recvfrom(1024)

                    if data == b'DISCOVER_SERVER':
                        reply = f'IP={self.server_ip};PORT={self.server_port}'
                        print(f'{reply}')
                        sock.sendto(reply.encode(), addr)

                except timeout: # running 체크용
                    continue
                except OSError: # sock 닫힘.
                    break
                except Exception as e:
                    print(f'* broadcast 예외: {e}')
                    break
        finally:
            self.broadcast_running = False # cleanup

            if sock:
                try:
                    sock.close()
                except:
                    pass
            self.broadcast_sock = None

    # =====================================================
    #    Server start
    # =====================================================
    def start_server(self, ip, port):
        print('* ChatServer: start_server')     

        self.running = False # 실제 서버 오픈후 True ( in _setup_server_socket)
        self.thread = threading.Thread(
            target=self._run_server, args=(ip, port), daemon=True
        )
        self.thread.start()

        self.broadcast_running = False
        self.broadcasting()

    ### 서버 스레드 ###
    def _run_server(self, ip, port):
        print('* ChatServer: _run_server')   

        try:
            if not self._setup_server_socket(ip, port):
                return
            self._accept_loop()

        finally:
            self._shutdown_server()   

    def _setup_server_socket(self, ip, port):
        print('* ChatServer: _setup_server_socket')     

        try:
            self.server_sock = socket(AF_INET, SOCK_STREAM)
            self.server_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            self.server_sock.settimeout(1.0)

            self.server_sock.bind((ip, port))
            self.server_sock.listen(1)
            
            self.xprint(f'* 서버 오픈! 클라이언트가 접속할수 있습니다. ({time_tag()})\n\n') # 리스닝 중.
            self.running = True
            return True

        except Exception as e:
            self.xprint(f'\n! 서버 소켓 생성 실패: {e}\n')
            self.server_sock = None
            return False

    def _accept_loop(self):
        print('* ChatServer: _accept_loop')     

        while self.running and self.server_sock:
            try:                    
                client, remote = self.server_sock.accept()
                print(f'* 접속 수락 from {remote}')
                self._on_client_connected(client, remote) # _recv_loop 포함.

            except timeout:
                continue
            except OSError as e:
                # 서버 소켓이 닫혔을 때 
                print(f'* 서버 소켓 종료: {e}')
                break

            except Exception as e:
                print(f'* accept에서 진짜 예외: {e}')
                break # 서버 정상종료? or other 비정상 종료

    def _on_client_connected(self, client, remote):
        print('* ChatServer: _on_client_connected')     

        self.client_sock = client
        self.client_sock.settimeout(1.0)

        stamp = time_tag()
        self.xprint(f'* 클라이언트가 연결됨: {remote} ({stamp})\n\n')
        self.set_controls(True)

        # 연결 알림음 
        self.exe_alarm(self.sound, self.sound_height, self.sound_length) # 기본음,  800Hz, 500ms
        self._recv_loop()

        self._cleanup_client()
        self.set_controls(False)

    def _cleanup_client(self):
        print('* ChatServer: _cleanup_client')     

        if self.client_sock:
            try:
                self.client_sock.close()
            except Exception:
                pass
        self.client_sock = None

    def _shutdown_server(self):
        print('* ChatServer: _shutdown_server')     

        self._close_all_sockets()
        self.set_controls(False)

        self.xprint(f'! 서버 종료됨 ({time_tag()})\n\n')

    ### 수신 루프 ###
    def _recv_loop(self):
        print('* ChatServer: _recv_loop in 1st')      
        try:
            while self.running and self.client_sock:
                try:
                    data = self.client_sock.recv(self.BUFSIZE)

                    if not data: # 클라이언트 정상 종료 (FIN)
                        print('* 클라이언트 정상 종료 *')
                        self._on_client_disconnected()
                        break

                    if data == b'\x00': # keepalive
                        continue
                    self._handle_message(data)

                except timeout:
                    # 타임아웃은 정상 동작 (running 체크용)
                    continue
                except ConnectionResetError:
                    print('* 클라이언트 강제 종료 *') # 프로세스 kill등 
                    self._on_client_disconnected()
                    break
                except OSError as e:
                    # 소켓 레벨 오류 (닫힌 소켓 등)
                    print(f'* 소켓 오류: {e}')
                    #self._on_client_disconnected()
                    break

                except Exception as e: # 진짜 예외!
                    print(f'* 예외 발생: {e}')
                    break
        finally:
            pass

    def _handle_message(self, data):
        print('* ChatServer: _handle_message')     

        try:
            payload = json.loads(data.decode(errors='ignore'))
        except json.JSONDecodeError:
            print('* 잘못된 JSON 수신')
            self.xprint('[!] 잘못된 데이터가 수신되었습니다.')
            return

        sender = payload.get('sender', '?')
        msg = payload.get('message','')
        time = payload.get('time', time_tag())

        self.xprint(f'{sender} {msg} ({time})\n\n')
        self.exe_alarm(self.sound, self.sound_height, self.sound_length) # 기본음,  800Hz, 500ms               

    def _on_client_disconnected(self):
        stamp = time_tag()
        self.xprint(f'* 클라이언트에서 연결을 종료하였습니다. ({stamp})\n\n')


    ### 서버 → 클라이언트 송신 ###
    def _send(self, text):
        print('* ChatServer: _send') 

        if self.client_sock:
            try:
                self.client_sock.send(text.encode())
                return True
            except:
                return False
        return False

# =========================================================
#                  GUI Class
# =========================================================
class ChatServerGUI: # xPrint사용
    CONFIG_FILE =  "./misoyeon_11_server_config.json"
    ### GUI 출력

    def __init__(self):

        self.server = ChatServer(self.xPrint, self.set_controls)

        self.server_ip = None
        self.server_port = None
        self.imsi_label = '준비중' # self.idLabel의 임시값 저장소.

        self.gui_x = 1413 # GUI 위치
        self.gui_y =  660 # GUI 위치 

        self.sound = 1 # 알림음
        self.sound_height = 800 # 알림음 높이. (단위: Hz)
        self.sound_length = 500 # 알림음 길이. (단위: 밀리초)
        self.sound_height_min =  400
        self.sound_height_max =  900
        self.sound_length_min =  300
        self.sound_length_max = 1000

        self.MENU_W = 500
        self.MENU_H = 340
        self.MOVE_END_DELAY = 200 # ms : GUI 이전 위치 기억에 필요.
        self._move_job = None #  GUI 이전 위치 기억에 필요.

        self.win = tk.Tk()
        self.win.title(f"미소연 Server - {os.path.basename(__file__)}{' '*18}by JYHn")

        # 최초 실행했을때의 위치(정중앙)
        screen_width  = self.win.winfo_screenwidth()  # 1920 
        screen_height = self.win.winfo_screenheight() # 1080
        gui_x  = int(screen_width/2) - int(self.MENU_W/2)
        gui_y = int(screen_height/2) - int(self.MENU_H/2)
        #print(f'{gui_x=}, {gui_y=}') # 1980x1080에서는 (710,370)

        self.default_config = {
            "idLabel": "●진료실●",
            "x": gui_x, # 화면중앙, # 우하단 -> 1413,
            "y": gui_y, # 화면중앙, # 우하단 ->  660,
            "sound": 1, # 기본음(삑)
            "sound_height": 800, # Hz
            "sound_length": 500  # ms
        }

        x_geometry = f'{self.MENU_W}x{self.MENU_H}+{self.gui_x}+{self.gui_y}'
        self.win.geometry(x_geometry)
        self.win.resizable(False, False)

        self.win.bind("<Configure>", self.on_configure) # GUI 위치 저장 위해서.

        ### 메시지 히스토리 ###
        self.history = []
        self.history_index = 0

        ### GUI 작성 ###
        self.load_notebook_style()
        self.nbook = ttk.Notebook(self.win, width=480, height=320)
        self.nbook.pack(fill='both', expand=True)
        self._build_tabs()
        self._build_chatting_tab()
        self._build_setting_tab()
        self._build_inform_tab()

        ### Server addr 받아옴.
        self.server_ip, self.server_port = self.server.server_addr_to_GUI() 

        ### GUI에 data setting, 이전 GUI 위치에 출현.
        self.win.withdraw() ######### GUI 안보이기.
        self.load_process()
        self.display_load_data()
        self.win.deiconify() ######## GUI 보이기.

        self.apply_sound_config_to_server() # 알림음 설정 변수를 class ChatServer로 보냄.
        
        self.win.mainloop()


    # =====================================================
    #    GUI의 이전 위치를 저장/ 활용하기 위한 함수들.
    # =====================================================
    def on_configure(self, event):
        # 이전에 예약된 이동 종료 판정이 있으면 취소.
        job = getattr(self.win, "_move_job", None)
        if job is not None:
            self.win.after_cancel(job)

        # 새로 이동 종료 판정 예약.
        self.win._move_job = self.win.after(self.MOVE_END_DELAY, self.on_move_end)

    def on_move_end(self):
        self.win._move_job = None
        self.gui_x,self.gui_y = self.win.winfo_x(), self.win.winfo_y()        
        #print(f'이동 종료: {self.gui_x=}, {self.gui_y=}')
        self.save_config(silent=True)
    # =====================================================

    def xPrint(self, text):
        def _append():
            self.txt['state'] = 'normal'
            self.txt.insert('end', text)
            self.txt.see('end')
            self.txt['state'] = 'disabled'
        self.txt.after(0, _append)

    def load_notebook_style(self):
        print('* ChatServerGUI: load_notebook_style')        

        style = ttk.Style()

        # 테마 확인 (선택)
        print(f'{style.theme_use("default")=}') # default:classic, vista:modern

        # Notebook 기본 스타일
        style.configure(
            "TNotebook.Tab",
            padding=[15, 5],
            #font=("맑은 고딕", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", "#ffffff"), 
                ("!selected", "#cccccc")
            ],
            foreground=[
                ("selected", "black"),
                ("!selected", "#555555")
            ],            
            font=[
                ("selected", ("맑은 고딕", 12, "bold")),
                ("!selected", ("맑은 고딕", 10,))
            ]
        )
       
    # ================================
    #           GUI 구성
    # ================================
    def _build_tabs(self):
        print('* ChatServerGUI: _build_tabs')       

        # 2 Tabs.
        self.tab_chatting = tk.Frame(self.nbook)
        self.tab_chatting.pack()
        self.tab_setting = tk.Frame(self.nbook)
        self.tab_setting.pack()
        self.tab_inform = tk.Frame(self.nbook)
        self.tab_inform.pack()

        self.nbook.add(self.tab_chatting, text='Chatting ◖ Server ◗')
        self.nbook.add(self.tab_setting,  text='Setting')
        self.nbook.add(self.tab_inform,  text='Inform')

        # Chatting Tab.
        self.fr_addr = tk.Frame(self.tab_chatting)
        self.fr_addr.pack(side='top', fill='x', padx=10, pady=5)
        self.fr_text = tk.Frame(self.tab_chatting)
        self.fr_text.pack(side='top', fill='both')
        self.fr_control = tk.Frame(self.tab_chatting)
        self.fr_control.pack(side='top', fill='x', padx=10, pady=5)

        # Setting Tab.
        self.fr_label = tk.LabelFrame(self.tab_setting, text=' Label 설정 ', relief='solid', bd=1)
        self.fr_label.pack(side='top', fill='x', padx=10, pady=5)
        self.fr_alarm_sound = tk.LabelFrame(self.tab_setting, text=' 알림음 설정 ', relief='solid', borderwidth=1)
        self.fr_alarm_sound.pack(side='top', fill='x', padx=10, pady=5)
        self.fr_set_save = tk.Frame(self.tab_setting)
        self.fr_set_save.pack(side='top', fill='x', padx=10, pady=5)

        # Inform Tab.
        self.fr_inform = tk.Frame(self.tab_inform, relief='solid', bd=1)
        self.fr_inform.pack(side='top', fill='x', padx=10, pady=5)

    # --------------------------------
    #    Chatting Tab
    # --------------------------------
    def _build_chatting_tab(self):
        print('* ChatServerGUI: _build_chatting_tab')       

        # Addr Area
        self.ip = tk.StringVar(value=self.server_ip)
        ttk.Label(self.fr_addr, text='IP').pack(side='left')
        self.entry_ip = ttk.Entry(self.fr_addr, state='readonly', textvariable=self.ip, width=12)
        self.entry_ip.pack(side='left', padx=10)

        self.port = tk.StringVar(value=str(self.server_port))
        ttk.Label(self.fr_addr, text='Port').pack(side='left')
        self.entry_port = ttk.Entry(self.fr_addr, state='readonly',textvariable=self.port, width=8)
        self.entry_port.pack(side='left', padx=10)

        self.btn_start = ttk.Button(self.fr_addr, text='Start', command=self.onStart)
        self.btn_start.pack(side='left', expand=True, fill='both')

        # ScrolledText Area
        self.txt = scrolledtext.ScrolledText(self.fr_text, height=17)
        self.txt.pack(fill='both', padx=15)
        self.txt.insert('end', '* 서버 먼저 실행 후 클라이언트 실행해 주세요 *\n\n')
        self.txt['state'] = 'disabled'

        # Control Area
        self.label_idLabel = tk.Label(self.fr_control,)
        self.label_idLabel.pack(side='left')
        self.msg = tk.StringVar()
        self.entry_msg = ttk.Entry(self.fr_control, font=('맑은고딕',12), textvariable=self.msg)
        self.entry_msg.pack(side='left', expand=True, fill='both', padx=2)

        # Enter 키 → 전송
        self.entry_msg.bind("<Return>", lambda e: self.onSend())

        # 메시지 히스토리 ↑↓
        self.entry_msg.bind("<Up>", self.onHistoryUp)
        self.entry_msg.bind("<Down>", self.onHistoryDown)

        self.btn_send = ttk.Button(self.fr_control, text='Send', width=10, command=self.onSend)
        self.btn_send.pack(side='left', padx=5)

        # 처음에는 비활성화
        self.set_controls(False)

    # --------------------------------
    #    Setting Tab
    # --------------------------------
    def _build_setting_tab(self):
        print('* ChatServerGUI: _build_setting_tab')       

        tk.Label(self.fr_label, text='Label (3자 이상) :').pack(side='left')
        self.idLabel = tk.StringVar(value=self.imsi_label)
        self.entry_idLabel = ttk.Entry(self.fr_label, textvariable=self.idLabel, font=('맑은고딕',12), width=14)
        self.entry_idLabel.pack(side='left', padx=10)

        # 알람음 설정 Frame
        # row=0
        self.alarm_sound = tk.IntVar(value=1)
        tk.Radiobutton(
            self.fr_alarm_sound, text='단순한 기본음 ->',
            variable=self.alarm_sound, value=1
        ).grid(row=0, column=0, sticky='w', padx=(5, 0))

        # 음 높이
        tk.Label(self.fr_alarm_sound, text='음 높이(Hz)') \
            .grid(row=0, column=1, sticky='w', padx=(0, 5))

        self.cbox_sound_height = ttk.Combobox(
            self.fr_alarm_sound, width=5, state='readonly',
            values=[num for num in range(400, 1000, 100)]
        )
        self.cbox_sound_height.grid(row=0, column=2, sticky='w')
        self.cbox_sound_height.set(self.sound_height)

        # 음 길이
        tk.Label(self.fr_alarm_sound, text='음 길이(초)') \
            .grid(row=0, column=3, sticky='e', padx=(10, 5))

        self.cbox_sound_length = ttk.Combobox(self.fr_alarm_sound, width=5, state='readonly')
        self.cbox_sound_length['values'] = [ num/1000 for num in range(300, 1100, 100) ]
        self.cbox_sound_length.grid(row=0, column=4, sticky='w', padx=(0, 15))
        self.cbox_sound_length.set(self.sound_length/1000)

        self.btn_test = ttk.Button(self.fr_alarm_sound, width=8, text='Sound\n  Test', command=self.test_sound)
        self.btn_test.grid(row=0, column=5, rowspan=2, pady=(0,8)) 

        # row=1
        tk.Radiobutton(
            self.fr_alarm_sound, text='윈도우 기본음 ->',
            variable=self.alarm_sound, value=2
        ).grid(row=1, column=0, sticky='w', padx=(5, 0))
        self.alarm_sound.set(self.sound)
        tk.Label(self.fr_alarm_sound, text='(음 높이와 길이 조절이 안됨)') \
            .grid(row=1, column=1, columnspan=4, sticky='w', padx=(0, 5))

        self.btn_set_save = ttk.Button(self.fr_set_save, text='Save', command=self.save_config)
        self.btn_set_save.pack()

    # --------------------------------
    #    Inform Tab
    # --------------------------------
    def _build_inform_tab(self):
        print('* ChatServerGUI: _build_inform_tab')       

        message = \
        '''
        이 프로그램은 1:1 전용 채팅 프로그램입니다.
        2개의 파일(서버, 클라이언트)로 구성되어 있고
        내부 네트워크에서만 작동하고, 
        통신은 1:1만 가능하기에 보안에는 크게 신경쓰지 않았습니다.
        [사용법]
        서버 프로그램을 먼저 실행시켜서 [Start]를 클릭하고
        이후에 클라이언트를 실행시켜서 [Connect]를 클릭해 서버에 접속하면 됩니다.
        feedback: jyhoonnc@naver.com

        * 프로그램 사용중 발생하는 모든 책임은 사용자에게 있습니다 *
        '''
        tk.Label(self.fr_inform, text=message).pack(side='left')

    def test_sound(self):
        xsound = self.alarm_sound.get() 
        if xsound == 1: # 단순음
            _height = int(self.cbox_sound_height.get())
            _length = int(float(self.cbox_sound_length.get())*1000)
            self.server.exe_alarm(xsound, _height, _length)
        
        elif xsound ==2: # 윈도우 기본음
            self.server.exe_alarm(xsound)

    # =============================================
    #    config.json 읽기/쓰기/검증
    # =============================================
    def load_process(self):
        print('* ChatServerGUI: load_process')        

        need_default = (
            not self.load_saved_file() 
            or not self.validate_data()
        )

        if need_default:
            self.save_default()
            self.saved = self.default_config.copy()
            msg = (
                '설정파일이 없거나 수정되었습니다.\n'
                '기본값으로 다시 저장합니다.\n'
                '프로그램은 정상 실행됩니다.'
            )
            tkmbox.showerror('설정파일 에러', msg)            

        self.load_data()

    def load_data(self):
        print('* ChatServerGUI: load_data')        

        self.imsi_label = self.saved["idLabel"][:10].strip()
        # self.idLabel 값은 display_load_data()에서 imsi_label로 설정됨.
        self.gui_x = self.saved["x"]
        self.gui_y = self.saved["y"]

        self.sound = self.saved["sound"]
        self.sound_height = self.saved["sound_height"]
        self.sound_length = self.saved["sound_length"]
        print(f'{self.imsi_label=}, {type(self.imsi_label)=}')
        print(f'{self.gui_x=}, {type(self.gui_x)=}')
        print(f'{self.gui_y=}, {type(self.gui_y)=}')
        print(f'{self.sound=}, {type(self.sound)=}')
        print(f'{self.sound_height=}, {type(self.sound_height)=}')
        print(f'{self.sound_length=}, {type(self.sound_length)=}')

    def display_load_data(self):
        print('* ChatServerGUI: display_load_data')        

        self.ip.set(self.server_ip)
        self.port.set(self.server_port)

        self.label_idLabel['text'] = self.imsi_label
        self.idLabel.set(self.imsi_label)

        # load data에 의해서 직전 마지막 위치로 GUI 보여줌.
        x_geometry = f'{self.MENU_W}x{self.MENU_H}+{self.gui_x}+{self.gui_y}'
        self.win.geometry(x_geometry)

        self.alarm_sound.set(self.sound)
        self.cbox_sound_height.set(self.sound_height)
        self.cbox_sound_length.set(self.sound_length/1000)

    def save_default(self):
        print('* ChatServerGUI: save_default')        

        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.default_config, f, indent=4, ensure_ascii=False)
            return True
        except:
            return False

    def load_saved_file(self):
        print('* ChatServerGUI: load_saved_file')

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                self.saved = json.load(f)
                return True
        except Exception as e:
            print(f"설정파일 오류: {e}")
            return False 

    def validate_data(self):
        print('* ChatServerGUI: validate_data')        

        errors = []

        # idLabel: str 타입, 최소 3자 이상
        id_label = str(self.saved.get("idLabel",''))[:10].strip()
        if not isinstance(id_label, str) or len(id_label) < 3:
            errors.append("idLabel은 최소 3자 이상의 문자열이어야 합니다.")
        #print(f'{id_label=}')

        screen_width = self.win.winfo_screenwidth() - self.MENU_W  # 1920 - 메뉴넓이
        screen_height = self.win.winfo_screenheight() -self.MENU_H # 1080 - 메뉴높이
        # x: 스크린 x 좌표 (0 ~ screen_width - 메뉴넓이)
        x = self.saved.get("x")
        if not isinstance(x, int) or not (0 <= x <= screen_width):
            errors.append(f"x는 0 이상 {screen_width} 이하의 정수여야 합니다.")
        print(f'{x=}')

        # y: 스크린 y 좌표 (0 ~ screen_height - 메뉴높이)
        y = self.saved.get("y")
        if not isinstance(y, int) or not (0 <= y <= screen_height):
            errors.append(f"y는 0 이상 {screen_height} 이하의 정수여야 합니다.")
        print(f'{y=}')


        # sound: 1 또는 2
        sound = self.saved.get("sound")
        if sound not in (1, 2):
            errors.append("sound는 1 또는 2만 허용됩니다.")
        print(f'{sound=}')


        # sound_height: 400~900, 100 단위
        sound_height = self.saved.get("sound_height")
        if (
            not isinstance(sound_height, int)
            or sound_height < self.sound_height_min # 400
            or sound_height > self.sound_height_max # 900
            or sound_height % 100 != 0
        ):
            errors.append(f"sound_height는 {self.sound_height_min}~{self.sound_height_max}\
             사이의 값이며 100 단위여야 합니다.")
        print(f'{sound_height=}')


        # sound_length: 300~1000, 100 단위
        sound_length = self.saved.get("sound_length")
        if (
            not isinstance(sound_length, int)
            or sound_length < self.sound_length_min # 300
            or sound_length > self.sound_length_max # 1000
            or sound_length % 100 != 0
        ):
            errors.append(f"sound_length는 {self.sound_length_min}~{self.sound_length_max}\
             사이의 값이며 100 단위여야 합니다.")
        print(f'{sound_length=}')

        # 결과
        if errors:
            print(f'{errors=}')
            return False
        else:
            return True

    ### 설정 저장 ### 
    def save_config(self, *, silent=False):
        print('* ChatServerGUI: save_config')     

        idLabel = self.entry_idLabel.get()[:10].strip()
        if len(idLabel) < 3:
            if not silent:
                tkmbox.showerror("Label 에러", "Label은 3자 이상되어야 합니다.")
            self.imsi_label = self.saved['idLabel']
            self.label_idLabel['text'] = self.saved['idLabel']
        else:   
            self.imsi_label = idLabel
            self.label_idLabel['text'] = idLabel

        self.idLabel.set(self.imsi_label)

        isound = self.alarm_sound.get()
        self.sound_height = int(self.cbox_sound_height.get())
        self.sound_length = int(float(self.cbox_sound_length.get())*1000)

        config_values = {
            "idLabel": self.imsi_label,
            "x": self.gui_x,
            "y": self.gui_y,
            "sound": isound,
            "sound_height": self.sound_height,
            "sound_length": self.sound_length
        }

        self.apply_sound_config_to_server()

        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_values, f, indent=4, ensure_ascii=False)
        except Exception:
            tkmbox.showerror('* 설정파일 에러로 변경사항이 저장되지 않았습니다!')

    # -------------------------------------
    #    알림음을 class ChatServer에 연결: save_config()때마다 실행해야됨.
    # -------------------------------------
    def apply_sound_config_to_server(self):
        print('* ChatServerGUI: apply_sound_config_to_server')        

        config = SoundConfig(
            sound = self.alarm_sound.get(),
            sound_height = int(self.cbox_sound_height.get()),
            sound_length = int(float(self.cbox_sound_length.get())*1000)
            )
        self.server.set_config(config)

    ### 입력 컨트롤 활성/비활성
    def set_controls(self, enable):
        print('* ChatServerGUI: set_controls\n')              

        if enable:
            self.entry_msg['state'] = 'normal'
            self.entry_msg.focus_set()
            self.btn_send['state'] =  'normal'
        else:
            self.entry_msg['state'] = 'disabled'
            self.btn_send['state'] =  'disabled'

    # ==============================
    #    버튼:  서버 Start / Stop 
    # ==============================
    def onStart(self):
        print('* ChatServerGUI: onStart')            

        if self.btn_start['text'] == "Start":
            ### Start
            self.btn_start['text'] = "Stop"
            print(f'{self.port.get()=}, {type(self.port.get())=}')
            self.server.start_server(self.ip.get(), int(self.port.get()))
        else:
            ### Stop
            self.btn_start['text'] = "Start"

            self.server._close_all_sockets()
        
        self.set_controls(False)


    # ================================
    #    메세지 전송
    # ================================
    def onSend(self):
        print('* ChatServerGUI: onSend')        

        itext = self.msg.get().strip()
        if not itext:
            return

        ## 메시지 히스토리 관리 
        if itext in self.history: # 중복되는것 제거.
            self.history.remove(itext)
        self.history.append(itext)
        self.history_index = len(self.history)

        payload = {
            "type": "chat",
            "sender": self.idLabel.get().strip(),
            "message": itext,
            "time": time_tag()
        }

        try: 
            json_text = json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            self.xPrint(f'* 메시지 직렬화 실패: {e}\n\n')
            return

        if self.server._send(json_text):
            self.xPrint(f"{payload['sender']} {payload['message']} ({payload['time']})\n\n")
            self.msg.set('')
            self.entry_msg.focus_set()
        else:
            self.xPrint(f"! 전송 실패. 연결상태를 확인하세요! ({time_tag()})\n\n")

    # ================================
    #   메시지 히스토리 기능 (Up / Down)
    # ================================
    def onHistoryUp(self, event):
        if not self.history:
            return

        if self.history_index > 0:
            self.history_index -= 1

        self.msg.set(self.history[self.history_index])
        self.entry_msg.icursor("end")

    def onHistoryDown(self, event):
        if not self.history:
            return

        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.msg.set(self.history[self.history_index])
        else:
            self.history_index = len(self.history)
            self.msg.set("")

        self.entry_msg.icursor("end")

# =====================================================
#   실행
# =====================================================
if __name__ == "__main__":
    ChatServerGUI()
