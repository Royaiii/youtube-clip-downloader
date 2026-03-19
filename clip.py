"""
YouTube 클립 다운로더 (PyQt6)
"""

import subprocess
import sys
import os
import re
import threading
import time
import json

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QCheckBox, QGroupBox, QSlider, QSizePolicy,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QPalette, QColor


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_executable(name):
    """같은 폴더 → PATH 순서로 실행파일 탐색"""
    # 1) exe/스크립트와 같은 폴더
    local = os.path.join(get_app_dir(), name)
    if os.path.isfile(local):
        return local
    # 2) PATH에서 찾기
    import shutil
    found = shutil.which(name.replace(".exe", "")) or shutil.which(name)
    if found:
        return found
    # 3) Windows WinGet 설치 경로
    if sys.platform == "win32" and name == "ffmpeg.exe":
        winget_base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_base):
            for root, dirs, files in os.walk(winget_base):
                if name in files:
                    return os.path.join(root, name)
    return None


FFMPEG_PATH = find_executable("ffmpeg.exe")
YTDLP_PATH = find_executable("yt-dlp.exe")


def get_ytdlp_cmd():
    if YTDLP_PATH:
        return [YTDLP_PATH]
    return [sys.executable, "-m", "yt_dlp"]


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def format_time(seconds):
    seconds = int(seconds)
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_time(text):
    """M:SS 또는 H:MM:SS → 초"""
    parts = text.strip().split(":")
    parts = [int(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


# --- Signals ---
class WorkerSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    progress_text = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    duration_fetched = pyqtSignal(float, str)


# --- Range Slider ---
class RangeSlider(QWidget):
    rangeChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._low = 0
        self._high = 100
        self._pressed = None
        self.setMinimumHeight(60)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_range(self, min_val, max_val):
        self._min = min_val
        self._max = max(min_val + 1, max_val)
        self._low = min_val
        self._high = max_val
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def set_low(self, val):
        self._low = max(self._min, min(val, self._high - 1))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def set_high(self, val):
        self._high = min(self._max, max(val, self._low + 1))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def low(self):
        return self._low

    def high(self):
        return self._high

    def _val_to_x(self, val):
        margin = 12
        w = self.width() - 2 * margin
        if self._max == self._min:
            return margin
        return margin + int((val - self._min) / (self._max - self._min) * w)

    def _x_to_val(self, x):
        margin = 12
        w = self.width() - 2 * margin
        ratio = max(0.0, min(1.0, (x - margin) / w))
        return int(self._min + ratio * (self._max - self._min))

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QBrush, QPen
        from PyQt6.QtCore import QRect

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 12
        track_y = 20
        track_h = 8
        w = self.width() - 2 * margin

        # track bg
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(60, 60, 60)))
        p.drawRoundedRect(margin, track_y, w, track_h, 4, 4)

        # selected range
        x_low = self._val_to_x(self._low)
        x_high = self._val_to_x(self._high)
        p.setBrush(QBrush(QColor(66, 133, 244)))
        p.drawRoundedRect(x_low, track_y, x_high - x_low, track_h, 4, 4)

        # handles
        for x, color in [(x_low, QColor(66, 133, 244)), (x_high, QColor(234, 67, 53))]:
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawEllipse(x - 8, track_y - 4, 16, 16)

        # time labels
        p.setPen(QPen(QColor(200, 200, 200)))
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.drawText(x_low - 25, 46, format_time(self._low))
        p.drawText(x_high - 25, 46, format_time(self._high))

        p.end()

    def mousePressEvent(self, event):
        x = event.position().x()
        x_low = self._val_to_x(self._low)
        x_high = self._val_to_x(self._high)
        if abs(x - x_low) < abs(x - x_high):
            self._pressed = "low"
        else:
            self._pressed = "high"
        self._handle_mouse(x)

    def mouseMoveEvent(self, event):
        if self._pressed:
            self._handle_mouse(event.position().x())

    def mouseReleaseEvent(self, event):
        self._pressed = None

    def _handle_mouse(self, x):
        val = self._x_to_val(x)
        if self._pressed == "low":
            self.set_low(val)
        elif self._pressed == "high":
            self.set_high(val)


