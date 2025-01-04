NumChannels: int = 233

def freq_to_channel(freq: float) -> int:
    """
    Convert a Wi-Fi frequency (in MHz) to its corresponding channel number.
    Supports 2.4 GHz, 5 GHz, and 6 GHz Wi-Fi bands.
    Args:
     freq: The frequency in MHz.
    Returns:
     The Wi-Fi channel as an integer, or ValueError if the frequency is invalid.
    """
    # 2.4 GHz Wi-Fi channels
    if 2412 <= freq <= 2472:  # 2.4 GHz Wi-Fi
        return int(((freq - 2412) / 5) + 1)
    elif freq == 2484:  # Channel 14 special
        return 14
    # 5 GHz Wi-Fi channels
    elif 5150 <= freq <= 5850:  # 5 GHz Wi-Fi
        if 5150 <= freq <= 5350:  # Channels 36-64
            return int(((freq - 5180) / 20) + 36)
        elif 5470 <= freq <= 5725:  # Channels 100-144
            return int(((freq - 5500) / 20) + 100)
        else:  # Channels 149-165
            return int(((freq - 5745) / 20) + 149)
    # 6 GHz Wi-Fi channels
    elif 5925 <= freq <= 7125:  # 6 GHz Wi-Fi
        return int(((freq - 5950) / 20) + 11)
    # If the frequency does not match any valid channel
    raise ValueError(f"The frequency {freq} MHz is not a valid Wi-Fi frequency.")