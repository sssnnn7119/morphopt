from ..optcore import ObjectiveFunction as BaseObjectiveFunction


class ObjectiveFunction(BaseObjectiveFunction):
    """
    This class is responsible for computing the objective function value and the design sensitivity variables for shape optimization.
    """

    def save(self, foldpath, iteration, insname = 'final_model', surface = 'surface_0_All'):
        super().save(foldpath, iteration, insname, surface)
        # Save the FEA model for each iteration
        self.fe.save_model(f"{foldpath}/{self.pathlog_required()[1]}/femodel_{iteration}")
    