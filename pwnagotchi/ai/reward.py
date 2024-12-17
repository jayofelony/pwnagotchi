import pwnagotchi.mesh.wifi as wifi

range: tuple[float, float] = (-.7, 1.02)
fuck_zero: float = 1e-20


class RewardFunction(object):
    def __call__(self, epoch_n: float, state: dict[str, float]) -> float:

        tot_epochs: float = epoch_n + fuck_zero
        tot_interactions: float = max(state['num_deauths'] + state['num_associations'], state['num_handshakes']) + fuck_zero
        tot_channels: int = wifi.NumChannels

        h: float = state['num_handshakes'] / tot_interactions
        a: float = .2 * (state['active_for_epochs'] / tot_epochs)
        c: float = .1 * (state['num_hops'] / tot_channels)

        b: float = -.3 * (state['blind_for_epochs'] / tot_epochs)
        m: float = -.3 * (state['missed_interactions'] / tot_interactions)
        i: float = -.2 * (state['inactive_for_epochs'] / tot_epochs)

        # include emotions if state >= 5 epochs
        _sad: float = state['sad_for_epochs'] if state['sad_for_epochs'] >= 5 else 0
        _bored: float = state['bored_for_epochs'] if state['bored_for_epochs'] >= 5 else 0
        s: float = -.2 * (_sad / tot_epochs)
        l: float = -.1 * (_bored / tot_epochs)

        return h + a + c + b + i + m + s + l
