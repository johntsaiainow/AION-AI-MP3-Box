"""Google AIY Voice HAT V1 top button and single-color lamp."""

from glob import glob

BUTTON = 23
LED = 25


def open_voice_button():
    try:
        import gpiod
        from gpiod.line import Bias, Direction, Edge, Value
    except ImportError:
        return None
    for path in sorted(glob("/dev/gpiochip*")):
        try:
            with gpiod.Chip(path) as chip:
                if chip.get_info().label != "pinctrl-bcm2835":
                    continue
                return chip.request_lines(
                    consumer="aiy-box-rebirth", config={
                        BUTTON: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                                   active_low=True, edge_detection=Edge.RISING),
                        LED: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                    },
                )
        except OSError:
            continue
    return None


def set_voice_lamp(request, playing):
    from gpiod.line import Value
    try:
        request.set_value(LED, Value.ACTIVE if playing else Value.INACTIVE)
    except OSError:
        pass
