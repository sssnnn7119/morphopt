from torchfea import FEAController
from torchfea.model.loads.contact import (
    Contact as TorchFEAContact,
)
from torchfea.model.loads.contact import (
    ContactSelf as TorchFEASelfContact,
)

from ....constants import CONSTANT
from .base_component import BaseFEAComponent


class Contact(BaseFEAComponent):
    """Declare contact between named surfaces on two assembly instances.

    This declaration has no per-case amplitude parameters. It creates a TorchFEA contact load
    using the supplied penalty-transition settings.
    """

    def __init__(
        self,
        instance_name1: str,
        surface_name1: str,
        instance_name2: str,
        surface_name2: str,
        penalty_threshold_h: float = CONSTANT.KERNEL.FEA.CONTACT_PENALTY_THRESHOLD,
        penalty_start_f: float | None = None,
        penalty_end_f: float | None = None,
    ) -> None:
        """Initialize Contact and its configuration state.

        Args:
            instance_name1 (str): Registered Instance name on the first contact side.
            surface_name1 (str): Named surface set on the first contact side.
            instance_name2 (str): Registered Instance name on the second contact side.
            surface_name2 (str): Named surface set on the second contact side.
            penalty_threshold_h (float): Contact transition distance in model length units; None
                retains the backend default when accepted.
            penalty_start_f (float | None): Optional contact force at the start of the penalty
                transition.
            penalty_end_f (float | None): Optional contact force at the end of the penalty
                transition.
        """
        super().__init__()
        self.instance_name1 = instance_name1
        self.surface_name1 = surface_name1
        self.instance_name2 = instance_name2
        self.surface_name2 = surface_name2
        self.penalty_threshold_h = float(penalty_threshold_h)
        self.penalty_start_f = (
            None if penalty_start_f is None else float(penalty_start_f)
        )
        self.penalty_end_f = None if penalty_end_f is None else float(penalty_end_f)

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        kwargs = {
            "instance_name1": self.instance_name1,
            "instance_name2": self.instance_name2,
            "surface_name1": self.surface_name1,
            "surface_name2": self.surface_name2,
            "penalty_threshold_h": self.penalty_threshold_h,
        }
        if self.penalty_start_f is not None:
            kwargs["penalty_start_f"] = self.penalty_start_f
        if self.penalty_end_f is not None:
            kwargs["penalty_end_f"] = self.penalty_end_f
        loadobj = TorchFEAContact(**kwargs)

        fe.assembly.add_load(loadobj, name)


class SelfContact(BaseFEAComponent):
    """Declare self-contact on one named instance surface.

    This declaration has no per-case amplitude parameters. An omitted threshold retains the
    TorchFEA backend default.
    """

    def __init__(
        self,
        instance_name: str,
        surface_name: str,
        penalty_threshold_h: float | None = None,
    ) -> None:
        """Initialize SelfContact and its configuration state.

        Args:
            instance_name (str): Registered Instance name in the assembly.
            surface_name (str): Named surface set on the selected instance.
            penalty_threshold_h (float | None): Contact transition distance in model length units;
                None retains the backend default when accepted.
        """
        super().__init__()
        self.instance_name = instance_name
        self.surface_name = surface_name
        self.penalty_threshold_h = (
            None if penalty_threshold_h is None else float(penalty_threshold_h)
        )

    @property
    def num_values(self) -> int:
        """Return the number of load parameters supplied by each load case.

        Returns:
            int: Number of scalar load-case parameters exposed by this component.
        """
        return 0

    def modify_fea(self, fe: FEAController, name: str) -> None:
        """Create and register this declaration in the finite-element assembly.

        Args:
            fe (FEAController): TorchFEA controller whose assembly is modified or solved.
            name (str): Name identifying the item in its owning collection.
        """
        kwargs = {
            "instance_name": self.instance_name,
            "surface_name": self.surface_name,
        }
        if self.penalty_threshold_h is not None:
            kwargs["penalty_threshold_h"] = self.penalty_threshold_h
        loadobj = TorchFEASelfContact(**kwargs)

        fe.assembly.add_load(loadobj, name)
