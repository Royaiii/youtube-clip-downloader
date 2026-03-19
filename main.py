"""
YouTube Clip Downloader
https://github.com/Royaiii/youtube-clip-downloader
"""

import subprocess
import sys
import os
import re
import shutil
import threading
import time
import json
import glob

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QCheckBox, QGroupBox, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen


# ─── Utilities ───

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_executable(name):
    """Look for executable: same folder -> PATH -> WinGet packages."""
    local = os.path.join(get_app_dir(), name)
    if os.path.isfile(local):
        return local
    found = shutil.which(name.replace(".exe", "")) or shutil.which(name)
    if found:
        return found
    if sys.platform == "win32" and name == "ffmpeg.exe":
        winget = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"
        )
        if os.path.isdir(winget):
            for root, _, files in os.walk(winget):
                if name in files:
                    return os.path.join(root, name)
    return None


FFMPEG_PATH = find_executable("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
YTDLP_PATH = find_executable("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")


def get_ytdlp_cmd():
    if YTDLP_PATH:
        return [YTDLP_PATH]
    return [sys.executable, "-m", "yt_dlp"]


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def format_time(seconds):
    seconds = int(seconds)
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"


def parse_time(text):
    parts = [int(p) for p in text.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _no_window():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ─── Signals ───

class WorkerSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    progress_text = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    duration_fetched = pyqtSignal(float, str)


# ─── Range Slider Widget ───

class RangeSlider(QWidget):
    rangeChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = self._low = 0
        self._max = self._high = 100
        self._pressed = None
        self.setMinimumHeight(60)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_range(self, lo, hi):
        self._min = lo
        self._max = max(lo + 1, hi)
        self._low = lo
        self._high = hi
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def set_low(self, v):
        self._low = max(self._min, min(v, self._high - 1))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def set_high(self, v):
        self._high = min(self._max, max(v, self._low + 1))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def low(self):
        return self._low

    def high(self):
        return self._high

    def _v2x(self, v):
        m = 14
        w = self.width() - 2 * m
        return m + int((v - self._min) / max(1, self._max - self._min) * w)

    def _x2v(self, x):
        m = 14
        w = self.width() - 2 * m
        return int(self._min + max(0.0, min(1.0, (x - m) / w)) * (self._max - self._min))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m, ty, th = 14, 22, 6
        w = self.width() - 2 * m
        # track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(50, 50, 50)))
        p.drawRoundedRect(m, ty, w, th, 3, 3)
        # selected
        xl, xh = self._v2x(self._low), self._v2x(self._high)
        p.setBrush(QBrush(QColor(66, 133, 244)))
        p.drawRoundedRect(xl, ty, max(1, xh - xl), th, 3, 3)
        # handles
        for x, c in [(xl, QColor(66, 133, 244)), (xh, QColor(234, 67, 53))]:
            p.setBrush(QBrush(c))
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawEllipse(x - 7, ty - 4, 14, 14)
        # labels
        p.setPen(QPen(QColor(180, 180, 180)))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(xl - 20, 48, format_time(self._low))
        p.drawText(xh - 20, 48, format_time(self._high))
        p.end()

    def mousePressEvent(self, e):
        x = e.position().x()
        self._pressed = "low" if abs(x - self._v2x(self._low)) < abs(x - self._v2x(self._high)) else "high"
        self._do(x)

    def mouseMoveEvent(self, e):
        if self._pressed:
            self._do(e.position().x())

    def mouseReleaseEvent(self, _e):
        self._pressed = None

    def _do(self, x):
        v = self._x2v(x)
        if self._pressed == "low":
            self.set_low(v)
        else:
            self.set_high(v)


# ─── Stylesheet ───

STYLESHEET = """
QMainWindow { background: #181818; }
QGroupBox {
    color: #d0d0d0; border: 1px solid #333; border-radius: 8px;
    margin-top: 12px; padding: 16px 12px 10px 12px; font-size: 13px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
QLabel { color: #bbb; font-size: 13px; }
QLineEdit {
    background: #242424; color: #e0e0e0; border: 1px solid #383838;
    border-radius: 5px; padding: 7px 10px; font-size: 13px; selection-background-color: #4285f4;
}
QLineEdit:focus { border-color: #4285f4; }
QPushButton {
    background: #4285f4; color: #fff; border: none; border-radius: 5px;
    padding: 8px 20px; font-size: 13px; font-weight: bold;
}
QPushButton:hover { background: #5a9bf4; }
QPushButton:pressed { background: #3367d6; }
QPushButton:disabled { background: #333; color: #666; }
QPushButton[secondary="true"] { background: #2a2a2a; color: #bbb; }
QPushButton[secondary="true"]:hover { background: #383838; }
QTextEdit {
    background: #141414; color: #888; border: 1px solid #252525;
    border-radius: 5px; font-family: 'Cascadia Code', Consolas, monospace; font-size: 11px;
    padding: 6px;
}
QProgressBar {
    background: #242424; border: 1px solid #333; border-radius: 5px;
    text-align: center; color: #ccc; font-size: 11px; min-height: 20px;
}
QProgressBar::chunk { background: #4285f4; border-radius: 4px; }
QCheckBox { color: #bbb; font-size: 12px; spacing: 6px; }
"""


# ─── Main Window ───

class ClipDownloaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Clip Downloader")
        self.setFixedSize(700, 680)
        self.setStyleSheet(STYLESHEET)

        self.signals = WorkerSignals()
        self.signals.log.connect(self._append_log)
        self.signals.progress.connect(lambda v: self.progress_bar.setValue(v))
        self.signals.progress_text.connect(lambda t: self.status_label.setText(t))
        self.signals.finished.connect(self._on_finished)
        self.signals.duration_fetched.connect(self._on_duration_fetched)

        self._downloading = False
        self._start_time = 0
        self._duration = 0
        self._title = ""

        self._build_ui()
        self._check_deps()

    def _build_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        root = QVBoxLayout(c)
        root.setSpacing(6)
        root.setContentsMargins(18, 14, 18, 14)

        # ── URL ──
        g1 = QGroupBox("YouTube URL")
        h1 = QHBoxLayout(g1)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtu.be/... 또는 https://www.youtube.com/watch?v=...")
        self.fetch_btn = QPushButton("불러오기")
        self.fetch_btn.setFixedWidth(90)
        self.fetch_btn.clicked.connect(self._fetch_duration)
        h1.addWidget(self.url_input)
        h1.addWidget(self.fetch_btn)
        root.addWidget(g1)

        # ── Range ──
        g2 = QGroupBox("구간 선택")
        v2 = QVBoxLayout(g2)
        self.video_info = QLabel("URL을 입력하고 '불러오기'를 클릭하세요")
        self.video_info.setStyleSheet("color:#666; font-size:12px;")
        v2.addWidget(self.video_info)

        self.slider = RangeSlider()
        self.slider.setEnabled(False)
        self.slider.rangeChanged.connect(self._on_range)
        v2.addWidget(self.slider)

        tr = QHBoxLayout()
        tr.addWidget(QLabel("시작:"))
        self.t_start = QLineEdit("0:00")
        self.t_start.setFixedWidth(80)
        self.t_start.editingFinished.connect(lambda: self._sync_slider("start"))
        tr.addWidget(self.t_start)
        tr.addSpacing(16)
        tr.addWidget(QLabel("종료:"))
        self.t_end = QLineEdit("0:00")
        self.t_end.setFixedWidth(80)
        self.t_end.editingFinished.connect(lambda: self._sync_slider("end"))
        tr.addWidget(self.t_end)
        tr.addSpacing(16)
        self.dur_label = QLabel("클립 길이: 0초")
        self.dur_label.setStyleSheet("color:#4285f4; font-weight:bold;")
        tr.addWidget(self.dur_label)
        tr.addStretch()
        v2.addLayout(tr)
        root.addWidget(g2)

        # ── Save ──
        g3 = QGroupBox("저장 설정")
        v3 = QVBoxLayout(g3)

        nr = QHBoxLayout()
        nr.addWidget(QLabel("파일명:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("비우면 영상 제목으로 자동 생성")
        nr.addWidget(self.name_input)
        v3.addLayout(nr)

        dr = QHBoxLayout()
        dr.addWidget(QLabel("경로:"))
        self.dir_input = QLineEdit(os.path.join(get_app_dir(), "clips"))
        dr.addWidget(self.dir_input)
        bb = QPushButton("폴더 선택")
        bb.setProperty("secondary", True)
        bb.setFixedWidth(90)
        bb.clicked.connect(self._browse)
        dr.addWidget(bb)
        v3.addLayout(dr)

        orow = QHBoxLayout()
        self.cb_exact = QCheckBox("정확한 자르기 (느림)")
        self.cb_audio = QCheckBox("소리 제거")
        orow.addWidget(self.cb_exact)
        orow.addWidget(self.cb_audio)
        orow.addStretch()
        v3.addLayout(orow)
        root.addWidget(g3)

        # ── Progress ──
        g4 = QGroupBox("진행 상태")
        v4 = QVBoxLayout(g4)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p%")
        v4.addWidget(self.progress_bar)

        sr = QHBoxLayout()
        self.status_label = QLabel("대기 중")
        self.status_label.setStyleSheet("color:#666;")
        sr.addWidget(self.status_label)
        sr.addStretch()
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("color:#666; font-size:11px;")
        sr.addWidget(self.time_label)
        v4.addLayout(sr)
        root.addWidget(g4)

        # ── Buttons ──
        br = QHBoxLayout()
        self.dl_btn = QPushButton("다운로드")
        self.dl_btn.clicked.connect(self._start_download)
        br.addWidget(self.dl_btn)
        ob = QPushButton("폴더 열기")
        ob.setProperty("secondary", True)
        ob.clicked.connect(self._open_folder)
        br.addWidget(ob)
        br.addStretch()
        root.addLayout(br)

        # ── Log ──
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        root.addWidget(self.log)

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    # ── Helpers ──

    def _check_deps(self):
        parts = []
        parts.append(f"yt-dlp: {'OK' if YTDLP_PATH else 'python module'}")
        parts.append(f"ffmpeg: {'OK' if FFMPEG_PATH else 'NOT FOUND'}")
        self._append_log(" | ".join(parts))

    def _append_log(self, msg):
        self.log.append(msg)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.dir_input.text())
        if d:
            self.dir_input.setText(d)

    def _open_folder(self):
        p = self.dir_input.text()
        if os.path.isdir(p):
            if sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])

    def _tick(self):
        if self._downloading:
            self.time_label.setText(f"경과: {format_time(time.time() - self._start_time)}")

    # ── Fetch ──

    def _fetch_duration(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.video_info.setText("영상 정보 불러오는 중...")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            proc = subprocess.run(
                get_ytdlp_cmd() + ["--dump-json", "--no-playlist", url],
                capture_output=True, timeout=30, creationflags=_no_window(),
            )
            out = proc.stdout.decode("utf-8", errors="replace")
            err = proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                d = json.loads(out)
                self.signals.duration_fetched.emit(float(d.get("duration", 0)), d.get("title", "clip"))
            else:
                self.signals.log.emit(f"Error: {err.strip().splitlines()[-1]}")
                self.signals.duration_fetched.emit(0, "")
        except Exception as e:
            self.signals.log.emit(f"Error: {e}")
            self.signals.duration_fetched.emit(0, "")

    def _on_duration_fetched(self, dur, title):
        self.fetch_btn.setEnabled(True)
        if dur > 0:
            self._duration = dur
            self._title = title
            self.video_info.setText(f"{title[:60]}  ({format_time(dur)})")
            self.slider.set_range(0, int(dur))
            self.slider.setEnabled(True)
            self.t_start.setText("0:00")
            self.t_end.setText(format_time(dur))
            self._update_dur()
        else:
            self.video_info.setText("영상 정보를 불러올 수 없습니다")

    # ── Range sync ──

    def _on_range(self, lo, hi):
        self.t_start.setText(format_time(lo))
        self.t_end.setText(format_time(hi))
        self._update_dur()

    def _sync_slider(self, which):
        try:
            v = parse_time(self.t_start.text() if which == "start" else self.t_end.text())
            if which == "start":
                self.slider.set_low(v)
            else:
                self.slider.set_high(v)
            self._update_dur()
        except (ValueError, IndexError):
            pass

    def _update_dur(self):
        try:
            d = max(0, parse_time(self.t_end.text()) - parse_time(self.t_start.text()))
            self.dur_label.setText(f"클립 길이: {d}초")
        except (ValueError, IndexError):
            pass

    # ── Download ──

    def _start_download(self):
        url = self.url_input.text().strip()
        start = self.t_start.text().strip()
        end = self.t_end.text().strip()

        if not url or not start or not end:
            QMessageBox.warning(self, "입력 필요", "URL, 시작/종료 시간을 모두 입력하세요.")
            return
        if not FFMPEG_PATH:
            QMessageBox.critical(self, "ffmpeg 없음", "ffmpeg을 설치하거나 프로그램과 같은 폴더에 넣어주세요.")
            return

        # Build output path and check overwrite
        output_dir = self.dir_input.text()
        os.makedirs(output_dir, exist_ok=True)

        name = self.name_input.text().strip()
        if name:
            if not name.endswith(".mp4"):
                name += ".mp4"
        else:
            title = self._title if self._title else "clip"
            name = f"{sanitize_filename(title[:50])}_{start.replace(':', '')}_{end.replace(':', '')}.mp4"

        output_path = os.path.join(output_dir, name)

        if os.path.isfile(output_path):
            reply = QMessageBox.question(
                self,
                "파일 이미 존재",
                f"'{name}' 파일이 이미 존재합니다.\n덮어쓰시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._downloading = True
        self._start_time = time.time()
        self.dl_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("다운로드 시작...")
        self.status_label.setStyleSheet("color:#bbb;")
        self.timer.start(1000)

        threading.Thread(
            target=self._download_worker,
            args=(url, start, end, output_path, self.cb_exact.isChecked(), self.cb_audio.isChecked()),
            daemon=True,
        ).start()

    def _download_worker(self, url, start, end, output_path, exact_cut, no_audio):
        ffmpeg_dir = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else ""
        output_base = output_path.rsplit(".", 1)[0]

        self.signals.log.emit(f"다운로드: {start} ~ {end}")
        self.signals.progress.emit(5)
        self.signals.progress_text.emit("다운로드 준비 중...")

        cmd = get_ytdlp_cmd()
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", ffmpeg_dir]
        cmd += [
            "--download-sections", f"*{start}-{end}",
            "-f", "best[ext=mp4][height<=1080]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--no-playlist", "--newline", "--progress",
        ]
        if exact_cut:
            cmd += ["--force-keyframes-at-cuts"]
        cmd += ["-o", output_base + ".%(ext)s", url]

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=_no_window(),
            )

            buf = b""
            while True:
                ch = proc.stdout.read(1)
                if not ch:
                    break
                if ch in (b"\n", b"\r"):
                    if buf:
                        line = buf.decode("utf-8", errors="replace").strip()
                        buf = b""
                        if not line:
                            continue
                        m = re.search(r"\[download\]\s+([\d.]+)%", line)
                        if m:
                            pct = float(m.group(1))
                            self.signals.progress.emit(max(5, min(95, int(pct))))
                            parts = [f"{pct:.1f}%"]
                            sm = re.search(r"of\s+~?([\d.]+\S+)", line)
                            if sm:
                                parts.append(sm.group(1))
                            sp = re.search(r"at\s+([\d.]+\S+)", line)
                            if sp:
                                parts.append(sp.group(1))
                            et = re.search(r"ETA\s+(\S+)", line)
                            if et:
                                parts.append(f"남은: {et.group(1)}")
                            self.signals.progress_text.emit("  |  ".join(parts))
                        elif "[download] 100%" in line:
                            self.signals.progress.emit(95)
                            self.signals.progress_text.emit("처리 중...")
                        elif "[Merger]" in line:
                            self.signals.progress_text.emit("병합 중...")
                        elif "Destination" in line:
                            self.signals.progress_text.emit("다운로드 중...")
                        if any(k in line for k in ("[download]", "[Merger]", "ERROR", "WARNING")):
                            if "%" not in line:
                                self.signals.log.emit(line)
                else:
                    buf += ch

            proc.wait()

            actual = output_base + ".mp4"
            if not os.path.isfile(actual):
                cands = glob.glob(output_base + ".*")
                actual = cands[0] if cands else output_path

            if proc.returncode == 0 and os.path.isfile(actual):
                if no_audio and FFMPEG_PATH:
                    self.signals.progress_text.emit("소리 제거 중...")
                    tmp = actual.rsplit(".", 1)[0] + "_noaudio.mp4"
                    subprocess.run(
                        [FFMPEG_PATH, "-i", actual, "-an", "-c:v", "copy", "-y", tmp],
                        capture_output=True, timeout=60, creationflags=_no_window(),
                    )
                    if os.path.isfile(tmp):
                        os.remove(actual)
                        os.rename(tmp, actual)

                mb = os.path.getsize(actual) / (1024 * 1024)
                self.signals.progress.emit(100)
                self.signals.finished.emit(True, f"{actual}\n({mb:.1f} MB)")
            else:
                self.signals.finished.emit(False, "다운로드 실패 — 로그를 확인하세요")

        except Exception as e:
            self.signals.finished.emit(False, str(e))

    def _on_finished(self, ok, msg):
        self._downloading = False
        self.timer.stop()
        self.dl_btn.setEnabled(True)
        elapsed = time.time() - self._start_time

        if ok:
            self.status_label.setText("완료!")
            self.status_label.setStyleSheet("color:#34a853; font-weight:bold;")
            self.time_label.setText(f"소요: {format_time(elapsed)}")
            self._append_log(f"완료: {msg}")
            QMessageBox.information(self, "완료", f"저장됨:\n{msg}")
        else:
            self.status_label.setText("실패")
            self.status_label.setStyleSheet("color:#ea4335;")
            self._append_log(f"오류: {msg}")

        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet("color:#666;"))


# ─── Entry ───

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = ClipDownloaderWindow()
    w.show()
    sys.exit(app.exec())
