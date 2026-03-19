"""
YouTube Clip Downloader
https://github.com/Royaiii/youtube-clip-downloader
"""

import subprocess, sys, os, re, shutil, threading, time, json, glob

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QCheckBox, QFrame, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen


# ─── Utilities ───

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def find_executable(name):
    local = os.path.join(get_app_dir(), name)
    if os.path.isfile(local):
        return local
    found = shutil.which(name.replace(".exe", "")) or shutil.which(name)
    if found:
        return found
    if sys.platform == "win32" and name == "ffmpeg.exe":
        winget = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget):
            for root, _, files in os.walk(winget):
                if name in files:
                    return os.path.join(root, name)
    return None

FFMPEG_PATH = find_executable("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
YTDLP_PATH = find_executable("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")

def get_ytdlp_cmd():
    return [YTDLP_PATH] if YTDLP_PATH else [sys.executable, "-m", "yt_dlp"]

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)

def fmt(seconds):
    s = int(seconds)
    h, m, sc = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sc:02d}" if h else f"{m}:{sc:02d}"

def parse_time(text):
    p = [int(x) for x in text.strip().split(":")]
    if len(p) == 3: return p[0]*3600 + p[1]*60 + p[2]
    if len(p) == 2: return p[0]*60 + p[1]
    return p[0]

def _nw():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

def build_font():
    f = QFont()
    f.setPointSize(10)
    f.setFamilies(["Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo",
                   "Noto Sans CJK KR", "Segoe UI", "Sans Serif"])
    return f


# ─── Signals ───

class Sig(QObject):
    log = pyqtSignal(str)
    prog = pyqtSignal(int)
    status = pyqtSignal(str)
    done = pyqtSignal(bool, str)
    info = pyqtSignal(float, str)


# ─── Range Slider ───

class RangeSlider(QWidget):
    changed = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self._lo = self._mn = 0
        self._hi = self._mx = 100
        self._drag = None
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setRange(self, lo, hi):
        self._mn, self._mx = lo, max(lo+1, hi)
        self._lo, self._hi = lo, hi
        self.update(); self.changed.emit(self._lo, self._hi)

    def setLow(self, v):
        self._lo = max(self._mn, min(v, self._hi-1))
        self.update(); self.changed.emit(self._lo, self._hi)

    def setHigh(self, v):
        self._hi = min(self._mx, max(v, self._lo+1))
        self.update(); self.changed.emit(self._lo, self._hi)

    def low(self): return self._lo
    def high(self): return self._hi

    def _v2x(self, v):
        m = 12; w = self.width() - 2*m
        return m + int((v - self._mn) / max(1, self._mx - self._mn) * w)

    def _x2v(self, x):
        m = 12; w = self.width() - 2*m
        return int(self._mn + max(0, min(1, (x-m)/w)) * (self._mx - self._mn))

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() // 2
        m = 12; w = self.width() - 2*m
        # track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(50, 50, 50)))
        p.drawRoundedRect(m, cy-2, w, 4, 2, 2)
        # selected
        xl, xh = self._v2x(self._lo), self._v2x(self._hi)
        p.setBrush(QBrush(QColor(66, 133, 244)))
        p.drawRoundedRect(xl, cy-2, max(1, xh-xl), 4, 2, 2)
        # handles
        for x, c in [(xl, QColor(66,133,244)), (xh, QColor(219,68,55))]:
            p.setBrush(QBrush(c)); p.setPen(QPen(Qt.GlobalColor.white, 2))
            p.drawEllipse(x-6, cy-6, 12, 12)
        p.end()

    def mousePressEvent(self, e):
        x = e.position().x()
        self._drag = "lo" if abs(x-self._v2x(self._lo)) <= abs(x-self._v2x(self._hi)) else "hi"
        self._move(x)
    def mouseMoveEvent(self, e):
        if self._drag: self._move(e.position().x())
    def mouseReleaseEvent(self, _): self._drag = None
    def _move(self, x):
        v = self._x2v(x)
        self.setLow(v) if self._drag == "lo" else self.setHigh(v)


