
import torch
from .baseobject import BaseObject
import morphopt
from .modelparams import Params

class BaseUpdater(BaseObject):
    """
    Base class for all Updaters.
    """

    class Optimizer():

        class BaseOpt():
            def __init__(self, closure: callable):
                self.closure = closure
                """
                the objective function to be optimized, which should return the objective value
                """

                self.grad = torch.func.jacrev(self.closure)
                """        the gradient of the objective function, which should return the gradient vector
                """

                # params for line search
                self._c1 = 1e-4
                self._rou1 = 0.2

            def set_line_search_params(self, c1: float = None, rou1: float = None):
                """
                Set the parameters for the line search method.

                Parameters:
                    c1 (float): The parameter for the Wolfe condition.
                    rou1 (float): The parameter for the backtracking line search.
                """
                if c1 is not None:
                    self._c1 = c1
                if rou1 is not None:
                    self._rou1 = rou1

            def _LineSearchBacktracking(self, x0: torch.Tensor, dx: torch.Tensor, direction: torch.Tensor, alpha0: float = 1.0, obj0: float = None):
                
                """
                Backtracking line search to find the step length for the optimization process.
                
                Parameters:
                    x0 (torch.Tensor): The current point in the optimization process.
                    dx (torch.Tensor): The gradient vector at the current point.
                    direction (torch.Tensor): The search direction.
                    alpha0 (float): The initial step length.
                    c1 (float): The parameter for the Wolfe condition.
                    rou1 (float): The parameter for the backtracking line search.
                    obj0 (float): The initial objective value.

                Returns:
                    float: The step length that satisfies the Wolfe condition.
                """

                if obj0 is None:
                    obj0 = self.closure(x0)

                alpha = alpha0
                while True:
                    x_new = x0 + alpha * direction
                    with torch.no_grad():
                        obj_new = self.closure(x_new)
                    if ~torch.isnan(obj_new) and ~torch.isinf(
                            obj_new
                    ) and obj_new < obj0 + self._c1 * alpha * dx.dot(direction):
                        return alpha, obj_new
                    alpha *= self._rou1
                    if (alpha * direction).abs().max() < 1e-14:
                        return 0., obj0

            def step(x_now: torch.Tensor, gk_now: torch.Tensor=None) -> torch.Tensor:
                """
                Perform a single optimization step.
                """
                pass

        class LBFGS(BaseOpt):
            def __init__(self,
                        closure: callable,
                        num_limit:int = 10,
                        tol_error:float = 1e-10) -> None:
                super().__init__(closure=closure)
                self.SK = []
                self.YK = []
                self.rhok = []

                self.num_limit = num_limit
                """
                the number of pairs of Hessian and gradient stored in the memory
                """

                self.tol_error = tol_error
                """
                the tolerance for the convergence of the optimization process
                """

            def Hg_loop(self, dv: torch.Tensor) -> torch.Tensor:
                """
                Compute the product of the inverse Hessian matrix and the gradient vector.
                This is done using the BFGS update formula.

                Parameters:
                    dv (torch.Tensor): The gradient vector.

                Returns:
                    torch.Tensor: The product of the inverse Hessian matrix and the gradient vector.
                """
                
                q = dv.clone()
                alpha = torch.zeros(len(self.SK))
                for i in range(len(self.SK) - 1, -1, -1):
                    alpha[i] = self.rhok[i] * self.SK[i].dot(q)
                    q = q - alpha[i] * self.YK[i]
                
                y = q / (self.rhok[-1] * self.YK[-1].dot(self.YK[-1]))
                
                for i in range(len(self.SK)):
                    beta = self.rhok[i] * self.YK[i].dot(y)
                    y = y + (alpha[i] - beta) * self.SK[i]
                    
                return y
            
            def step(self, x_now: torch.Tensor, gk_now: torch.Tensor=None):
                
                obj_now = self.closure(x_now)
                if gk_now is None:
                    gk_now: torch.Tensor = self.grad(x_now).flatten()

                gk_now.view(-1)[gk_now.view(-1).isnan()] = 0
                
                # if the first iteration, use steepest descent direction
                if len(self.SK) == 0:
                    dk = -gk_now
                else:
                    dk = self.Hg_loop(-gk_now)
                if dk.view(-1).isnan().any():
                    dk = -gk_now
                    self.SK = []
                    self.YK = []
                    self.rhok = []

                # if the gradient is not positive, use steepest descent direction
                if (dk * gk_now).sum() > 0:
                    dk = -dk

                # line search
                alpha, obj_new = self._LineSearchBacktracking(x0=x_now, dx=gk_now, direction=dk, alpha0=1., obj0=obj_now)

                # if the step length is too small, stop the iteration
                if abs(alpha) <= self.tol_error:
                    self.SK = []
                    self.YK = []
                    self.rhok = []

                x_new = x_now + alpha * dk
                

                if obj_new>obj_now:
                    self.SK = []
                    self.YK = []
                    self.rhok = []
                    return 0., torch.zeros_like(x_now), gk_now
                
                gk_new: torch.Tensor =self.grad(x_new).flatten()

                yk = gk_new.flatten() - gk_now.flatten()
                sk = alpha * dk.flatten()

                # BFGS method
                if yk.norm() > 1e-14 and sk.norm() > 1e-14:
                    self.SK.append(sk)
                    self.YK.append(yk)
                    self.rhok.append(1 / yk.dot(sk))

                    if len(self.SK) > self.num_limit:
                        self.SK = self.SK[1:]
                        self.YK = self.YK[1:]
                        self.rhok = self.rhok[1:]
                
                return alpha, dk, gk_new




    def __init__(self, params: Params, *args, **kwargs):
        """
        Initialize the BaseUpdater.
        """

        self.obj_funcs: dict[str, callable] = {}
        """A dictionary of objective functions to be optimized.
        The keys are the names of the functions, and the values are the functions themselves.
        """

        self.constraints_funcs: dict[str, callable] = {}
        """A dictionary of constraints to be satisfied.
        The keys are the names of the constraints, and the values are the constraints themselves.
        """

        self.params: Params = params
        """The parameters of optimization process.
        This should be set to an instance of the Params class.
        """
        
        self.optimizer: BaseUpdater.Optimizer.BaseOpt = None
        """The optimization algorithm used to update the design variables.
        This should be set to an instance of a subclass of Optimizer.BaseOpt.
        """

    
    def reinitialize(self, iter_now: int, sensitivity: list[torch.Tensor]) -> None:
        """
        reInitialize the updater with the current iteration and sensitivity.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
        
    def initialize(self) -> None:
        """
        Initialize the updater.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def closure(self, x: torch.Tensor, return_list: bool = False) -> torch.Tensor:
        """
        This method is called to update the design variables based on the optimization algorithm used.
        
        Parameters:
            x (torch.Tensor): The current design variables.
            return_list (bool): If True, returns a list of objective function values; otherwise, returns their sum.
        
        Returns:
            torch.Tensor: The objective function value(s).
        """
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def update_variables(self, dx: torch.Tensor) -> None:
        """
        Update the variables of the surfaces.
        """
        pass

    def update(self) -> torch.Tensor:
        """
        Update the parameters of the optimization process.
        """
        raise NotImplementedError("This method should be overridden by subclasses.")

