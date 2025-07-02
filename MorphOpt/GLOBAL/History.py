import numpy as np

class History:
    """
    A class to record the information of the optimization process.
    """

    def __init__(self):
        self.history_objective: list[float] = []
        """
        The history of the objective function values.
        """
        self.history_time: list[list[float]] = []
        """
        The history of the time taken for each iteration.
        """
        
        self.history_deformation: list = []
        """
        The history of the deformation values.
        """

        self.iteration: int = 0
        """
        The current iteration number.
        """

    def save(self, path: str) -> None:
        """
        Save the history to a file.
        """
        np.savetxt(path + '/history_objective.txt', self.history_objective, delimiter=',')
        np.savetxt(path + '/history_time.txt', self.history_time, delimiter=',')
        np.savetxt(path + '/iteration.txt', [self.iteration], delimiter=',')
        np.save(path + '/history_deformation.npy', self.history_deformation)

    def load(self, path: str) -> None:
        """
        Load the history from a file.
        """
        self.history_objective = np.loadtxt(path + '/history_objective.txt', delimiter=',').tolist()
        self.history_time = np.loadtxt(path + '/history_time.txt', delimiter=',').tolist()
        self.iteration = int(np.loadtxt(path + '/iteration.txt', delimiter=','))
        self.history_deformation = np.load(path + '/history_deformation.npy').tolist()