

class BaseObject:
    def save(self, foldpath: str, iteration: int) -> None:
        """
        Save the objective function data to a file.
        
        Args:
            foldpath (str): The path to save the objective function data.
            iteration (int): The iteration number to save.
        """
        pass

    def load(self, foldpath: str, iteration: int) -> None:
        """
        Load the objective function data from a file.
        
        Args:
            foldpath (str): The path to load the objective function data from.
            iteration (int): The iteration number to load.
        """
        pass