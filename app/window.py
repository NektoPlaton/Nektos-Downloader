from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QComboBox,
    QProgressBar,
    QFileDialog,
)

from app.downloader import (
    DOWNLOAD_DIR,
    download_video,
    get_video_info,
    remove_partial_files,
)


class DownloadThread(QThread):
    finished_signal = Signal()
    cancelled_signal = Signal(set)
    error_signal = Signal(str, set)
    progress_signal = Signal(float, str, str)

    def __init__(
        self,
        url: str,
        quality: str,
        download_dir: Path,
        resume: bool = False,
    ):
        super().__init__()

        self.url = url
        self.quality = quality
        self.download_dir = download_dir
        self.resume = resume
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def is_cancelled(self) -> bool:
        return self.cancel_requested

    def progress_update(
        self,
        percent: float,
        speed_text: str,
        eta_text: str,
    ) -> None:
        self.progress_signal.emit(percent, speed_text, eta_text)

    def run(self) -> None:
        try:
            was_cancelled, created_files = download_video(
                url=self.url,
                quality=self.quality,
                download_dir=self.download_dir,
                progress_callback=self.progress_update,
                cancel_callback=self.is_cancelled,
                resume=self.resume,
            )

        except Exception as error:
            self.error_signal.emit(str(error), set())
            return

        if was_cancelled:
            self.cancelled_signal.emit(created_files)
        else:
            self.finished_signal.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.download_thread = None
        self.is_paused = False

        self.last_url = None
        self.last_quality = None
        self.last_download_dir = DOWNLOAD_DIR

        self.created_files: set[str] = set()

        self.setWindowTitle("Nekto's Downloader")
        self.setMinimumSize(760, 620)

        central_widget = QWidget()
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)

        outer_layout = QVBoxLayout(central_widget)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.setContentsMargins(45, 40, 45, 40)

        card = QWidget()
        card.setObjectName("card")
        card.setMaximumWidth(720)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(42, 34, 42, 34)
        layout.setSpacing(14)

        title = QLabel("Nekto's Downloader")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Скачивайте видео в выбранную папку")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("Вставьте ссылку на видео...")

        self.info_button = QPushButton("Получить информацию")
        self.info_button.setObjectName("info_button")
        self.info_button.clicked.connect(self.load_video_info)

        url_layout = QHBoxLayout()
        url_layout.setSpacing(10)
        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.info_button)

        folder_title = QLabel("Папка сохранения")
        folder_title.setObjectName("field_label")

        self.save_folder_input = QLineEdit()
        self.save_folder_input.setObjectName("save_folder_input")
        self.save_folder_input.setReadOnly(True)
        self.save_folder_input.setText(str(DOWNLOAD_DIR.resolve()))

        self.folder_button = QPushButton("Выбрать папку")
        self.folder_button.setObjectName("folder_button")
        self.folder_button.clicked.connect(self.choose_download_folder)

        folder_layout = QHBoxLayout()
        folder_layout.setSpacing(10)
        folder_layout.addWidget(self.save_folder_input, 1)
        folder_layout.addWidget(self.folder_button)

        self.status_label = QLabel("Готов к работе")
        self.status_label.setObjectName("status_label")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.status_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.quality_box = QComboBox()
        self.quality_box.setObjectName("quality_box")
        self.quality_box.addItem("Выберите качество")
        self.quality_box.setEnabled(False)

        self.download_button = QPushButton("Скачать")
        self.download_button.setObjectName("download_button")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.start_download)

        self.stop_button = QPushButton("Стоп")
        self.stop_button.setObjectName("stop_button")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.toggle_stop_resume)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        buttons_layout.addWidget(self.download_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.cancel_button)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        layout.addLayout(url_layout)
        layout.addWidget(folder_title)
        layout.addLayout(folder_layout)

        layout.addSpacing(6)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        layout.addSpacing(2)

        layout.addWidget(self.quality_box)
        layout.addLayout(buttons_layout)

        outer_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        self._load_styles()

    def _load_styles(self) -> None:
        styles_path = Path(__file__).parent / "resources" / "styles.qss"

        if not styles_path.exists():
            print(f"Не найден файл стилей: {styles_path}")
            return

        try:
            self.setStyleSheet(styles_path.read_text(encoding="utf-8"))
        except OSError as error:
            print(f"Не удалось загрузить стили: {error}")

    def set_controls_downloading(self, downloading: bool) -> None:
        can_change_settings = not downloading and not self.is_paused

        self.url_input.setEnabled(can_change_settings)
        self.info_button.setEnabled(can_change_settings)

        self.save_folder_input.setEnabled(can_change_settings)
        self.folder_button.setEnabled(can_change_settings)

        self.quality_box.setEnabled(
            can_change_settings and self.quality_box.count() > 1
        )

        self.download_button.setEnabled(
            can_change_settings
            and self.quality_box.currentText() != "Выберите качество"
        )

        self.stop_button.setEnabled(downloading or self.is_paused)
        self.cancel_button.setEnabled(downloading or self.is_paused)

        if self.is_paused:
            self.stop_button.setText("Продолжить")
        else:
            self.stop_button.setText("Стоп")

    def _connect_thread(self) -> None:
        self.download_thread.progress_signal.connect(self.download_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.cancelled_signal.connect(self.download_cancelled)
        self.download_thread.error_signal.connect(self.download_error)

    def choose_download_folder(self) -> None:
        current_dir = str(self.last_download_dir.resolve())

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для сохранения видео",
            current_dir,
        )

        if not selected_dir:
            return

        self.last_download_dir = Path(selected_dir)
        self.save_folder_input.setText(
            str(self.last_download_dir.resolve())
        )

        self.status_label.setText(
            "Папка для сохранения выбрана:\n"
            f"{self.last_download_dir}"
        )

    def load_video_info(self) -> None:
        url = self.url_input.text().strip()

        if not url:
            self.status_label.setText("Вставьте ссылку на видео.")
            return

        self.status_label.setText("Получаю информацию о видео...")
        self.info_button.setEnabled(False)

        try:
            info = get_video_info(url)
            formats = info.get("formats", [])

            allowed_qualities = [2160, 1440, 1080, 720, 480, 360]
            qualities = []

            for fmt in formats:
                height = fmt.get("height")

                if height in allowed_qualities:
                    quality = f"{height}p"

                    if quality not in qualities:
                        qualities.append(quality)

            qualities.sort(
                key=lambda value: int(value.removesuffix("p")),
                reverse=True,
            )

            self.quality_box.clear()
            self.quality_box.addItem("Выберите качество")
            self.quality_box.addItems(qualities)

            self.quality_box.setEnabled(bool(qualities))
            self.download_button.setEnabled(bool(qualities))

            title = info.get("title") or "Без названия"
            uploader = info.get("uploader") or "Неизвестный автор"

            if qualities:
                qualities_text = ", ".join(qualities)
            else:
                qualities_text = "Подходящие качества не найдены"

            self.status_label.setText(
                f"Название: {title}\n"
                f"Автор: {uploader}\n\n"
                f"Доступные качества: {qualities_text}"
            )

        except Exception as error:
            self.quality_box.clear()
            self.quality_box.addItem("Выберите качество")
            self.quality_box.setEnabled(False)
            self.download_button.setEnabled(False)

            self.status_label.setText(
                f"Ошибка получения информации:\n{error}"
            )

        finally:
            if not self.is_paused:
                self.info_button.setEnabled(True)

    def start_download(self) -> None:
        url = self.url_input.text().strip()
        quality = self.quality_box.currentText()

        if not url:
            self.status_label.setText("Вставьте ссылку на видео.")
            return

        if quality == "Выберите качество":
            self.status_label.setText("Выберите качество видео.")
            return

        if self.download_thread and self.download_thread.isRunning():
            return

        self.last_url = url
        self.last_quality = quality
        self.is_paused = False
        self.created_files = set()

        self.progress_bar.setValue(0)
        self.status_label.setText(
            "Скачивание начинается...\n"
            f"Папка: {self.last_download_dir}"
        )

        self.download_thread = DownloadThread(
            url=self.last_url,
            quality=self.last_quality,
            download_dir=self.last_download_dir,
            resume=False,
        )
        self._connect_thread()

        self.set_controls_downloading(True)
        self.download_thread.start()

    def toggle_stop_resume(self) -> None:
        if not self.download_thread:
            return

        if not self.is_paused:
            if self.download_thread.isRunning():
                self.download_thread.cancel()

                self.is_paused = True
                self.status_label.setText(
                    "Останавливаю загрузку: жду завершения текущего фрагмента..."
                )

                self.stop_button.setEnabled(False)
                self.cancel_button.setEnabled(False)

        else:
            if self.download_thread.isRunning():
                return

            if not self.last_url or not self.last_quality:
                self.status_label.setText(
                    "Не удалось продолжить: параметры загрузки не найдены."
                )
                self.is_paused = False
                self.set_controls_downloading(False)
                return

            self.is_paused = False
            self.status_label.setText(
                "Возобновление загрузки...\n"
                f"Папка: {self.last_download_dir}"
            )

            self.download_thread = DownloadThread(
                url=self.last_url,
                quality=self.last_quality,
                download_dir=self.last_download_dir,
                resume=True,
            )
            self._connect_thread()

            self.set_controls_downloading(True)
            self.download_thread.start()

    def cancel_download(self) -> None:
        if self.is_paused and (
            not self.download_thread
            or not self.download_thread.isRunning()
        ):
            remove_partial_files(self.created_files)

            self.created_files = set()
            self.is_paused = False

            self.progress_bar.setValue(0)
            self.status_label.setText(
                "Скачивание отменено. Недокачанные файлы удалены."
            )
            self.set_controls_downloading(False)
            return

        if self.download_thread and self.download_thread.isRunning():
            self.is_paused = False
            self.download_thread.cancel()

            self.status_label.setText(
                "Отмена запрошена: жду завершения текущего фрагмента..."
            )

            self.cancel_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def download_progress(
        self,
        percent: float,
        speed_text: str,
        eta_text: str,
    ) -> None:
        value = max(0, min(100, int(percent)))

        self.progress_bar.setValue(value)
        self.status_label.setText(
            f"Скачивание: {percent:.1f}%\n"
            f"Скорость: {speed_text}\n"
            f"Осталось: {eta_text}"
        )

    def download_finished(self) -> None:
        self.progress_bar.setValue(100)
        self.status_label.setText(
            "Видео скачано.\n"
            f"Сохранено в: {self.last_download_dir}"
        )

        self.is_paused = False
        self.created_files = set()

        self.set_controls_downloading(False)

    def download_cancelled(self, created_files: set[str]) -> None:
        self.created_files = created_files

        if self.is_paused:
            self.status_label.setText(
                "Загрузка приостановлена.\n"
                "Нажмите «Продолжить», чтобы возобновить."
            )
            self.set_controls_downloading(False)
            return

        remove_partial_files(created_files)

        self.created_files = set()
        self.progress_bar.setValue(0)
        self.status_label.setText(
            "Скачивание отменено. Недокачанные файлы удалены."
        )
        self.set_controls_downloading(False)

    def download_error(
        self,
        error: str,
        created_files: set[str],
    ) -> None:
        self.created_files = created_files
        self.is_paused = False

        self.status_label.setText(f"Ошибка скачивания:\n{error}")
        self.set_controls_downloading(False)