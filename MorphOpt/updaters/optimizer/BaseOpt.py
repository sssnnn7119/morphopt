import torch


class BaseOpt():
    def __init__(self, closure: callable):
        self.closure = closure
        """
        the objective function to be optimized, which should return the objective value
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
                return alpha
            alpha *= self._rou1
            if (alpha * direction).abs().max() < 1e-14:
                return 0.

    def step(x_now: torch.Tensor) -> torch.Tensor:
        """
        Perform a single optimization step.
        """
        pass

class LBFGS(BaseOpt):
    def __init__(self,
                 closure: callable,
                 num_limit:int = 10,
                 tol_error:float = 1e-10) -> None:
        super(LBFGS, self).__init__(closure=closure)
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
    
    def step(self, x_now: torch.Tensor):
        
        
        x_now_ = x_now.detach().requires_grad_()
        obj_now = self.closure(x_now_)
        gk_now = torch.autograd.grad(obj_now, x_now_)[0]

        gk_now.view(-1)[gk_now.view(-1).isnan()] = 0
        
        # if the first iteration, use steepest descent direction
        if len(self.SK) == 0:
            dk = -gk_now
        else:
            dk = self.Hg_loop(-gk_now)
        dk.view(-1)[dk.view(-1).isnan()] = 0

        # if the gradient is not positive, use steepest descent direction
        if (dk * gk_now).sum() > 0:
            dk = -dk

        # line search
        alpha = self._LineSearchBacktracking(x0=x_now, dx=gk_now, direction=dk, alpha0=1., obj0=obj_now)

        # if the step length is too small, stop the iteration
        if abs(alpha) <= self.tol_error:
            self.SK = []
            self.YK = []
            self.rhok = []

        x_new = x_now + alpha * dk
        
        x_new_ = x_new.detach().requires_grad_()
        obj_new = self.closure(x_new_)

        if obj_new>obj_now:
            self.SK = []
            self.YK = []
            self.rhok = []
            return torch.zeros_like(x_now)
        
        gk_new = torch.autograd.grad(obj_new, x_new_)[0]

        yk = gk_new.flatten() - gk_now.flatten()
        sk = alpha * dk.flatten()

        # BFGS method
        if yk.norm() > 0:
            self.SK.append(sk)
            self.YK.append(yk)
            self.rhok.append(1 / yk.dot(sk))

            if len(self.SK) > self.num_limit:
                self.SK = self.SK[1:]
                self.YK = self.YK[1:]
                self.rhok = self.rhok[1:]
        
        return alpha, dk


