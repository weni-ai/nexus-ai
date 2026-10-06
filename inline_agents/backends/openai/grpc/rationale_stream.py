"""Hold assistant text until a tool call shows it is rationale, or the response ends."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamPiece:
    kind: str
    text: str
    rationale_index: str | None = None


class RationaleStreamClassifier:
    """Classify one turn's assistant text before it reaches the live stream.

    While rationale is enabled, text stays held. A tool call releases the hold
    as one complete rationale. The end of the response releases whatever remains
    as final-answer pieces, in the same chunks the model produced.
    """

    def __init__(self, *, enabled: bool):
        self.enabled = enabled
        self._hold: list[str] = []
        self._index = 0
        self._pending: list[StreamPiece] = []

    def on_text(self, text: str) -> None:
        if not text:
            return
        if not self.enabled:
            self._pending.append(StreamPiece(kind="delta", text=text))
            return
        self._hold.append(text)

    def on_tool_call(self) -> None:
        if not self.enabled:
            return
        text = "".join(self._hold).strip()
        self._hold.clear()
        if not text:
            return
        self._index += 1
        self._pending.append(StreamPiece(kind="rationale", text=text, rationale_index=str(self._index)))

    def finish(self) -> None:
        if not self.enabled:
            return
        pending = list(self._hold)
        self._hold.clear()
        for part in pending:
            if part:
                self._pending.append(StreamPiece(kind="delta", text=part))

    def drain(self) -> list[StreamPiece]:
        pieces = self._pending
        self._pending = []
        return pieces
