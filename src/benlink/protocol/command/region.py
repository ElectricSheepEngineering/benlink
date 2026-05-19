from __future__ import annotations
from .bitfield import Bitfield, bf_int_enum, bf_int
from .common import ReplyStatus


class SetRegionBody(Bitfield):
    region_id: int = bf_int(8)


class SetRegionReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