# --- Main Window ---
class ClipDownloaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube 클립 다운로더")
        self.setFixedSize(680, 650)
        self.signals = WorkerSignals()
        self.signals.log.connect(self._append_log)
        self.signals.progress.connect(self._set_progress)
        self.signals.progress_text.connect(self._set_progress_text)
        self.signals.finished.connect(self._on_finished)
        self.signals.duration_fetched.connect(self._on_duration_fetched)
        self._downloading = False
        self._start_time = 0
        self._duration = 0
        self._title = ""

        self._apply_dark_theme()
        self._build_ui()
        self._check_deps()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QGroupBox {
                color: #e0e0e0; border: 1px solid #3a3a3a; border-radius: 6px;
                margin-top: 10px; padding-top: 14px; font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLabel { color: #cccccc; }
            QLineEdit {
                background: #2d2d2d; color: #e0e0e0; border: 1px solid #3a3a3a;
                border-radius: 4px; padding: 6px 8px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #4285f4; }
            QPushButton {
                background: #4285f4; color: white; border: none; border-radius: 4px;
                padding: 8px 18px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #5a9bf4; }
            QPushButton:pressed { background: #3367d6; }
            QPushButton:disabled { background: #3a3a3a; color: #666666; }
            QPushButton#secondaryBtn {
                background: #333333; color: #cccccc;
            }
            QPushButton#secondaryBtn:hover { background: #444444; }
            QTextEdit {
                background: #1a1a1a; color: #aaaaaa; border: 1px solid #2a2a2a;
                border-radius: 4px; font-family: Consolas; font-size: 12px;
            }
            QProgressBar {
                background: #2d2d2d; border: 1px solid #3a3a3a; border-radius: 4px;
                text-align: center; color: #e0e0e0; font-size: 12px; height: 22px;
            }
            QProgressBar::chunk { background: #4285f4; border-radius: 3px; }
            QCheckBox { color: #cccccc; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 12, 16, 12)

        # --- URL ---
        url_group = QGroupBox("YouTube URL")
        url_layout = QHBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtu.be/... 또는 https://www.youtube.com/watch?v=...")
        self.fetch_btn = QPushButton("불러오기")
        self.fetch_btn.setFixedWidth(90)
        self.fetch_btn.clicked.connect(self._fetch_duration)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.fetch_btn)
        layout.addWidget(url_group)

        # --- 구간 선택 ---
        range_group = QGroupBox("구간 선택")
        range_layout = QVBoxLayout(range_group)

        self.video_info_label = QLabel("URL을 입력하고 '불러오기'를 클릭하세요")
        self.video_info_label.setStyleSheet("color: #888888; font-size: 12px;")
        range_layout.addWidget(self.video_info_label)

        self.range_slider = RangeSlider()
        self.range_slider.setEnabled(False)
        self.range_slider.rangeChanged.connect(self._on_range_changed)
        range_layout.addWidget(self.range_slider)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("시작:"))
        self.start_input = QLineEdit("0:00")
        self.start_input.setFixedWidth(80)
        self.start_input.editingFinished.connect(self._on_start_edited)
        time_row.addWidget(self.start_input)
        time_row.addSpacing(20)
        time_row.addWidget(QLabel("종료:"))
        self.end_input = QLineEdit("0:00")
        self.end_input.setFixedWidth(80)
        self.end_input.editingFinished.connect(self._on_end_edited)
        time_row.addWidget(self.end_input)
        time_row.addSpacing(20)
        self.clip_duration_label = QLabel("클립 길이: 0초")
        self.clip_duration_label.setStyleSheet("color: #4285f4; font-weight: bold;")
        time_row.addWidget(self.clip_duration_label)
        time_row.addStretch()
        range_layout.addLayout(time_row)

        layout.addWidget(range_group)

        # --- 저장 설정 ---
        save_group = QGroupBox("저장 설정")
        save_layout = QVBoxLayout(save_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("파일명:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("비우면 영상 제목으로 자동 생성")
        name_row.addWidget(self.name_input)
        save_layout.addLayout(name_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("경로:"))
        self.dir_input = QLineEdit(os.path.join(get_app_dir(), "clips"))
        dir_row.addWidget(self.dir_input)
        browse_btn = QPushButton("폴더 선택")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(browse_btn)
        save_layout.addLayout(dir_row)

        opts_row = QHBoxLayout()
        self.exact_cut_cb = QCheckBox("정확한 자르기 (느림)")
        self.exact_cut_cb.setChecked(False)
        opts_row.addWidget(self.exact_cut_cb)
        self.no_audio_cb = QCheckBox("소리 제거")
        self.no_audio_cb.setChecked(False)
        opts_row.addWidget(self.no_audio_cb)
        opts_row.addStretch()
        save_layout.addLayout(opts_row)

        layout.addWidget(save_group)

        # --- 진행 ---
        progress_group = QGroupBox("진행 상태")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        progress_layout.addWidget(self.progress_bar)

        status_row = QHBoxLayout()
        self.status_label = QLabel("대기 중")
        self.status_label.setStyleSheet("color: #888888;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("color: #888888; font-size: 11px;")
        status_row.addWidget(self.time_label)
        progress_layout.addLayout(status_row)

        layout.addWidget(progress_group)

        # --- 버튼 ---
        btn_row = QHBoxLayout()
        self.dl_btn = QPushButton("다운로드")
        self.dl_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.dl_btn)
        open_btn = QPushButton("폴더 열기")
        open_btn.setObjectName("secondaryBtn")
        open_btn.clicked.connect(self._open_folder)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- 로그 ---
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        layout.addWidget(self.log_text)

        # Timer for elapsed time
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self._update_elapsed)

    def _check_deps(self):
        msgs = []
        if YTDLP_PATH:
            msgs.append(f"yt-dlp: {os.path.basename(YTDLP_PATH)}")
        else:
            msgs.append("yt-dlp: python module")
        if FFMPEG_PATH:
            msgs.append(f"ffmpeg: OK")
        else:
            msgs.append("ffmpeg: 없음!")
        self._append_log(" | ".join(msgs))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.dir_input.text())
        if d:
            self.dir_input.setText(d)

    def _open_folder(self):
        path = self.dir_input.text()
        if os.path.isdir(path):
            os.startfile(path)

    def _append_log(self, msg):
        self.log_text.append(msg)

    def _set_progress(self, val):
        self.progress_bar.setValue(val)

    def _set_progress_text(self, text):
        self.status_label.setText(text)

    def _update_elapsed(self):
        if not self._downloading:
            return
        elapsed = time.time() - self._start_time
        self.time_label.setText(f"경과: {format_time(elapsed)}")

    # --- Fetch Duration ---
    def _fetch_duration(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.video_info_label.setText("영상 정보 불러오는 중...")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            cmd = get_ytdlp_cmd() + [
                "--dump-json", "--no-playlist", url
            ]
            proc = subprocess.run(
                cmd, capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                data = json.loads(stdout)
                duration = data.get("duration", 0)
                title = data.get("title", "clip")
                self.signals.duration_fetched.emit(float(duration), title)
            else:
                self.signals.log.emit(f"오류: {stderr.strip().split(chr(10))[-1]}")
                self.signals.duration_fetched.emit(0, "")
        except Exception as e:
            self.signals.log.emit(f"오류: {e}")
            self.signals.duration_fetched.emit(0, "")

    def _on_duration_fetched(self, duration, title):
        self.fetch_btn.setEnabled(True)
        if duration > 0:
            self._duration = duration
            self._title = title
            self.video_info_label.setText(f"{title[:60]}  ({format_time(duration)})")
            self.range_slider.set_range(0, int(duration))
            self.range_slider.setEnabled(True)
            self.start_input.setText("0:00")
            self.end_input.setText(format_time(duration))
            self._update_clip_duration()
        else:
            self.video_info_label.setText("영상 정보를 불러올 수 없습니다")

    def _on_range_changed(self, low, high):
        self.start_input.setText(format_time(low))
        self.end_input.setText(format_time(high))
        self._update_clip_duration()

    def _on_start_edited(self):
        try:
            val = parse_time(self.start_input.text())
            self.range_slider.set_low(val)
            self._update_clip_duration()
        except (ValueError, IndexError):
            pass

    def _on_end_edited(self):
        try:
            val = parse_time(self.end_input.text())
            self.range_slider.set_high(val)
            self._update_clip_duration()
        except (ValueError, IndexError):
            pass

    def _update_clip_duration(self):
        try:
            s = parse_time(self.start_input.text())
            e = parse_time(self.end_input.text())
            diff = max(0, e - s)
            self.clip_duration_label.setText(f"클립 길이: {diff}초")
        except (ValueError, IndexError):
            pass

    # --- Download ---
    def _start_download(self):
        url = self.url_input.text().strip()
        start = self.start_input.text().strip()
        end = self.end_input.text().strip()

        if not url or not start or not end:
            QMessageBox.warning(self, "입력 필요", "URL, 시작/종료 시간을 입력하세요.")
            return
        if not FFMPEG_PATH:
            QMessageBox.critical(self, "ffmpeg 없음", "ffmpeg.exe를 프로그램과 같은 폴더에 넣어주세요.")
            return

        self._downloading = True
        self._start_time = time.time()
        self.dl_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("다운로드 시작...")
        self.elapsed_timer.start(1000)

        exact = self.exact_cut_cb.isChecked()
        no_audio = self.no_audio_cb.isChecked()
        threading.Thread(target=self._download_worker, args=(url, start, end, exact, no_audio), daemon=True).start()

    def _download_worker(self, url, start, end, exact_cut, no_audio=False):
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
        ffmpeg_dir = os.path.dirname(FFMPEG_PATH) if FFMPEG_PATH else ""

        self.signals.log.emit(f"다운로드: {start} ~ {end}")
        self.signals.progress_text.emit("다운로드 준비 중...")
        self.signals.progress.emit(5)

        # 단일 스트림 포맷 (병합 불필요 = 빠름)
        # 720p mp4 단일 스트림 > 없으면 아무 단일 스트림
        # output_path에서 확장자 제거 (yt-dlp가 자동 추가)
        output_base = output_path.rsplit(".", 1)[0] if "." in output_path else output_path

        cmd = get_ytdlp_cmd()
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", ffmpeg_dir]
        cmd += [
            "--download-sections", f"*{start}-{end}",
            "-f", "best[ext=mp4][height<=1080]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--newline",
            "--progress",
        ]
        if exact_cut:
            cmd += ["--force-keyframes-at-cuts"]
        cmd += ["-o", output_base + ".%(ext)s", url]

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            buf = b""
            while True:
                chunk = proc.stdout.read(1)
                if not chunk:
                    break
                if chunk in (b"\n", b"\r"):
                    if buf:
                        line = buf.decode("utf-8", errors="replace").strip()
                        buf = b""
                        if not line:
                            continue

                        # yt-dlp progress: [download]  45.2% of ~10.50MiB at 2.50MiB/s ETA 00:03
                        m = re.search(r'\[download\]\s+([\d.]+)%', line)
                        if m:
                            pct = float(m.group(1))
                            self.signals.progress.emit(max(5, min(95, int(pct))))

                            parts = []
                            parts.append(f"{pct:.1f}%")
                            size_m = re.search(r'of\s+~?([\d.]+\S+)', line)
                            if size_m:
                                parts.append(size_m.group(1))
                            speed_m = re.search(r'at\s+([\d.]+\S+)', line)
                            if speed_m:
                                parts.append(speed_m.group(1))
                            eta_m = re.search(r'ETA\s+(\S+)', line)
                            if eta_m:
                                parts.append(f"남은: {eta_m.group(1)}")
                            self.signals.progress_text.emit("  |  ".join(parts))

                        elif "[download] 100%" in line:
                            self.signals.progress.emit(95)
                            self.signals.progress_text.emit("처리 중...")
                        elif "[Merger]" in line or "Merging" in line:
                            self.signals.progress_text.emit("병합 중...")
                        elif "Destination" in line:
                            self.signals.progress_text.emit("다운로드 중...")
                        elif "has already been downloaded" in line:
                            self.signals.progress.emit(95)
                            self.signals.progress_text.emit("이미 다운로드됨")
                        elif "Fixing" in line:
                            self.signals.progress_text.emit("프레임 처리 중...")

                        # 로그에도 주요 라인 표시
                        if any(kw in line for kw in ["[download]", "[Merger]", "ERROR", "WARNING"]):
                            if "%" not in line:  # 퍼센트 라인은 너무 많으니 스킵
                                self.signals.log.emit(line)
                else:
                    buf += chunk

            proc.wait()

            # yt-dlp가 실제 생성한 파일 찾기
            actual_path = output_base + ".mp4"
            if not os.path.isfile(actual_path):
                # 혹시 다른 확장자로 생성됐을 수 있음
                import glob
                candidates = glob.glob(output_base + ".*")
                actual_path = candidates[0] if candidates else output_path

            if proc.returncode == 0 and os.path.isfile(actual_path):
                # 소리 제거 옵션
                if no_audio and FFMPEG_PATH:
                    self.signals.progress_text.emit("소리 제거 중...")
                    temp_path = actual_path.rsplit(".", 1)[0] + "_noaudio.mp4"
                    ff_cmd = [
                        FFMPEG_PATH, "-i", actual_path,
                        "-an", "-c:v", "copy", "-y", temp_path
                    ]
                    ff_proc = subprocess.run(
                        ff_cmd, capture_output=True, timeout=60,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    )
                    if ff_proc.returncode == 0 and os.path.isfile(temp_path):
                        os.remove(actual_path)
                        os.rename(temp_path, actual_path)

                size_mb = os.path.getsize(actual_path) / (1024 * 1024)
                self.signals.progress.emit(100)
                self.signals.finished.emit(True, f"{actual_path}\n({size_mb:.1f} MB)")
            else:
                self.signals.finished.emit(False, "다운로드 실패 — 로그를 확인하세요")

        except Exception as e:
            self.signals.finished.emit(False, str(e))

    def _on_finished(self, success, msg):
        self._downloading = False
        self.elapsed_timer.stop()
        self.dl_btn.setEnabled(True)
        elapsed = time.time() - self._start_time

        if success:
            self.status_label.setText("완료!")
            self.status_label.setStyleSheet("color: #34a853; font-weight: bold;")
            self.time_label.setText(f"소요: {format_time(elapsed)}")
            self._append_log(f"완료: {msg}")
            QMessageBox.information(self, "완료", f"저장됨:\n{msg}")
        else:
            self.status_label.setText("실패")
            self.status_label.setStyleSheet("color: #ea4335;")
            self._append_log(f"오류: {msg}")

        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet("color: #888888;"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = ClipDownloaderWindow()
    window.show()
    sys.exit(app.exec())
