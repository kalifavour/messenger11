# misoyeon_client17.py
import json
import os.path
import threading
import tkinter as tk
import winsound

from dataclasses import dataclass
from datetime import datetime
from socket import *
from time import sleep
from tkinter import messagebox as tkmbox
from tkinter import ttk, scrolledtext

KEEPALIVE_INTERVAL = 10 # 초 (heartbeat)

@dataclass
class SoundConfig:
    sound: int
    sound_height: int  
    sound_length: int  

def time_tag():
    return datetime.now().strftime("%H:%M")

# =====================================================
#   ChatClient  (소켓 + 스레드)
# =====================================================
class ChatClient:
    def __init__(self, print_callback, disconnect_callback):   
        self.print_callback = print_callback
        self.set_controls = disconnect_callback
        self.BUFSIZE = 1024
        self.sock = None
        self.running = False
        self.server_ip = None
        self.server_port = None

        self.sound_config: SoundConfig | None = None 

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

    def server_addr_to_GUI(self): # GUI로 addr 보내줌.
        return self.server_ip, self.server_port


    def get_broadcast_addr(self):
        print('* ChatClientGUI: get_broadcast_addr\n')

        BROADCAST_IP = '255.255.255.255'
        BROADCAST_PORT = 50100 # 서버와 사전 약속된 포트
        TIMEOUT = 1
        RETRY = 1

        isock = socket(AF_INET, SOCK_DGRAM)
        isock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
        isock.settimeout(TIMEOUT)
        message = b'DISCOVER_SERVER'

        for _ in range(RETRY):
            try:
                isock.sendto(message, (BROADCAST_IP, BROADCAST_PORT))
                data, addr = isock.recvfrom(1024)
                print(f'{addr=}')

                text = data.decode()
                parts = dict(item.split('=') for item in text.split(';'))

                server_ip = parts['IP']
                server_port = int(parts['PORT'])
                return server_ip, server_port

            except timeout:
                print('Discovery timeout, retry...')
                sleep(0.5)

        return None, None

    # =====================================================
    #   서버로 연결
    # =====================================================
    def _connect(self):
        print('* ChatClient: _connect')

        self.server_ip, self.server_port = self.get_broadcast_addr()

        try:
            # 소켓 생성
            self.sock = socket(AF_INET, SOCK_STREAM)
            self.sock.settimeout(1.0)

            # 서버 연결
            self.sock.connect((self.server_ip, self.server_port))

            # 연결 성공 처리 => _recv_loop, _keepalive_loop
            self._on_connect_success()
            return True

        except timeout: # 서버 응답 없음!
            print(f'* check timeout')
            tkmbox.showerror('타임아웃','서버가 [Start] 되었는지 확인하세요.')

        except Exception as e: # get_broadcast_addr에서 timeout 예외발생.
            #self.xprint(f"! _connect:서버 연결 실패: {e}\n\n")
            tkmbox.showerror('서버확인','서버가 [Start] 되었는지 확인하세요.')
            return False            

    def _on_connect_success(self):
        print('* ChatClient: _on_connect_success')

        self.running = True

        stamp = time_tag()
        self.xprint(f'* 서버 연결됨 ({stamp})\n\n')

        # 서버 연결음.
        self.exe_alarm(self.sound, self.sound_height, self.sound_length) # 기본음,  800Hz, 500ms
        
        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()
        return True

    def _keepalive_loop(self):
        while self.running:
            try:
                self.sock.send(b'\x00') # heartbeat
            except Exception as e:
                self.xprint(f'! KeepAlive 실패: {e}\n')
                break
            sleep(KEEPALIVE_INTERVAL)

    def _recv_loop(self):
        print('* ChatClient: _recv_loop in 1st')

        while self.running and self.sock:
            try:
                stamp = time_tag()
                data = self.sock.recv(self.BUFSIZE)

                if not data: # 서버가 정상 종료.
                    self._on_server_disconnected()
                    break

                if data == b'\x00': # heartbeat => 무시
                    continue

                self._handle_message(data)

            except timeout:
                continue
            except Exception as e: # 비정상 연결종료. 
                print(f'* Debug : {e=}')
                #self.xprint(f'! 수신 오류: {e}\n')
                break

        self._close_sockets() # self.running = False 포함.

    # =====================================================
    #   모든 종료는 이곳에서 (중복 종료하지 않도록)
    # =====================================================
    def _close_sockets(self):
        print('* ChatClient: _close_sockets')

        if not self.running:
            return
        self.running = False

        try:
            self.sock.shutdown(SHUT_RDWR)
        except:
            pass
        try:
            self.sock.close()
        except:
            pass
        self.xprint(f"* 연결 종료됨 ({time_tag()})\n\n")
        self.set_controls(False)     

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

    def _on_server_disconnected(self):
        stamp = time_tag()
        self.xprint(f'* 서버에서 연결을 종료하였습니다. ({stamp})\n\n')

    def _send(self, text):
        print('* ChatClient: _send')

        if self.sock and self.running:
            try:
                self.sock.send(text.encode())
                return True
            except Exception as e:
                stamp = time_tag()
                self.xprint(f' 송신 오류: {e} ({stamp})\n')
                #return False
        return False



