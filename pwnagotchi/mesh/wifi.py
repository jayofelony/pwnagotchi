NumChannels = 233

def freq_to_channel(freq):
    if freq <= 2472: # 2.4ghz wifi
        return int(((freq - 2412) / 5) + 1)
    elif freq == 2484: # channel 14 special
        return int(14)
    elif 5150 <= freq <= 5895: # 5ghz wifi
        return int(((freq - 5180) / 5) + 36)
    elif 5925 <= freq <= 7115: # 6ghz wifi
        return int(((freq - 5950) / 5) + 11)
    else:
        return 0
