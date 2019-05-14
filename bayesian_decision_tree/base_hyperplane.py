from abc import ABC

import numpy as np
from scipy.optimize._differentialevolution import DifferentialEvolutionSolver
from scipy.sparse import csc_matrix, csr_matrix

from bayesian_decision_tree.base import BaseNode
from bayesian_decision_tree.hyperplane_optimization import HyperplaneOptimizationFunction, ScipyOptimizer


class BaseHyperplaneNode(BaseNode, ABC):
    """
    The base class for all Bayesian decision tree algorithms (classification and regression). Performs all the high-level fitting
    and prediction tasks and outsources the low-level work to the subclasses.
    """
    def __init__(self, partition_prior, prior, child_type, is_regression, optimizer, level):
        BaseNode.__init__(self, partition_prior, prior, child_type, is_regression, level)

        if optimizer is None:
            # default to 'Differential Evolution' which works well and is reasonably fast
            optimizer = ScipyOptimizer(DifferentialEvolutionSolver, 666)

        self.optimizer = optimizer

        # to be set later
        self.best_hyperplane_normal = None
        self.best_hyperplane_origin = None

    def _fit(self, X, y, delta, verbose, feature_names):
        if verbose:
            print('Training level {} with {:10} data points'.format(self.level, len(y)))

        dense = isinstance(X, np.ndarray)
        if not dense and isinstance(X, csr_matrix):
            # column accesses coming up, so convert to CSC sparse matrix format
            X = csc_matrix(X)

        log_p_data_post_all = self._compute_log_p_data_post_no_split(y)

        # the function to optimize (depends on X and y, hence we need to instantiate it for every data set anew)
        optimization_function = HyperplaneOptimizationFunction(
            X,
            y,
            self._compute_log_p_data_post_split,
            log_p_data_post_all,
            self.optimizer.search_space_is_unit_hypercube)

        # create and run optimizer
        self.optimizer.solve(optimization_function)

        self.optimization_function = optimization_function

        # retrieve best hyperplane split from optimization function
        if optimization_function.best_hyperplane_normal is not None:
            # split data and target to recursively train children
            projections = X @ optimization_function.best_hyperplane_normal \
                          - np.dot(optimization_function.best_hyperplane_normal, optimization_function.best_hyperplane_origin)
            indices1 = np.where(projections < 0)[0]
            indices2 = np.where(projections >= 0)[0]

            if len(indices1) > 0 and len(indices2) > 0:
                """
                Note: The reason why indices1 or indices2 could be empty is that the optimizer might find a
                'split' that puts all data one one side and nothing on the other side, and that 'split' has
                a higher log probability than 'log_p_data_post_all' because of the partition prior
                overwhelming the data likelihoods (which are of course identical between the 'all data' and
                the 'everything on one side split' scenarios)s.
                """
                X1 = X[indices1]
                X2 = X[indices2]
                y1 = y[indices1]
                y2 = y[indices2]

                # compute posteriors of children and priors for further splitting
                prior_child1 = self._compute_posterior(y1, 0)
                prior_child2 = self._compute_posterior(y2, 0)

                # store split info, create children and continue training them if there's data left to split
                self.best_hyperplane_normal = optimization_function.best_hyperplane_normal
                self.best_hyperplane_origin = optimization_function.best_hyperplane_origin

                self.child1 = self.child_type(self.partition_prior, prior_child1, self.optimizer, self.level + 1)
                self.child2 = self.child_type(self.partition_prior, prior_child2, self.optimizer, self.level + 1)

                if X1.shape[0] > 1:
                    self.child1._fit(X1, y1, delta, verbose, feature_names)
                else:
                    self.child1.posterior = self._compute_posterior(y1)

                if X2.shape[0] > 1:
                    self.child2._fit(X2, y2, delta, verbose, feature_names)
                else:
                    self.child2.posterior = self._compute_posterior(y2)

        # compute posterior
        self.n_dim = X.shape[1]
        self.posterior = self._compute_posterior(y)

    def _compute_child1_and_child2_indices(self, X, dense):
        projections = X @ self.best_hyperplane_normal - np.dot(self.best_hyperplane_normal, self.best_hyperplane_origin)
        indices1 = np.where(projections < 0)[0]
        indices2 = np.where(projections >= 0)[0]

        return indices1, indices2

    def is_leaf(self):
        self._ensure_is_fitted()
        return self.best_hyperplane_normal is None

    def _prune(self):
        depth_and_leaves_start = self.depth_and_leaves()

        if self.is_leaf():
            return

        if self.child1.is_leaf() and self.child2.is_leaf():
            if self.child1._predict_leaf() == self.child2._predict_leaf():
                # same prediction (class if classification, value if regression) -> no need to split
                self.child1 = None
                self.child2 = None
                self.log_p_data_post_no_split = None
                self.log_p_data_post_best = None

                self.best_hyperplane_normal = None
                self.best_hyperplane_origin = None
        else:
            self.child1._prune()
            self.child2._prune()

        if depth_and_leaves_start != self.depth_and_leaves():
            # we did some pruning somewhere down this sub-tree -> prune again
            self._prune()

    def __str__(self):
        return self._str([], '\u2523', '\u2517', '\u2503', '\u2265', None)

    def _str(self, anchor, VERT_RIGHT, DOWN_RIGHT, BAR, GEQ, is_front_child):
        anchor_str = ''.join(' ' + a for a in anchor)
        s = ''
        if is_front_child is not None:
            s += anchor_str + ' {:5s}: '.format('front' if is_front_child else 'back')

        if self.is_leaf():
            s += 'y={}'.format(self._predict_leaf())
            if not self.is_regression:
                s += ', p(y)={}'.format(self._predict(None, predict_class=False)[0])
        else:
            s += 'HP(origin={}, normal={})'.format(self.best_hyperplane_origin, self.best_hyperplane_normal)

            # 'back' child (the child that is on the side of the hyperplane opposite to the normal vector, or projection < 0)
            s += '\n'
            anchor_child1 = [VERT_RIGHT] if len(anchor) == 0 else (anchor[:-1] + [(BAR if is_front_child else '  '), VERT_RIGHT])
            s += self.child1._str(anchor_child1, VERT_RIGHT, DOWN_RIGHT, BAR, GEQ, False)

            # 'front' child (the child that is on same side of the hyperplane as the normal vector, or projection >= 0)
            s += '\n'
            anchor_child2 = [DOWN_RIGHT] if len(anchor) == 0 else (anchor[:-1] + [(BAR if is_front_child else '  '), DOWN_RIGHT])
            s += self.child2._str(anchor_child2, VERT_RIGHT, DOWN_RIGHT, BAR, GEQ, True)
        return s
