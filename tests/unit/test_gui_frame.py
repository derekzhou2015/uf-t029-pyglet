"""Unit tests for pyglet.gui.frame spatial hash bookkeeping.

These tests use a stub window and stub widgets so they can run
without a GL context.
"""

import pytest

from pyglet.gui.frame import Frame, MovableFrame
from pyglet.gui.widgets import WidgetBase


class DummyWindow:
    """Minimal stand-in for a pyglet Window."""

    def __init__(self):
        self.handlers = []

    def push_handlers(self, *handlers):
        self.handlers.extend(handlers)

    def remove_handlers(self, *handlers):
        for handler in handlers:
            self.handlers.remove(handler)


class DummyWidget(WidgetBase):
    """A WidgetBase subclass that needs no graphics resources."""

    def __init__(self, x, y, width=20, height=20):
        super().__init__(x, y, width, height)
        self.mouse_press_calls = []

    def _update_position(self):
        pass

    def on_mouse_press(self, x, y, buttons, modifiers):
        self.mouse_press_calls.append((x, y))


@pytest.fixture
def window():
    return DummyWindow()


@pytest.fixture
def frame(window):
    return Frame(window)


def press_at(frame, x, y):
    frame.on_mouse_press(x, y, buttons=1, modifiers=0)
    frame.on_mouse_release(x, y, buttons=1, modifiers=0)


def test_add_and_remove_widget(frame):
    """Existing add/remove path: widget is hashed in, then fully removed."""
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)

    cell = frame._hash(15, 15)
    assert widget in frame._cells[cell]

    frame.remove_widget(widget)
    assert widget not in frame._cells[cell]
    # A removed widget must not receive events:
    press_at(frame, 15, 15)
    assert widget.mouse_press_calls == []


def test_remove_widget_is_idempotent(frame):
    """Removing a widget that is not tracked must not raise."""
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)
    frame.remove_widget(widget)
    frame.remove_widget(widget)  # should be a no-op, not an exception


def test_move_widget_to_empty_area(frame):
    """Moving a widget to an unoccupied area updates the spatial hash."""
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)
    old_cell = frame._hash(15, 15)

    # Move far away, into cells that do not exist yet:
    widget.position = 500, 500

    assert widget not in frame._cells[old_cell]
    assert widget in frame._cells[frame._hash(505, 505)]

    # Old position must no longer hit; new position must hit:
    press_at(frame, 15, 15)
    assert widget.mouse_press_calls == []
    press_at(frame, 505, 505)
    assert widget.mouse_press_calls == [(505, 505)]


def test_move_widget_onto_occupied_area(frame):
    """Moving a widget onto another widget's cells must not corrupt the hash."""
    widget_a = DummyWidget(10, 10)
    widget_b = DummyWidget(300, 300)
    frame.add_widget(widget_a)
    frame.add_widget(widget_b)

    widget_a.position = 310, 310

    cell = frame._hash(315, 315)
    assert widget_a in frame._cells[cell]
    assert widget_b in frame._cells[cell]

    # Both widgets receive events at the shared location:
    press_at(frame, 315, 315)
    assert widget_a.mouse_press_calls == [(315, 315)]
    assert widget_b.mouse_press_calls == [(315, 315)]

    # widget_a's old position is clean, widget_b is unaffected there:
    press_at(frame, 15, 15)
    assert widget_a.mouse_press_calls == [(315, 315)]


def test_move_widget_via_x_and_y_setters(frame):
    """Repositioning through the x/y properties also re-hashes."""
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)

    widget.x = 200
    widget.y = 200

    assert widget not in frame._cells[frame._hash(15, 15)]
    assert widget in frame._cells[frame._hash(205, 205)]
    press_at(frame, 205, 205)
    assert widget.mouse_press_calls == [(205, 205)]


def test_move_does_not_affect_other_widgets(frame):
    """Other widgets in the frame stay registered after a move."""
    moved = DummyWidget(10, 10)
    bystander = DummyWidget(100, 100)
    frame.add_widget(moved)
    frame.add_widget(bystander)

    moved.position = 500, 500

    assert bystander in frame._cells[frame._hash(105, 105)]
    press_at(frame, 105, 105)
    assert bystander.mouse_press_calls == [(105, 105)]


def test_remove_after_move(frame):
    """A widget can be cleanly removed after being moved."""
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)
    widget.position = 500, 500
    frame.remove_widget(widget)

    assert not any(widget in cell for cell in frame._cells.values())
    press_at(frame, 505, 505)
    assert widget.mouse_press_calls == []


def test_movable_frame_drag_and_drop(window):
    """Full MovableFrame drag: press with modifier, drag, release."""
    frame = MovableFrame(window, modifier=1)
    widget = DummyWidget(10, 10)
    frame.add_widget(widget)

    # Grab the widget with the modifier held:
    frame.on_mouse_press(15, 15, buttons=1, modifiers=1)
    assert widget in frame._moving_widgets
    # While moving, the widget is out of the spatial hash:
    assert not any(widget in cell for cell in frame._cells.values())

    # Drag to a new location and drop:
    frame.on_mouse_drag(115, 115, dx=100, dy=100, buttons=1, modifiers=1)
    assert widget.position == (110, 110)
    frame.on_mouse_release(115, 115, buttons=1, modifiers=0)

    assert frame._moving_widgets == set()
    assert widget in frame._cells[frame._hash(115, 115)]
    # The cell the widget was grabbed from must no longer contain it:
    assert widget not in frame._cells[frame._hash(15, 15)]

    # Hit area follows the drop position:
    press_at(frame, 15, 15)
    assert widget.mouse_press_calls == []
    press_at(frame, 115, 115)
    assert widget.mouse_press_calls == [(115, 115)]
