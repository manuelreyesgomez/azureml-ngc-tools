import threading


class port_forward_logger(threading.Thread):
    def __init__(self, portforward_proc):
        super().__init__()

        self.portforward_proc = portforward_proc
        self.portforward_log = open("portforward_out_log.txt", "w")
        self.stop_logging = threading.Event()
        self.running = True

    def run(self):
        while self.running:
            portforward_out = self.portforward_proc.stdout.readline()
            if self.portforward_proc != "":
                self.portforward_log.write(portforward_out)
                self.portforward_log.flush()

        return

    def join(self, timeout=None):
        self.running = False
        self.stop_logging.set()
        super().join(timeout)
