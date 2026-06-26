try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QTreeView
except ImportError:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QTreeView

import mobase


class MO2StartupScroll(mobase.IPlugin):
    PLUGIN_NAME = "Startup Scroll"
    VALID_POSITIONS = ("bottom", "top", "disabled")

    def __init__(self):
        super().__init__()
        self._organizer = None
        self._main_window = None
        self._startup_attempt = 0
        self._startup_retry_count = 0
        self._startup_retry_interval_ms = 0
        self._startup_popup_wait_timeout_ms = 0
        self._startup_popup_wait_elapsed_ms = 0

    def name(self):
        return self.PLUGIN_NAME

    def localizedName(self):
        return self.name()

    def displayName(self):
        return self.name()

    def author(self):
        return "Keenan Selbee"

    def description(self):
        return "Scrolls the mod and plugin panes to configured startup positions."

    def version(self):
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)

    def isActive(self):
        return True

    def settings(self):
        return [
            mobase.PluginSetting(
                "mod_list_position",
                "Startup position for the left mod list: bottom, top, or disabled.",
                "bottom",
            ),
            mobase.PluginSetting(
                "plugin_list_position",
                "Startup position for the right plugin list: bottom, top, or disabled.",
                "bottom",
            ),
            mobase.PluginSetting(
                "startup_delay_ms",
                "Delay before the first startup scroll attempt.",
                750,
            ),
            mobase.PluginSetting(
                "retry_count",
                "Number of startup scroll attempts.",
                4,
            ),
            mobase.PluginSetting(
                "retry_interval_ms",
                "Delay between startup scroll attempts.",
                750,
            ),
            mobase.PluginSetting(
                "popup_wait_timeout_ms",
                "Maximum time to wait for startup popups before scrolling anyway.",
                120000,
            ),
            mobase.PluginSetting(
                "debug_logging",
                "Print debug messages to the MO2 log.",
                False,
            ),
        ]

    def init(self, organizer):
        self._organizer = organizer
        organizer.onUserInterfaceInitialized(self._on_user_interface_initialized)
        return True

    def _on_user_interface_initialized(self, main_window):
        self._main_window = main_window

        startup_delay = self._int_setting("startup_delay_ms", 750, 0, 60000)
        self._startup_attempt = 0
        self._startup_retry_count = self._int_setting("retry_count", 4, 1, 20)
        self._startup_retry_interval_ms = self._int_setting("retry_interval_ms", 750, 0, 60000)
        self._startup_popup_wait_timeout_ms = self._int_setting(
            "popup_wait_timeout_ms",
            120000,
            0,
            600000,
        )
        self._startup_popup_wait_elapsed_ms = 0

        QTimer.singleShot(startup_delay, self._apply_startup_scroll)

    def _apply_startup_scroll(self):
        if self._startup_popup_is_active() and self._can_wait_for_startup_popup():
            delay = self._popup_poll_interval_ms()
            self._startup_popup_wait_elapsed_ms += delay
            self._log(
                "startup popup active; deferring scroll for {0} ms ({1}/{2} ms)".format(
                    delay,
                    self._startup_popup_wait_elapsed_ms,
                    self._startup_popup_wait_timeout_ms,
                )
            )
            QTimer.singleShot(delay, self._apply_startup_scroll)
            return

        self._startup_attempt += 1
        mod_position = self._position_setting("mod_list_position", "bottom")
        plugin_position = self._position_setting("plugin_list_position", "bottom")

        mod_done = self._position_view("modList", mod_position)
        plugin_done = self._position_view("espList", plugin_position)

        self._log(
            "attempt {0}: modList={1}, espList={2}".format(
                self._startup_attempt,
                "skipped" if mod_position == "disabled" else mod_done,
                "skipped" if plugin_position == "disabled" else plugin_done,
            )
        )

        if self._startup_attempt < self._startup_retry_count:
            QTimer.singleShot(self._startup_retry_interval_ms, self._apply_startup_scroll)

    def _startup_popup_is_active(self):
        try:
            return QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None
        except Exception:
            return False

    def _can_wait_for_startup_popup(self):
        if self._startup_popup_wait_timeout_ms <= 0:
            return False

        return self._startup_popup_wait_elapsed_ms < self._startup_popup_wait_timeout_ms

    def _popup_poll_interval_ms(self):
        if self._startup_retry_interval_ms > 0:
            return min(
                self._startup_retry_interval_ms,
                self._startup_popup_wait_timeout_ms - self._startup_popup_wait_elapsed_ms,
            )

        return min(250, self._startup_popup_wait_timeout_ms - self._startup_popup_wait_elapsed_ms)

    def _position_view(self, object_name, position):
        if position == "disabled":
            return True

        view = self._find_tree_view(object_name)
        if view is None:
            return False

        scroll_bar = view.verticalScrollBar()
        if scroll_bar is None:
            return False

        if position == "top":
            view.scrollToTop()
            scroll_bar.setValue(scroll_bar.minimum())
        else:
            view.scrollToBottom()
            scroll_bar.setValue(scroll_bar.maximum())

        return True

    def _find_tree_view(self, object_name):
        if self._main_window is not None:
            view = self._main_window.findChild(QTreeView, object_name)
            if view is not None:
                return view

        for widget in QApplication.allWidgets():
            if isinstance(widget, QTreeView) and widget.objectName() == object_name:
                return widget

        return None

    def _position_setting(self, key, default):
        value = self._string_setting(key, default).strip().lower()
        if value in self.VALID_POSITIONS:
            return value

        self._log('invalid setting {0}="{1}", using {2}'.format(key, value, default))
        return default

    def _setting_value(self, key, default):
        try:
            value = self._organizer.pluginSetting(self.name(), key)
            if value is not None:
                return value
        except Exception:
            pass

        return default

    def _string_setting(self, key, default):
        return str(self._setting_value(key, default))

    def _int_setting(self, key, default, minimum, maximum):
        value = self._setting_value(key, default)
        try:
            value = int(value)
        except Exception:
            value = default

        if value < minimum:
            return minimum
        if value > maximum:
            return maximum

        return value

    def _bool_setting(self, key, default):
        value = self._setting_value(key, default)
        if isinstance(value, bool):
            return value

        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False

        return default

    def _log(self, message):
        if self._bool_setting("debug_logging", False):
            print("[Startup Scroll] {0}".format(message))


def createPlugin():
    return MO2StartupScroll()
