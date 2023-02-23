try:
    from ansible.utils.display import Display as OrigDisplay
    HAS_DISPLAY = True
except:
    HAS_DISPLAY = False
    pass

class Display:

    def __init__(self) -> None:
        self.display = OrigDisplay() if HAS_DISPLAY else None

    def info(self, msg, color=None, stderr=False, screen_only=False,
             log_only=False, newline=True):
        if self.display:
            self.display.display(msg, color, stderr,
                                 screen_only, log_only, newline)

    def v(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=0)

    def vv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=1)

    def vvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=2)

    def vvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=3)

    def vvvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=4)

    def vvvvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=5)

    def debug(self, msg, host=None):
        if self.display:
            self.display.debug(msg, host)

    def verbose(self, msg, host=None, caplevel=2):
        if self.display:
            self.display.verbose(msg, host, caplevel)
