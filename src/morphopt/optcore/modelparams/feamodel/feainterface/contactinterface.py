from torchfea import FEAController
import torch
from .basefeainterface import BaseFEAInterface

# Prefer the same import style as PressureInterface
try:
	from torchfea.model.loads.contact import Contact, ContactSelf  # type: ignore
except Exception:  # Fallback if package structure differs
	# Defer import to get_fea_load to avoid import-time failures
	Contact = None  # type: ignore
	ContactSelf = None  # type: ignore


class ContactInterface(BaseFEAInterface):
	"""
	Contact load interface between two instances.

	Notes:
	- This contact interface has no amplitude values (num_values = 0).
	  It is registered once and applied as a constraint; no per-step values required.
	- Penalty parameters can be specified via init args.

	This interface describes a contact constraint between surface1 of instance1
	and surface2 of instance2. It integrates with LoadsParams so contact loads
	are injected consistently during solve and sensitivity sub-steps.
	"""

	def __init__(
		self,
		instance_name1: str,
		surface_name1: str,
		instance_name2: str,
		surface_name2: str,
		penalty_threshold_h: float = 3.0,
		penalty_start_f: float | None = None,
		penalty_end_f: float | None = None,
	) -> None:
		super().__init__()
		self.instance_name1 = instance_name1
		self.surface_name1 = surface_name1
		self.instance_name2 = instance_name2
		self.surface_name2 = surface_name2
		self.penalty_threshold_h = float(penalty_threshold_h)
		self.penalty_start_f = None if penalty_start_f is None else float(penalty_start_f)
		self.penalty_end_f = None if penalty_end_f is None else float(penalty_end_f)

	@property
	def num_values(self) -> int:
		return 0

	def modify_fea(self, fe: FEAController, name: str):

		# Lazy import to be robust to different package layouts
		global Contact
		if Contact is None:
			from FEA.assemble.loads.contact import Contact as _Contact  # type: ignore
			Contact = _Contact  # type: ignore

		kwargs = dict(
			instance_name1=self.instance_name1,
			instance_name2=self.instance_name2,
			surface_name1=self.surface_name1,
			surface_name2=self.surface_name2,
			penalty_threshold_h=self.penalty_threshold_h,
		)
		if self.penalty_start_f is not None:
			kwargs["penalty_start_f"] = self.penalty_start_f
		if self.penalty_end_f is not None:
			kwargs["penalty_end_f"] = self.penalty_end_f
		loadobj = Contact(**kwargs)  # type: ignore

		fe.assembly.add_load(loadobj, name)



class ContactSelfInterface(BaseFEAInterface):
	"""
	Self-contact load interface for a single instance surface.

	Notes:
	- This self-contact interface has no amplitude values (num_values = 0).
	  It is registered once and applied as a constraint; no per-step values required.

	Adds a self-contact constraint for a given surface on one instance.
	"""

	def __init__(
		self,
		instance_name: str,
		surface_name: str,
		penalty_threshold_h: float | None = None,
	) -> None:
		super().__init__()
		self.instance_name = instance_name
		self.surface_name = surface_name
		self.penalty_threshold_h = None if penalty_threshold_h is None else float(penalty_threshold_h)
		
	@property
	def num_values(self) -> int:
		return 0

	def modify_fea(self, fe: FEAController, name: str):
		from torchfea.model.loads.contact import ContactSelf

		kwargs = dict(
			instance_name=self.instance_name,
			surface_name=self.surface_name,
		)
		if self.penalty_threshold_h is not None:
			kwargs["penalty_threshold_h"] = self.penalty_threshold_h
		loadobj = ContactSelf(**kwargs)  # type: ignore

		fe.assembly.add_load(loadobj, name)
