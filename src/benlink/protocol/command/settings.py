from __future__ import annotations
from .bitfield import Bitfield, bf_int_enum, bf_int, bf_bool, bf_dyn
from .common import ReplyStatus
import typing as t


class LocChMap:
    def forward(self, x: int) -> int | t.Literal["current"]:
        return x - 1 if x > 0 else "current"

    def back(self, y: int | t.Literal["current"]):
        return 0 if y == "current" else y + 1


class Settings(Bitfield):
    channel_a_lower: int = bf_int(4, default=0)
    channel_b_lower: int = bf_int(4, default=0)
    scan: bool = bf_bool(default=False)
    aghfp_call_mode: int = bf_int(1, default=0)
    double_channel: int = bf_int(2, default=0)
    squelch_level: int = bf_int(4, default=0)
    tail_elim: bool = bf_bool(default=False)
    auto_relay_en: bool = bf_bool(default=False)
    auto_power_on: bool = bf_bool(default=False)
    keep_aghfp_link: bool = bf_bool(default=False)
    mic_gain: int = bf_int(3, default=0)
    tx_hold_time: int = bf_int(4, default=0)
    tx_time_limit: int = bf_int(5, default=0)
    local_speaker: int = bf_int(2, default=0)
    bt_mic_gain: int = bf_int(3, default=0)
    adaptive_response: bool = bf_bool(default=False)
    dis_tone: bool = bf_bool(default=False)
    power_saving_mode: bool = bf_bool(default=False)
    auto_power_off: int = bf_int(3, default=0)
    auto_share_loc_ch: int = bf_int(5, default=0)
    hm_speaker: int = bf_int(2, default=0)
    positioning_system: int = bf_int(4, default=0)
    time_offset: int = bf_int(6, default=0)
    use_freq_range_2: bool = bf_bool(default=False)
    ptt_lock: bool = bf_bool(default=False)
    leading_sync_bit_en: bool = bf_bool(default=False)
    pairing_at_power_on: bool = bf_bool(default=False)
    screen_timeout: int = bf_int(5, default=0)
    kiss_upload_tx_msg: bool = bf_bool(default=False)
    kiss_en: bool = bf_bool(default=False)
    imperial_unit: bool = bf_bool(default=False)
    channel_a_upper: int = bf_int(4, default=0)
    channel_b_upper: int = bf_int(4, default=0)
    wx_mode: int = bf_int(2, default=0)
    noaa_ch: int = bf_int(4, default=0)
    vfol_tx_power_x: int = bf_int(2, default=0)
    vfo2_tx_power_x: int = bf_int(2, default=0)
    dis_digital_mute: bool = bf_bool(default=False)
    signaling_ecc_en: bool = bf_bool(default=False)
    ch_data_lock: bool = bf_bool(default=False)
    auto_share_loc_ch_upper: int = bf_int(3, default=0)
    kiss_tx_delay: int = bf_int(8, default=0)
    kiss_tx_tail: int = bf_int(8, default=0)
    vox_en: bool = bf_bool(default=False)
    vox_level: int = bf_int(3, default=0)
    dis_bt_mic: bool = bf_bool(default=False)
    vox_delay: int = bf_int(3, default=0)
    ns_en: bool = bf_bool(default=False)
    alarm_volume: int = bf_int(4, default=0)
    use_custom_location: bool = bf_bool(default=False)
    gpwpl_upload_en: bool = bf_bool(default=False)
    vfo1_mod_freq_x: int = bf_int(1, default=0)
    custom_location_lat: int = bf_int(24, default=0)
    custom_location_lon: int = bf_int(24, default=0)


class ReadSettingsBody(Bitfield):
    pass


class ReadSettingsReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
    settings: Settings | None = bf_dyn(
        lambda x: Settings if x.reply_status == ReplyStatus.SUCCESS else None
    )


class WriteSettingsBody(Bitfield):
    settings: Settings


class WriteSettingsReplyBody(Bitfield):
    reply_status: ReplyStatus = bf_int_enum(ReplyStatus, 8)