# ─── Section Card (replaces QGroupBox to avoid padding issues) ───

def make_section(title):
    frame = QFrame()
    frame.setStyleSheet("QFrame { background: #1c1c1c; border: 1px solid #2a2a2a; border-radius: 6px; }")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(12)
    if title:
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(lbl)
    return frame, layout


# ─── Main Window ───

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Clip Downloader")
        self.setFixedSize(720, 700)
        self.setStyleSheet("QMainWindow { background: #141414; }")

        self.sig = Sig()
        self.sig.log.connect(lambda m: self.log.append(m))
        self.sig.prog.connect(lambda v: self.bar.setValue(v))
        self.sig.status.connect(lambda t: self.stat.setText(t))
        self.sig.done.connect(self._done)
        self.sig.info.connect(self._got_info)

        self._dl = False; self._t0 = 0; self._dur = 0; self._title = ""
        self._build()
        self._deps()

    # --- common styles ---
    _input = "background:#1e1e1e; color:#ddd; border:1px solid #333; border-radius:4px; padding:6px 10px; font-size:13px; min-height:18px;"
    _input_focus = "border-color:#4285f4;"
    _btn_primary = "background:#4285f4; color:white; border:none; border-radius:4px; padding:7px 16px; font-size:13px; font-weight:bold; min-height:18px;"
    _btn_flat = "background:#252525; color:#aaa; border:none; border-radius:4px; padding:7px 16px; font-size:13px; min-height:18px;"
    _label = "color:#999; font-size:13px; background:transparent; border:none;"
    _label_accent = "color:#4285f4; font-size:13px; font-weight:bold; background:transparent; border:none;"
    _label_dim = "color:#555; font-size:12px; background:transparent; border:none;"

    def _make_input(self, placeholder="", width=None):
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setStyleSheet(f"QLineEdit {{ {self._input} }} QLineEdit:focus {{ {self._input_focus} }}")
        if width: e.setFixedWidth(width)
        return e

    def _make_btn(self, text, primary=True, width=None):
        b = QPushButton(text)
        style = self._btn_primary if primary else self._btn_flat
        hover = "background:#5a9bf4;" if primary else "background:#333;"
        disabled = "background:#222; color:#444;" if primary else "background:#1c1c1c; color:#444;"
        b.setStyleSheet(f"QPushButton {{ {style} }} QPushButton:hover {{ {hover} }} QPushButton:disabled {{ {disabled} }}")
        if width: b.setFixedWidth(width)
        return b

    def _build(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setSpacing(8)
        root.setContentsMargins(16, 16, 16, 16)

        # ── 1. URL ──
        s1, l1 = make_section("YouTube URL")
        row_url = QHBoxLayout(); row_url.setSpacing(8)
        self.url = self._make_input("https://youtu.be/... 또는 https://www.youtube.com/watch?v=...")
        self.fbtn = self._make_btn("불러오기", width=90)
        self.fbtn.clicked.connect(self._fetch)
        row_url.addWidget(self.url, 1)
        row_url.addWidget(self.fbtn)
        l1.addLayout(row_url)
        root.addWidget(s1)

        # ── 2. 구간 선택 ──
        s2, l2 = make_section("구간 선택")

        self.vinfo = QLabel("URL을 입력하고 '불러오기'를 클릭하세요")
        self.vinfo.setStyleSheet(self._label_dim)
        l2.addWidget(self.vinfo)

        self.slider = RangeSlider(); self.slider.setEnabled(False)
        self.slider.changed.connect(self._on_range)
        l2.addWidget(self.slider)

        row_time = QHBoxLayout(); row_time.setSpacing(8)
        ls = QLabel("시작"); ls.setStyleSheet(self._label); ls.setFixedWidth(30)
        row_time.addWidget(ls)
        self.ts = self._make_input(width=80)
        self.ts.setText("0:00"); self.ts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ts.setMaxLength(8)
        self.ts.editingFinished.connect(lambda: self._sync("s"))
        row_time.addWidget(self.ts)
        row_time.addSpacing(12)
        le = QLabel("종료"); le.setStyleSheet(self._label); le.setFixedWidth(30)
        row_time.addWidget(le)
        self.te = self._make_input(width=80)
        self.te.setText("0:00"); self.te.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.te.setMaxLength(8)
        self.te.editingFinished.connect(lambda: self._sync("e"))
        row_time.addWidget(self.te)
        row_time.addSpacing(16)
        self.dlbl = QLabel("클립 길이: 0초"); self.dlbl.setStyleSheet(self._label_accent)
        row_time.addWidget(self.dlbl)
        row_time.addStretch()
        l2.addLayout(row_time)
        root.addWidget(s2)

        # ── 3. 저장 설정 ──
        s3, l3 = make_section("저장 설정")

        row_name = QHBoxLayout(); row_name.setSpacing(8)
        ln = QLabel("파일명"); ln.setStyleSheet(self._label); ln.setFixedWidth(45)
        ln.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_name.addWidget(ln)
        self.fname = self._make_input("비우면 영상 제목으로 자동 생성")
        row_name.addWidget(self.fname, 1)
        l3.addLayout(row_name)

        row_dir = QHBoxLayout(); row_dir.setSpacing(8)
        ld = QLabel("경로"); ld.setStyleSheet(self._label); ld.setFixedWidth(45)
        ld.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_dir.addWidget(ld)
        self.fdir = self._make_input()
        self.fdir.setText(os.path.join(get_app_dir(), "clips"))
        row_dir.addWidget(self.fdir, 1)
        bb = self._make_btn("폴더 선택", primary=False, width=90)
        bb.clicked.connect(self._browse)
        row_dir.addWidget(bb)
        l3.addLayout(row_dir)

        row_opt = QHBoxLayout(); row_opt.setSpacing(8)
        row_opt.addSpacing(53)  # align with inputs
        self.cb_mute = QCheckBox("소리 제거")
        self.cb_mute.setStyleSheet("QCheckBox { color: #999; font-size: 12px; background: transparent; border: none; }")
        row_opt.addWidget(self.cb_mute)
        row_opt.addStretch()
        l3.addLayout(row_opt)
        root.addWidget(s3)

        # ── 4. 진행 상태 ──
        s4, l4 = make_section("진행 상태")
        self.bar = QProgressBar(); self.bar.setFormat("%p%")
        self.bar.setStyleSheet("""
            QProgressBar { background:#1e1e1e; border:1px solid #2a2a2a; border-radius:4px;
                           text-align:center; color:#aaa; font-size:11px; min-height:20px; max-height:20px; }
            QProgressBar::chunk { background:#4285f4; border-radius:3px; }
        """)
        l4.addWidget(self.bar)
        row_st = QHBoxLayout(); row_st.setSpacing(0)
        self.stat = QLabel("대기 중"); self.stat.setStyleSheet("color:#444; font-size:12px; background:transparent; border:none;")
        row_st.addWidget(self.stat, 1)
        self.tlbl = QLabel(""); self.tlbl.setStyleSheet("color:#444; font-size:11px; background:transparent; border:none;")
        self.tlbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_st.addWidget(self.tlbl)
        l4.addLayout(row_st)
        root.addWidget(s4)

        # ── 5. 버튼 ──
        row_btn = QHBoxLayout(); row_btn.setSpacing(8)
        self.dbtn = self._make_btn("다운로드", width=130)
        self.dbtn.clicked.connect(self._start)
        row_btn.addWidget(self.dbtn)
        ob = self._make_btn("폴더 열기", primary=False, width=100)
        ob.clicked.connect(self._opendir)
        row_btn.addWidget(ob)
        row_btn.addStretch()
        root.addLayout(row_btn)

        # ── 6. 로그 ──
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(64)
        self.log.setStyleSheet("""
            QTextEdit { background:#111; color:#666; border:1px solid #1e1e1e; border-radius:4px;
                        font-family: Consolas, monospace; font-size:11px; padding:6px; }
        """)
        root.addWidget(self.log)

        self.tmr = QTimer(); self.tmr.timeout.connect(self._tick)

    # ── Helpers ──
    def _deps(self):
        self.log.append(f"yt-dlp: {'OK' if YTDLP_PATH else 'module'}  |  ffmpeg: {'OK' if FFMPEG_PATH else 'NOT FOUND'}")
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.fdir.text())
        if d: self.fdir.setText(d)
    def _opendir(self):
        p = self.fdir.text()
        if os.path.isdir(p):
            os.startfile(p) if sys.platform == "win32" else subprocess.Popen(["xdg-open", p])
    def _tick(self):
        if self._dl: self.tlbl.setText(f"경과: {fmt(time.time()-self._t0)}")

    # ── Fetch ──
    def _fetch(self):
        u = self.url.text().strip()
        if not u: return
        self.fbtn.setEnabled(False); self.vinfo.setText("영상 정보 불러오는 중...")
        threading.Thread(target=self._fetch_w, args=(u,), daemon=True).start()

    def _fetch_w(self, url):
        try:
            r = subprocess.run(get_ytdlp_cmd()+["--dump-json","--no-playlist",url],
                               capture_output=True, timeout=30, creationflags=_nw())
            o = r.stdout.decode("utf-8", errors="replace")
            if r.returncode == 0:
                d = json.loads(o)
                self.sig.info.emit(float(d.get("duration",0)), d.get("title","clip"))
            else:
                e = r.stderr.decode("utf-8",errors="replace").strip().splitlines()[-1]
                self.sig.log.emit(f"Error: {e}"); self.sig.info.emit(0,"")
        except Exception as e:
            self.sig.log.emit(f"Error: {e}"); self.sig.info.emit(0,"")

    def _got_info(self, dur, title):
        self.fbtn.setEnabled(True)
        if dur > 0:
            self._dur, self._title = dur, title
            self.vinfo.setText(f"{title[:55]}  ({fmt(dur)})")
            self.slider.setRange(0, int(dur)); self.slider.setEnabled(True)
            self.ts.setText("0:00"); self.te.setText(fmt(dur)); self._updur()
        else:
            self.vinfo.setText("영상 정보를 불러올 수 없습니다")

    def _on_range(self, lo, hi):
        self.ts.setText(fmt(lo)); self.te.setText(fmt(hi)); self._updur()
    def _sync(self, w):
        try:
            v = parse_time(self.ts.text() if w=="s" else self.te.text())
            self.slider.setLow(v) if w=="s" else self.slider.setHigh(v); self._updur()
        except: pass
    def _updur(self):
        try:
            d = max(0, parse_time(self.te.text()) - parse_time(self.ts.text()))
            self.dlbl.setText(f"클립 길이: {d}초")
        except: pass

    # ── Download ──
    def _start(self):
        url, s, e = self.url.text().strip(), self.ts.text().strip(), self.te.text().strip()
        if not url or not s or not e:
            QMessageBox.warning(self,"입력 필요","URL, 시작/종료 시간을 모두 입력하세요."); return
        if not FFMPEG_PATH:
            QMessageBox.critical(self,"ffmpeg 없음","ffmpeg을 설치하거나 같은 폴더에 넣어주세요."); return

        odir = self.fdir.text(); os.makedirs(odir, exist_ok=True)
        nm = self.fname.text().strip()
        if nm:
            if not nm.endswith(".mp4"): nm += ".mp4"
        else:
            t = self._title or "clip"
            nm = f"{sanitize_filename(t[:50])}_{s.replace(':','')}_{e.replace(':','')}.mp4"
        op = os.path.join(odir, nm)

        if os.path.isfile(op):
            r = QMessageBox.question(self,"파일 이미 존재",
                f"'{nm}' 파일이 이미 존재합니다.\n덮어쓰시겠습니까?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes: return

        self._dl, self._t0 = True, time.time()
        self.dbtn.setEnabled(False); self.bar.setValue(0)
        self.stat.setText("다운로드 시작..."); self.stat.setStyleSheet("color:#999; font-size:12px; background:transparent; border:none;")
        self.tmr.start(1000)
        threading.Thread(target=self._dl_w, args=(url,s,e,op,self.cb_mute.isChecked()), daemon=True).start()

    def _dl_w(self, url, start, end, op, mute):
        ffdir = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else ""
        base = op.rsplit(".",1)[0]
        self.sig.log.emit(f"다운로드: {start} ~ {end}")
        self.sig.prog.emit(5); self.sig.status.emit("다운로드 준비 중...")
        cmd = get_ytdlp_cmd()
        if FFMPEG_PATH: cmd += ["--ffmpeg-location", ffdir]
        cmd += ["--download-sections",f"*{start}-{end}",
                "-f","best[ext=mp4][height<=1080]/best[ext=mp4]/best",
                "--merge-output-format","mp4","--no-playlist","--newline","--progress",
                "-o", base+".%(ext)s", url]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=_nw())
            buf = b""
            while True:
                ch = proc.stdout.read(1)
                if not ch: break
                if ch in (b"\n",b"\r"):
                    if buf:
                        ln = buf.decode("utf-8",errors="replace").strip(); buf = b""
                        if not ln: continue
                        m = re.search(r"\[download\]\s+([\d.]+)%", ln)
                        if m:
                            pct = float(m.group(1))
                            self.sig.prog.emit(max(5,min(95,int(pct))))
                            ps = [f"{pct:.1f}%"]
                            for pat,lbl in [(r"of\s+~?([\d.]+\S+)",None),(r"at\s+([\d.]+\S+)",None),(r"ETA\s+(\S+)","남은")]:
                                mm = re.search(pat,ln)
                                if mm: ps.append(f"{lbl}: {mm.group(1)}" if lbl else mm.group(1))
                            self.sig.status.emit("  |  ".join(ps))
                        elif "[download] 100%" in ln:
                            self.sig.prog.emit(95); self.sig.status.emit("처리 중...")
                        elif "[Merger]" in ln: self.sig.status.emit("병합 중...")
                        if any(k in ln for k in ("[download]","[Merger]","ERROR","WARNING")) and "%" not in ln:
                            self.sig.log.emit(ln)
                else: buf += ch
            proc.wait()
            actual = base+".mp4"
            if not os.path.isfile(actual):
                c = glob.glob(base+".*"); actual = c[0] if c else op
            if proc.returncode == 0 and os.path.isfile(actual):
                if mute and FFMPEG_PATH:
                    self.sig.status.emit("소리 제거 중..."); tmp = base+"_noaudio.mp4"
                    subprocess.run([FFMPEG_PATH,"-i",actual,"-an","-c:v","copy","-y",tmp],
                                   capture_output=True,timeout=60,creationflags=_nw())
                    if os.path.isfile(tmp): os.remove(actual); os.rename(tmp,actual)
                mb = os.path.getsize(actual)/(1024*1024)
                self.sig.prog.emit(100); self.sig.done.emit(True, f"{actual}\n({mb:.1f} MB)")
            else: self.sig.done.emit(False, "다운로드 실패 — 로그를 확인하세요")
        except Exception as e: self.sig.done.emit(False, str(e))

    def _done(self, ok, msg):
        self._dl = False; self.tmr.stop(); self.dbtn.setEnabled(True)
        el = time.time()-self._t0
        if ok:
            self.stat.setText("완료!"); self.stat.setStyleSheet("color:#34a853;font-weight:bold;font-size:12px;background:transparent;border:none;")
            self.tlbl.setText(f"소요: {fmt(el)}"); self.log.append(f"완료: {msg}")
            QMessageBox.information(self,"완료",f"저장됨:\n{msg}")
        else:
            self.stat.setText("실패"); self.stat.setStyleSheet("color:#ea4335;font-size:12px;background:transparent;border:none;")
            self.log.append(f"오류: {msg}")
        QTimer.singleShot(3000, lambda: self.stat.setStyleSheet("color:#444;font-size:12px;background:transparent;border:none;"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(build_font())
    w = App(); w.show()
    sys.exit(app.exec())
