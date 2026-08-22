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
    # 5 GHz Wi-Fi channels (36-177): channel number and frequency are
    # linearly related (freq = 5000 + 5*channel) across the whole band, not
    # per 20MHz-spaced sub-block - dividing by 20 without multiplying back
    # up by 4 only produced a correct result for the first channel of each
    # sub-band (36, 100, 149) and was wrong for every other one, and the
    # 5850 upper bound cut off channels 169/173/177 (5845/5865/5885 MHz)
    # entirely.
    elif 5150 <= freq <= 5895:  # 5 GHz Wi-Fi
        return int((freq - 5000) / 5)
    # 6 GHz Wi-Fi channels (1-233): freq = 5950 + 5*channel, same fix as above
    elif 5925 <= freq <= 7115:  # 6 GHz Wi-Fi
        return int((freq - 5950) / 5)
    # If the frequency does not match any valid channel
    raise ValueError(f"The frequency {freq} MHz is not a valid Wi-Fi frequency.")