class Updaters(BaseObject):
    """
    This class is responsible for updating the morphologies of the neurons.
    """

    def __init__(self, surfaces: BaseUpdater = None, materials: BaseUpdater = None, device: str = None, *args, **kwargs):
        """
        Initialize the Updaters class with a neuron object.

        Args:
            surfaces (BaseUpdater, optional): An instance of the BaseUpdater class for updating the surfaces.
            loads (UpdaterLoads, optional): An instance of the UpdaterLoads class for updating the loads.
            materials (BaseUpdater, optional): An instance of the BaseUpdater class for updating the materials.
            device (str, optional): The device to use for computating the objective function and sensitivity analysis. If None, it will use the default device.
        """
        self._surface: BaseUpdater = None
        """
        BaseUpdater: An instance of the BaseUpdater class for updating the surfaces.
        """
        self.if_update_surface = False
        """
        if_update_surface: A flag indicating whether the surface needs to be updated.
        """
        
        if surfaces is not None:
            self._surface = surfaces
            self.if_update_surface = True
        self._var_surface: torch.Tensor = None
        """
        var_surface: The updated surface variables.
        """

        self._materials: BaseUpdater = None
        """
        BaseUpdater: An instance for updating material variables.
        """
        self.if_update_material = False
        """
        if_update_material: A flag indicating whether material variables need updates.
        """
        if materials is not None:
            self._materials = materials
            self.if_update_material = True
        self._var_material: torch.Tensor = None
        """
        var_material: The updated material variables.
        """

        self._device: str = device
        """
        The device to use for computating the objective function and sensitivity analysis. If None, it will be cpu by default.
        """

    def reinitialize(self, iteration: int) -> None:
        """
        reInitialize the Updaters class.
        This method reinitializes the surfaces, loads, and materials if they are present.
        """
        pass

    def initialize(self) -> None:
        """
        Initialize the Updaters class.
        This method initializes the surfaces, loads, and materials if they are present.
        """
        if self.if_update_surface:
            self._surface.initialize()
        if self.if_update_material:
            self._materials.initialize()

    def update(self, gradients: dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Update the morphology of the neuron.
        """
        
        default_device = torch.get_default_device()

        # reinitialize each updater with the corresponding gradient, and update the variables for surfaces and materials.
        if self.if_update_surface:
            self._surface.reinitialize(gradient=gradients['geometry'])
        if self.if_update_material:
            self._materials.reinitialize(gradient=gradients['materials'])

        if self._device is not None:
            torch.set_default_device(self._device)
            morphopt.controller._change_device_recursive(self, self._device)
            morphopt.controller._change_device_recursive(gradients, self._device)

        if self.if_update_surface:
            self._var_surface = self._surface.update()
        if self.if_update_material:
            self._var_material = self._materials.update()

        if self._device is not None:
            torch.set_default_device(default_device)
            morphopt.controller._change_device_recursive(self, default_device)
    
    def update_variables(self) -> None:
        """
        Update the variables of the surfaces and loads.
        """
        if self.if_update_surface:
            self._surface.update_variables(dx=self._var_surface)
        if self.if_update_material:
            self._materials.update_variables(dx=self._var_material)

    def save(self, foldpath: str, iteration: int) -> None:
        """
        Save the updater state to a file.
        """
        if self.if_update_surface:
            self._surface.save(foldpath=foldpath, iteration=iteration)
        if self.if_update_material:
            self._materials.save(foldpath=foldpath, iteration=iteration)

    def load(self, foldpath: str, iteration: int) -> None:
        if self.if_update_surface:
            self._surface.load(foldpath=foldpath, iteration=iteration)
        if self.if_update_material:
            self._materials.load(foldpath=foldpath, iteration=iteration)


    def pathlog_required(self):
        paths = []
        if self.if_update_surface:
            paths += self._surface.pathlog_required()
        if self.if_update_material:
            paths += self._materials.pathlog_required()
        return paths