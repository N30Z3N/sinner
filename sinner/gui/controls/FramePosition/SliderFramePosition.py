from tkinter import Label, StringVar, Frame, X, TOP, NW, DISABLED, NORMAL, IntVar, Misc
from typing import Union, Callable, Any, Dict

from customtkinter import CTkSlider

from sinner.gui.controls.FramePosition.BaseFramePosition import BaseFramePosition


class SliderFramePosition(BaseFramePosition, CTkSlider):
    _container: Frame
    _position_label: Label
    _current_position: StringVar
    _cmd: Union[Callable[[float], None], None] = None

    def __init__(self, master: Misc | None, **kwargs):  # type: ignore[no-untyped-def]
        self._container = Frame(master, borderwidth=2)
        self._current_position = StringVar()
        self._position_label = Label(master)
        CTkSlider.__init__(self, self._container, **kwargs)
        self._position_label.configure(textvariable=self._current_position)
        self.update_position()

    def pack(self, **kwargs: Dict[str, Any]) -> Any:
        self._container.pack(fill=X)
        result = CTkSlider.pack(self, **kwargs)
        self._position_label.pack(anchor=NW, side=TOP, expand=False, fill=X, after=self)
        return result

    def pack_forget(self) -> Any:
        self._container.pack_forget()

    def _clicked(self, event: Any | None = None) -> None:
        CTkSlider._clicked(self, event)
        self.update_position()

    def set(self, output_value: int, from_variable_callback: bool = False) -> None:
        if self._from_ < self._to:
            if output_value > self._to:
                output_value = self._to
            elif output_value < self._from_:
                output_value = self._from_
        else:
            if output_value < self._to:
                output_value = self._to
            elif output_value > self._from_:
                output_value = self._from_

        self._output_value = self._round_to_step_size(output_value)
        try:
            self._value = (self._output_value - self._from_) / (self._to - self._from_)
        except ZeroDivisionError:
            self._value = 1

        self._draw()

        if self._variable is not None and not from_variable_callback:
            self._variable_callback_blocked = True
            self._variable.set(round(self._output_value) if isinstance(self._variable, IntVar) else self._output_value)
            self._variable_callback_blocked = False
        self.update_position()

    def update_position(self) -> None:
        if self._position_label:
            self._current_position.set(f'{self.position}/{self._to}')

    @property
    def to(self) -> int:
        return self._to

    @to.setter
    def to(self, value: int) -> None:
        if value > self.position:
            self.position = value
        self.configure(to=value)

    @property
    def position(self) -> int:
        return int(self.get())

    @position.setter
    def position(self, value: int) -> None:
        self.set(value)

    @property
    def container(self) -> Frame:
        return self._container

    def disable(self) -> None:
        CTkSlider.configure(self, True, state=DISABLED)

    def enable(self) -> None:
        CTkSlider.configure(self, True, state=NORMAL)
