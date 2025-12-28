import multiprocessing as mp

class Monitor:
    def __init__(self, dataqueue: mp.Queue = None):
        self.dataqueue = dataqueue
