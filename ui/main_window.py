from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
)

from core.avatars import avatar_file, remove_avatar
from core.settings import (
    delete_profile_files,
    display_name,
    find_profile,
    new_profile,
    profile_out_dir,
    profile_session,
    save_settings,
)
from ui.login_view import LoginView
from ui.main_view import MainView
from ui.profiles_view import ProfilesView
from ui.registration_view import RegistrationView
from ui.settings_dialog import SettingsDialog
from ui.theme import apply_theme
from ui.worker import TelegramWorker

APP_TITLE = "Amir Video Saver"
NAME_LIMIT = 30
OWNER_MISMATCH = (
    "Этот профиль привязан к другому аккаунту Telegram, поэтому вход отклонён. "
    "Войдите тем аккаунтом, с которого создан профиль, или создайте свой профиль со своими ключами."
)


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.profile = None  # открытый профиль
        self.pending = None  # новый профиль: сохраняется, когда Telegram принял ключи
        self.account_name = ""  # имя аккаунта в Telegram
        self.downloading = False  # идёт скачивание или оценка объёма

        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 700)
        self.setMinimumSize(900, 600)

        self.worker = TelegramWorker()
        self.registration = RegistrationView()
        self.profiles = ProfilesView()
        self.login = LoginView()
        self.main = MainView()

        self.stack = QStackedWidget()
        for page in (self.registration, self.profiles, self.login, self.main):
            self.stack.addWidget(page)
        self.setCentralWidget(self.stack)

        # сигналы потока Telegram -> окно
        self.worker.authorized.connect(self.on_authorized)
        self.worker.unauthorized.connect(self.on_unauthorized)
        self.worker.keys_rejected.connect(self.on_keys_rejected)
        self.worker.qr_ready.connect(self.on_qr_ready)
        self.worker.password_needed.connect(self.on_password_needed)
        self.worker.login_failed.connect(self.on_login_failed)
        self.worker.avatar_loaded.connect(self.on_avatar_loaded)
        self.worker.channels_loaded.connect(self.main.set_channels)
        self.worker.counts_loaded.connect(self.main.set_counts)
        self.worker.counts_failed.connect(self.main.set_counts_failed)
        self.worker.download_progress.connect(self.main.panel.set_progress)
        self.worker.download_log.connect(self.main.panel.add_log)
        self.worker.download_finished.connect(self.on_download_finished)
        self.worker.logged_out.connect(self.on_logged_out)
        self.worker.failed.connect(self.on_failed)

        # действия пользователя
        self.registration.submitted.connect(self.on_registered)
        self.registration.back.connect(self.show_profiles)
        self.profiles.opened.connect(self.on_open_profile)
        self.profiles.deleted.connect(self.on_delete_profile)
        self.profiles.added.connect(lambda: self.show_registration())
        self.login.retry.connect(self.on_retry)
        self.login.show_profiles.connect(self.show_profiles)
        self.main.channel_selected.connect(self.on_channel_selected)
        self.main.settings_requested.connect(self.open_settings)
        self.main.panel.start_requested.connect(self.on_start_download)
        self.main.panel.stop_requested.connect(self.worker.stop_download)
        self.main.panel.folder_changed.connect(self.on_folder_changed)
        self.main.refresh_requested.connect(self.on_refresh_channels)

        self.worker.channel_avatar_loaded.connect(self.main.set_channel_avatar)

        self.start()

    # ---------- вспомогательное ----------

    def confirm(self, text, info="", yes_text="Да"):
        box = QMessageBox(self)
        box.setWindowTitle(APP_TITLE)
        box.setText(text)
        if info:
            box.setInformativeText(info)
        yes = box.addButton(yes_text, QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def refuse_while_downloading(self):
        """True, если идёт скачивание: профиль менять и выходить из аккаунта сейчас нельзя."""
        if self.downloading:
            QMessageBox.information(self, APP_TITLE, "Сначала остановите скачивание.")
        return self.downloading

    # ---------- запуск ----------

    def start(self):
        profiles = self.settings["profiles"]
        if not profiles:
            self.show_registration()
        elif len(profiles) == 1:
            self.open_profile(profiles[0])
        else:
            self.show_profiles()

    def on_login_screen(self):
        """Сигналы входа, пришедшие после ухода с экрана входа, игнорируем."""
        return self.stack.currentWidget() is self.login

    # ---------- регистрация и профили ----------

    def show_registration(self, error="", values=None):
        self.registration.clear()
        if values:
            self.registration.set_values(*values)
        if error:
            self.registration.show_error(error)
        self.registration.set_back_visible(bool(self.settings["profiles"]))
        self.stack.setCurrentWidget(self.registration)

    @Slot()
    def show_profiles(self):
        self.worker.cancel_login()
        self.pending = None
        if not self.settings["profiles"]:
            self.show_registration()
            return
        self.profiles.set_profiles(self.settings["profiles"])
        self.stack.setCurrentWidget(self.profiles)

    @Slot()
    def on_refresh_channels(self):
        if self.downloading:
            return
        self.main.set_refreshing(True)
        self.worker.load_channels()  # перезагрузит список
        # если канал выбран — обновим и счётчики
        info = self.main.current_info()
        if info:
            self.worker.load_counts(info.id)

    @Slot(str, str)
    def on_registered(self, api_id, api_hash):
        # один ключ — один профиль: те же ключи в двух профилях означали бы общий лимит
        for existing in self.settings["profiles"]:
            if existing["api_id"] == api_id:
                self.show_registration(
                    error=f"Эти ключи уже используются в профиле «{display_name(existing)}». "
                    "Один ключ — один профиль.",
                    values=(api_id, api_hash),
                )
                return
        self.pending = new_profile(api_id, api_hash)
        self.open_profile(self.pending)

    def open_profile(self, profile):
        self.profile = profile
        self.login.set_profile(display_name(profile), bool(profile.get("tg_user_id")))
        self.login.show_connecting()
        self.stack.setCurrentWidget(self.login)
        self.worker.start(
            profile["api_id"], profile["api_hash"], profile_session(profile)
        )

    @Slot(str)
    def on_open_profile(self, profile_id):
        profile = find_profile(self.settings, profile_id)
        if profile:
            self.pending = None
            self.open_profile(profile)

    @Slot(str)
    def on_delete_profile(self, profile_id):
        profile = find_profile(self.settings, profile_id)
        if not profile:
            return

        if not self.confirm(
            f"Удалить профиль «{display_name(profile)}»?",
            "Ключи и вход на этом компьютере будут удалены. Скачанные файлы останутся. "
            "Сеанс в самом Telegram завершите вручную: Настройки → Устройства.",
            yes_text="Удалить",
        ):
            return

        if self.profile and self.profile["id"] == profile_id:
            self.worker.release()  # освобождаем файл входа, иначе Windows не даст его удалить
            self.profile = None
            self.main.set_channels([])
        delete_profile_files(profile)
        remove_avatar(
            profile_id
        )  # сохранённое фото аккаунта удаляется вместе с профилем
        self.settings["profiles"] = [
            p for p in self.settings["profiles"] if p["id"] != profile_id
        ]
        save_settings(self.settings)

        if self.settings["profiles"]:
            self.profiles.set_profiles(self.settings["profiles"])
        else:
            self.show_registration()

    def commit_profile(self):
        """Telegram принял ключи: только теперь профиль попадает в настройки."""
        if self.pending:
            self.settings["profiles"].append(self.pending)
            self.pending = None
            save_settings(self.settings)

    # ---------- вход ----------

    @Slot()
    def on_retry(self):
        if self.profile:
            self.open_profile(self.profile)
        else:
            self.start()

    @Slot(str)
    def on_keys_rejected(self, text):
        if not self.on_login_screen():
            return
        if self.pending:
            # опечатка в только что введённых ключах: возвращаем введённое для исправления
            values = (self.pending["api_id"], self.pending["api_hash"])
            self.pending = None
            self.show_registration(error=text, values=values)
        else:
            self.login.show_error(f"{text} Удалите профиль и создайте его заново.")

    @Slot()
    def on_unauthorized(self):
        if self.on_login_screen():
            self.worker.begin_qr_login()

    @Slot(str, int)
    def on_qr_ready(self, url, lifetime):
        if not self.on_login_screen():
            return
        self.commit_profile()  # QR выдан, значит Telegram принял ключи
        self.login.show_qr(url, lifetime)

    @Slot()
    def on_password_needed(self):
        text, ok = QInputDialog.getText(
            self,
            APP_TITLE,
            "Включена двухфакторная защита.\nВведите облачный пароль Telegram:",
            QLineEdit.EchoMode.Password,
        )
        self.worker.submit_password(text if ok else "")

    @Slot(str)
    def on_login_failed(self, text):
        if self.on_login_screen():
            self.login.show_error(text)

    @Slot(str, object)
    def on_authorized(self, name, tg_id):
        if not self.on_login_screen() or not self.profile:
            return

        profile = self.profile
        owner = profile.get("tg_user_id")
        if owner is not None and owner != tg_id:
            # в профиль пытается войти другой аккаунт: отклоняем и завершаем его вход в приложении.
            # Фото чужого аккаунта не загружается, поэтому оно не может заменить фото владельца
            self.worker.reject_account()
            self.login.show_error(OWNER_MISMATCH)
            return

        self.commit_profile()
        if owner is None:
            profile["tg_user_id"] = tg_id  # профиль привязан к этому аккаунту навсегда

        if not profile.get("name"):
            text, ok = QInputDialog.getText(
                self,
                APP_TITLE,
                "Как назвать этот профиль?\nИмя увидите только вы.",
                QLineEdit.EchoMode.Normal,
                name[:NAME_LIMIT],
            )
            chosen = text.strip() if ok else ""
            profile["name"] = (chosen or name)[:NAME_LIMIT]

        save_settings(self.settings)
        self.account_name = name
        # сначала показываем сохранённое фото (если есть), свежее подгрузится следом
        self.main.set_user(display_name(profile), avatar_file(profile["id"]))
        self.stack.setCurrentWidget(self.main)
        self.worker.load_channels()
        self.worker.load_avatar(profile["id"])

    @Slot(str, str)
    def on_avatar_loaded(self, profile_id, path):
        """Фото аккаунта скачано: обновляем его внизу слева и в списке профилей."""
        if self.profile and self.profile["id"] == profile_id:
            self.main.set_user_avatar(path or None)
        if self.stack.currentWidget() is self.profiles:
            self.profiles.set_profiles(self.settings["profiles"])

    # ---------- главный экран ----------

    @Slot(object)
    def on_channel_selected(self, info):
        self.main.panel.set_channel(
            info,
            profile_out_dir(self.settings, self.profile),
            self.settings["timezone"],
        )
        self.worker.load_counts(info.id)

    @Slot(str)
    def on_failed(self, text):
        QMessageBox.warning(self, APP_TITLE, text)

    # ---------- скачивание ----------

    @Slot(object)
    def on_start_download(self, opts):
        info = self.main.current_info()
        if info is None:
            return
        self.downloading = True
        self.main.set_locked(True)
        self.worker.start_download(info.id, opts)

    @Slot(str, bool, object)
    def on_download_finished(self, status, dry_run, result):
        self.downloading = False
        self.main.set_locked(False)
        self.main.panel.finish(status, dry_run, result)

    @Slot(str)
    def on_folder_changed(self, path):
        if self.profile:
            self.profile["out_dir"] = path
            save_settings(self.settings)

    # ---------- настройки ----------

    @Slot()
    def open_settings(self):
        account = f"Профиль: {display_name(self.profile)}\nАккаунт Telegram: {self.account_name}"
        dialog = SettingsDialog(self, account, self.settings["theme"])
        dialog.theme_changed.connect(self.on_theme)
        dialog.switch_requested.connect(self.on_switch_profile)
        dialog.logout_requested.connect(self.on_logout_requested)
        dialog.exec()

    @Slot(str)
    def on_theme(self, name):
        self.settings["theme"] = name
        apply_theme(QApplication.instance(), name)
        save_settings(self.settings)
        self.main.refresh()
        self.login.qr.update()

    @Slot()
    def on_switch_profile(self):
        if self.refuse_while_downloading():
            return
        self.main.set_channels([])
        self.show_profiles()

    @Slot()
    def on_logout_requested(self):
        if self.refuse_while_downloading():
            return
        self.worker.logout()

    @Slot()
    def on_logged_out(self):
        self.main.set_channels([])
        self.show_profiles()

    def closeEvent(self, event):
        if self.downloading and not self.confirm(
            "Скачивание ещё идёт.",
            "Остановить его и закрыть программу? Уже скачанное сохранится.",
            yes_text="Закрыть",
        ):
            event.ignore()
            return
        self.worker.shutdown()
        event.accept()
