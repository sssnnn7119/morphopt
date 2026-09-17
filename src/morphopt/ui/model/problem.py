from morphopt.optcore.modelparams.params import Params


class ProblemModel:
    """UI-facing problem definition placeholder."""

    def __init__(self, params: Params | None = None) -> None:
        self.params = params
        """Params graph edited by the UI."""
