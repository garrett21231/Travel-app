"""Reusable labels, cards, buttons, and outlined navigation containers."""
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from trip_ui.theme import BLACK, WHITE, BLUE, ASSETS


def text(value, size=16, color=WHITE, height=28, bold=False):
    """Create a left-aligned label that follows its assigned width and height.

    Single-line values shorten to fit. For notes or later-assigned multiline
    text, set shorten=False and bind height to texture_size when needed.
    """
    widget = Label(text=value, font_size=sp(size), color=color, bold=bold,
                   size_hint_y=None, height=dp(height), halign='left', valign='middle',
                   shorten='\n' not in value, shorten_from='right')
    widget.bind(size=lambda w, _: setattr(w, 'text_size', w.size))
    return widget



def wrapped_text(value, size=14, color=WHITE, height=24, bold=False):
    """Grow a label to fit its content at the current width, including phones."""
    widget = Label(text=value, font_size=sp(size), color=color, bold=bold,
                   size_hint_y=None, height=dp(height), halign='left', valign='middle')
    widget.bind(width=lambda w, width: setattr(w, 'text_size', (width, None)),
                texture_size=lambda w, size: setattr(w, 'height', max(dp(height), size[1])))
    return widget



def content_panel():
    """Size a card from its children so wrapped labels never overflow it."""
    panel = Panel(0)
    panel.bind(minimum_height=panel.setter('height'))
    return panel



class Panel(BoxLayout):
    """Reusable vertical card with padding, spacing, and a rounded background."""
    def __init__(self, height, color=WHITE, **kwargs):
        """Create a fixed-height card; height must fit children plus padding/gaps."""
        super().__init__(orientation='vertical', padding=dp(14), spacing=dp(8),
                         size_hint_y=None, height=dp(height), **kwargs)
        with self.canvas.before:
            Color(*color)
            # Corner radius of boxes
            self.shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)]) 
        self.bind(pos=self.update, size=self.update)

    def update(self, *_):
        """Keep the canvas background aligned when the card moves or resizes."""
        self.shape.pos, self.shape.size = self.pos, self.size



class Action(Button):
    """Text action button; primary=True adds the blue rounded fill."""
    def __init__(self, caption, callback, primary=False, color=None, **kwargs):
        """Call a zero-argument callback on release; forward extra Kivy options."""
        super().__init__(text=caption, font_size=kwargs.pop('font_size', sp(16)), bold=True,
                         color=color or (BLACK if primary else BLUE),
                         background_normal='', background_down='', background_color=(0, 0, 0, 0),
                         size_hint_y=None, height=dp(44), **kwargs)
        if primary:
            with self.canvas.before:
                self.fill = Color(*BLUE)
                self.shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(7)])
            self.bind(pos=self.update, size=self.update, state=self.update)
        self.bind(on_release=lambda _: callback())

    def update(self, *_):
        """Resize the primary fill and dim it while the button is pressed."""
        self.shape.pos, self.shape.size = self.pos, self.size
        self.fill.rgba = (*BLUE[:3], .7 if self.state == 'down' else 1)



class OutlineRow(BoxLayout):
    """Outlined horizontal container used for navigation rows and trip tabs."""
    def __init__(self, **kwargs):
        """Create the outline and connect it to layout position/size changes."""
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*WHITE)
            self.outline = Line(rounded_rectangle=(*self.pos, *self.size, dp(14)), width=1)
        self.bind(pos=self.update, size=self.update)

    def update(self, *_):
        """Redraw the outline to follow the row's current bounds."""
        self.outline.rounded_rectangle = (*self.pos, *self.size, dp(14))



class IconAction(Button):
    """A 44-dp touch target displaying a bundled icon at its original size."""
    def __init__(self, asset, callback):
        """Load asset relative to ASSETS and call callback when released."""
        super().__init__(background_normal='', background_down='', background_color=(0, 0, 0, 0),
                         size_hint=(None, None), size=(dp(44), dp(48))) # Length and height from edges of bounds.
        self.icon = Image(source=str(ASSETS / asset), size_hint=(None, None))
        self.add_widget(self.icon)
        self.bind(pos=self.update, size=self.update, on_release=lambda _: callback())
        self.update()

    def update(self, *_):
        """Center the image within its larger button touch target."""
        self.icon.size = self.icon.texture_size
        self.icon.center = self.center

