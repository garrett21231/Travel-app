"""Environment smoke checks; these do not implement or test Travel-app."""
import sqlite3


def test_sqlite_persistence_and_rollback(tmp_path):
    database = tmp_path / "environment-check.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO sample (value) VALUES (?)", ("saved locally",))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("saved locally",)
        connection.execute("UPDATE sample SET value = ?", ("edited locally",))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("edited locally",)
        connection.execute("DELETE FROM sample")
        connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (1,)
        connection.execute("DELETE FROM sample")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone() == (0,)


def test_kivy_render_and_button_event(tmp_path):
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label

    Window.size = (390, 844)
    completed = []

    class EnvironmentCheck(App):
        def build(self):
            layout = BoxLayout(orientation="vertical")
            self.label = Label(text="Environment check")
            self.button = Button(text="Check interaction")
            self.button.bind(on_release=lambda _: setattr(self.label, "text", "Interaction works"))
            layout.add_widget(self.label)
            layout.add_widget(self.button)
            return layout

        def on_start(self):
            Clock.schedule_once(self.check_button, 0.3)

        def check_button(self, _):
            self.button.dispatch("on_release")
            assert self.label.text == "Interaction works"
            Clock.schedule_once(self.check_render, 0.3)

        def check_render(self, _):
            image = self.root.export_as_image()
            assert image.texture.size == (390, 844)
            pixels = image.texture.pixels
            assert len(pixels) == 390 * 844 * 4
            assert len(set(pixels[index:index + 4] for index in range(0, len(pixels), 4))) > 4
            image.save(str(tmp_path / "kivy-environment.png"))
            assert (tmp_path / "kivy-environment.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            completed.append(True)
            self.stop()

    EnvironmentCheck().run()
    assert completed == [True]