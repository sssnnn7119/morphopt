import torch
from .baseloadinterface import BaseLoadInterface

# Prefer the same import style as PressureInterface
try:
	from FEA.assemble.loads.contact import Contact, ContactSelf  # type: ignore
except Exception:  # Fallback if package structure differs
	# Defer import to get_fea_load to avoid import-time failures
	Contact = None  # type: ignore
	ContactSelf = None  # type: ignore


class ContactInterface(BaseLoadInterface):
	"""
	Contact load interface between two instances.

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

	def get_fea_load(self):
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
		return Contact(**kwargs)  # type: ignore



class ContactSelfInterface(BaseLoadInterface):
	"""
	Self-contact load interface for a single instance surface.

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


	def get_fea_load(self):
		from FEA.assemble.loads.contact import ContactSelf

		kwargs = dict(
			instance_name=self.instance_name,
			surface_name=self.surface_name,
		)
		if self.penalty_threshold_h is not None:
			kwargs["penalty_threshold_h"] = self.penalty_threshold_h
		return ContactSelf(**kwargs)  # type: ignore
