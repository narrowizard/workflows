from typing import List, Optional, Dict, Union
from .iobase import pipe_interaction
from .widgets import Widget, Button


class Form:
    """
    A container for different widgets

    Syntax:
    """

    def __init__(
        self,
        components: List[Union[Widget, str]],
        title: Optional[str] = None,
    ):
        """
        components: components in the form, can be widgets (except Button) or strings
        title: title of the form
        """
        assert (
            any(isinstance(c, Button) for c in components) is False
        ), "Button is not allowed in Form"

        self._components = components
        self._title = title

        self._rendered = False

    @property
    def components(self) -> List[Union[Widget, str]]:
        """
        Return the components
        """
        return self._components

    def _in_chatmark(self) -> str:
        """
        Generate ChatMark syntax for all components
        """
        lines = []

        if self._title:
            lines.append(self._title)

        for c in self.components:
            if isinstance(c, str):
                lines.append(c)
            elif isinstance(c, Widget):
                lines.append(c._in_chatmark())
            else:
                raise ValueError(f"Invalid component {c}")

        return "\n".join(lines)

    def _parse_response(self, response: Dict):
        """
        Parse response from user input
        """
        for c in self.components:
            if isinstance(c, Widget):
                c._parse_response(response)

    def render(self):
        """
        Render to receive user input
        """
        if self._rendered:
            # already rendered once
            # not sure if the constraint is necessary
            # could be removed if re-rendering is needed
            raise RuntimeError("Widget can only be rendered once")

        self._rendered = True

        lines = [
            "```chatmark type=form",
            self._in_chatmark(),
            "```",
        ]

        chatmark = "\n".join(lines)
        response = pipe_interaction(chatmark)
        self._parse_response(response)