# =====================================================
#   ChatClientGUI (Tkinter)
# =====================================================
class ChatClientGUI:
    CONFIG_FILE =  "./misoyeon_11_client_config.json"

    def __init__(self):
        self.client = ChatClient(self.xPrint, self.set_controls) 

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
        self.win.title(f"미소연 Client - {os.path.basename(__file__)}{' '*18}by JYHn")

        # 최초 실행했을때의 위치(정중앙)
        screen_width  = self.win.winfo_screenwidth()  # 1920 
        screen_height = self.win.winfo_screenheight() # 1080
        gui_x  = int(screen_width/2) - int(self.MENU_W/2)
        gui_y = int(screen_height/2) - int(self.MENU_H/2)
        #print(f'{gui_x=}, {gui_y=}') # 1980x1080에서는 (710,370)

        self.default_config = {
            "idLabel": "◀대기실▶",
            "x": gui_x,
            "y": gui_y,
            "sound": 1, # 기본음(삑)
            "sound_height": 800, # Hz
            "sound_length": 500  # ms            
        }

        # ----------------------
        # config.json 불러오기
        # ----------------------
        #self.load_default_config()
        #self.load_style()        

        x_geometry = f'{self.MENU_W}x{self.MENU_H}+{self.gui_x}+{self.gui_y}'
        self.win.geometry(x_geometry)
        self.win.resizable(False, False)

        self.win.bind("<Configure>", self.on_configure) # GUI 위치 저장 위해서.

        # 메시지 히스토리
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

        ### GUI에 data setting, 이전 GUI 위치에 출현.
        self.win.withdraw() ######### GUI 안보이기.
        self.load_process()
        self.display_load_data()
        self.win.deiconify() ######## GUI 보이기.

        self.apply_sound_config_to_client() # 알림음 설정 변수를 확보.
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


    # =============================================
    #    config.json 읽기/쓰기/검증
    # =============================================
    def load_process(self):
        print('* ChatClientGUI: load_process')        

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
        print('* ChatClientGUI: load_data')        

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
        print('* ChatClientGUI: display_load_data')        

        self.label_idLabel['text'] = self.imsi_label
        self.idLabel.set(self.imsi_label)

        # load data에 의해서 직전 마지막 위치로 GUI 보여줌.
        x_geometry = f'{self.MENU_W}x{self.MENU_H}+{self.gui_x}+{self.gui_y}'
        self.win.geometry(x_geometry)

        self.alarm_sound.set(self.sound)
        self.cbox_sound_height.set(self.sound_height)
        self.cbox_sound_length.set(self.sound_length/1000)

    def save_default(self):
        print('* ChatClientGUI: save_default')        

        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.default_config, f, indent=4, ensure_ascii=False)
            return True
        except:
            return False

    def load_saved_file(self):
        print('* ChatClientGUI: load_saved_file')

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                self.saved = json.load(f)
                return True
        except Exception as e:
            print(f"설정파일 오류: {e}")
            return False 

    def validate_data(self):
        print('* ChatClientGUI: validate_data')        

        errors = []

        # idLabel: str 타입, 최소 3자 이상
        id_label = str(self.saved.get("idLabel", ''))[:10].strip()
        if not isinstance(id_label, str) or len(id_label) < 3 or None:
            errors.append("설정파일의 Label 이상입니다.")
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

    def load_notebook_style(self):
        print('* ChatClientGUI: load_notebook_style')        

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


    # -------------------------------------
    #    알림음을 class ChatClient에 연결
    # -------------------------------------
    def apply_sound_config_to_client(self):
        print('* ChatClientGUI: apply_sound_config_to_client')        

        config = SoundConfig(
            sound = self.alarm_sound.get(),
            sound_height = int(self.cbox_sound_height.get()),
            sound_length = int(float(self.cbox_sound_length.get())*1000)
            )
        self.client.set_config(config)


    # =====================================================
    # GUI 구성
    # =====================================================
    def _build_tabs(self):
        print('* ChatClientGUI: _build_tabs')

        # 2 Tabs.
        self.tab_chatting = tk.Frame(self.nbook)
        self.tab_chatting.pack()
        self.tab_setting = tk.Frame(self.nbook)
        self.tab_setting.pack()
        self.tab_inform = tk.Frame(self.nbook)
        self.tab_inform.pack()

        self.nbook.add(self.tab_chatting, text='Chatting ◖ Client ◗')
        self.nbook.add(self.tab_setting,  text='Setting')
        self.nbook.add(self.tab_inform,  text='Inform')

        # Chatting Tab.
        self.fr_addr = tk.Frame(self.tab_chatting)
        self.fr_addr.pack(side="top", fill="both", padx=10, pady=5)
        self.fr_text = tk.Frame(self.tab_chatting)
        self.fr_text.pack(side="top", fill="both")
        self.fr_control = tk.Frame(self.tab_chatting)
        self.fr_control.pack(side="top", fill="x", padx=10, pady=5)

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
        print('* ChatClientGUI: _build_chatting_tab')

        # Addr Area
        self.ip = tk.StringVar(value=self.server_ip)
        ttk.Label(self.fr_addr, text='IP').pack(side='left')
        self.entry_ip = ttk.Entry(self.fr_addr, state='readonly', textvariable=self.ip, width=12)
        self.entry_ip.pack(side='left', padx=10)

        self.port = tk.StringVar(value=self.server_port)
        ttk.Label(self.fr_addr, text="Port").pack(side="left")
        self.entry_port = ttk.Entry(self.fr_addr, state='readonly', \
            textvariable=self.port, width=8)
        self.entry_port.pack(side="left", padx=10)

        self.btn_connect = ttk.Button(self.fr_addr, text="Connect", width=17, command=self.onConnect)
        self.btn_connect.pack(side="left", expand=True, fill="both")

        # ScrolledText Area
        self.txt = scrolledtext.ScrolledText(self.fr_text, height=17)
        self.txt.pack(fill="both", padx=15)
        self.txt.insert("end", "* 서버 먼저 실행 후 클라이언트 실행해 주세요 *\n\n")
        self.txt["state"] = "disabled"

        # Control Area
        self.label_idLabel = tk.Label(self.fr_control)
        self.label_idLabel.pack(side='left')
        self.msg = tk.StringVar()
        self.entry_msg = ttk.Entry(self.fr_control, font=('맑은고딕',12), textvariable=self.msg)
        self.entry_msg.pack(side="left", expand=True, fill="both", padx=2)

        # Enter → 전송
        self.entry_msg.bind("<Return>", lambda e: self.onSend())

        # ↑↓ 화살표 → 메시지 히스토리
        self.entry_msg.bind("<Up>", self.onHistoryUp)
        self.entry_msg.bind("<Down>", self.onHistoryDown)

        self.btn_send = ttk.Button(self.fr_control, text="Send", width=10, command=self.onSend)
        self.btn_send.pack(side="left", padx=5)

        # 처음에는 비활성화
        self.set_controls(False)

        # --------------------------------
        #    Setting Tab
        # --------------------------------
    def _build_setting_tab(self):
        print('* ChatClientGUI: _build_setting_tab')

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
        print('* ChatClientGUI: _build_inform_tab')       

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
            self.client.exe_alarm(xsound, _height, _length)
        
        elif xsound ==2: # 윈도우 기본음
            self.client.exe_alarm(xsound)

    def save_config(self, *, silent=False):
        print('* ChatClientGUI: save_config')        

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

        self.apply_sound_config_to_client()

        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_values, f, indent=4, ensure_ascii=False)
        except Exception:
            tkmbox.showerror('* 설정파일 에러로 변경사항이 저장되지 않았습니다!')
    
    # =====================================================
    # GUI 출력
    # =====================================================
    def xPrint(self, msg):
        def _update():
            self.txt["state"] = "normal"
            self.txt.insert("end", msg)
            self.txt.see("end")
            self.txt["state"] = "disabled"
        self.txt.after(0, _update)

    # 입력창 활성/비활성
    def set_controls(self, enable):
        print('* ChatClientGUI: set_controls\n')

        if enable:
            self.entry_msg['state'] = 'normal'
            self.entry_msg.focus_set()
            self.btn_send['state'] = 'normal'
            self.btn_connect['text'] = 'Disconnect'
        else:
            self.entry_msg['state'] = 'disabled'
            self.btn_send['state'] = 'disabled'
            self.btn_connect['text'] = 'Connect'
        ## Server와 달리 Client는 [Connect]와 연동되기에
        ## 이곳에서 btn_connect['text']를 지정해야 된다.

    # ===========================================
    #   Connect / Disconnect
    # ===========================================
    def onConnect(self): # ip/port 변화 체크!
        print('* ChatClientGUI: onConnect')

        if self.btn_connect["text"] == "Connect":
            #self.btn_connect["text"] = "Disconnect"

            if self.client._connect():
                self.server_ip, self.server_port = self.client.server_addr_to_GUI()

                self.ip.set(self.server_ip)
                self.port.set(self.server_port)
                self.set_controls(True) # 버튼 텍스트를 바꾸어줌.
        else:
            self.client._close_sockets()
            #self.set_controls(False) #=> client._close_sockets()에 포함됨.


    # ================================
    #   메세지 전송
    # ================================
    def onSend(self): 
        print('* ChatClientGUI: onSend')

        itext = self.msg.get().strip()
        if not itext:
            return

        # 메시지 히스토리 관리.
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

        if self.client._send(json_text):
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
            # 마지막 이후는 빈칸
            self.history_index = len(self.history)
            self.msg.set("")

        self.entry_msg.icursor("end")


# =====================================================
#   실행
# =====================================================
if __name__ == "__main__":
    ChatClientGUI()
