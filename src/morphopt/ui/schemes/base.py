from morphopt.ui.model.problem import ProblemModel


class Scheme:
    def create_problem(self) -> ProblemModel:
        # TODO: Build a scheme-specific Params factory.
        return ProblemModel()
