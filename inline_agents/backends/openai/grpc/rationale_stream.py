"""Hold assistant text until a tool call shows it is rationale, or the response ends."""

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

PieceKind = Literal["rationale", "delta"]


@dataclass(frozen=True)
class StreamPiece:
    kind: PieceKind
    text: str
    rationale_index: str | None = None


@dataclass(frozen=True)
class RationaleSaveContext:
    project_uuid: str
    contact_urn: str
    preview: bool
    session_id: str
    contact_name: str
    channel_uuid: str | None


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
        pieces = list(self._pending)
        self._pending.clear()
        return pieces


class _StreamSink(Protocol):
    @property
    def is_active(self) -> bool: ...

    def send_rationale(self, content: str, rationale_index: str) -> bool: ...

    def send_delta(self, content: str, metadata: dict | None = None) -> bool: ...


def feed_stream_event(classifier: RationaleStreamClassifier, event) -> None:
    """Translate one SDK stream event into classifier input."""
    from openai.types.responses import ResponseTextDeltaEvent

    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
        classifier.on_text(event.data.delta or "")
        return
    item = getattr(event, "item", None)
    if event.type == "run_item_stream_event" and item is not None and getattr(item, "type", None) == "tool_call_item":
        classifier.on_tool_call()


def emit_stream_pieces(session: _StreamSink | None, pieces: list[StreamPiece]) -> list[StreamPiece]:
    """Send pieces on the live stream. Returns the rationale pieces that were queued."""
    if session is None or not session.is_active:
        return []
    sent: list[StreamPiece] = []
    for piece in pieces:
        if piece.kind == "rationale":
            if session.send_rationale(piece.text, piece.rationale_index or "1"):
                sent.append(piece)
            else:
                logger.warning(
                    "[emit_stream_pieces] rationale was not queued index=%s",
                    piece.rationale_index,
                )
            continue
        if not session.send_delta(piece.text):
            logger.warning("[emit_stream_pieces] final-response delta was not queued")
    return sent
