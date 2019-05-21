# -*- coding: utf-8 -*-
#
#
# PyRates software framework for flexible implementation of neural
# network model_templates and simulations. See also:
# https://github.com/pyrates-neuroscience/PyRates
#
# Copyright (C) 2017-2018 the original authors (Richard Gast and
# Daniel Rose), the Max-Planck-Institute for Human Cognitive Brain
# Sciences ("MPI CBS") and contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#
# CITATION:
#
# Richard Gast and Daniel Rose et. al. in preparation

"""Contains wrapper classes for different backends that are needed by the parser module.

A new backend needs to implement the following methods

Methods
-------
__init__
run
add_var
add_op
add_layer

Currently supported backends:
- Tensorflow: TensorflowBackend.

"""

# external imports
import time as t
from typing import Optional, Dict, Callable, List, Union, Tuple, Any
import numpy as np
import tensorflow as tf
from copy import deepcopy

# meta infos
__author__ = "Richard Gast"
__status__ = "development"


#############################################
# basic classes for operators and variables #
#############################################

class PyRatesVar:
    def __init__(self, vtype: str, dtype: str, shape: tuple, value: Any, name: str, backend: Any) -> None:
        """

        Parameters
        ----------
        vtype
        dtype
        shape
        value
        name
        backend
        """

        # check whether necessary arguments were provided
        if all([arg is None for arg in [shape, value, dtype]]):
            raise ValueError('Either `value` or `shape` and `dtype` need to be provided')

        # get shape
        if not shape:
            shape = value.shape if hasattr(value, 'shape') else ()

        # get data type
        if not dtype:
            dtype = value.dtype if hasattr(value, 'dtype') else type(value)
        dtype = dtype.name if hasattr(dtype, 'name') else str(dtype)
        if dtype in backend.dtypes:
            dtype = backend.dtypes[dtype]
        else:
            for dtype_tmp in backend.dtypes:
                if dtype_tmp in dtype:
                    dtype = backend.dtypes[dtype_tmp]
                    break
            else:
                raise ValueError(f'Invalid data type: {dtype}. Check documentation of the backend wrapper in use for '
                                 'valid data types.')

        # get value
        if value is None:
            value = np.zeros(shape=shape, dtype=dtype)
        elif not hasattr(value, 'shape'):
            value = np.zeros(shape=shape, dtype=dtype) + value

        # set attributes
        self.vtype = vtype
        self.dtype = dtype
        self.shape = tuple(shape)
        self.value = value
        self.name = name
        self.backend = backend

    def eval(self):
        return self.backend.eval_var(self.name)


class PyRatesOp:
    def __init__(self, op: Any, name: str, *args, **kwargs) -> None:
        """

        Parameters
        ----------
        op
        backend
        args
        kwargs
        """

        try:
            op_tmp = op(*args, **kwargs)
        except TypeError:
            try:
                args = (list(args),)
                op_tmp = op(*args, **kwargs)
            except TypeError:
                # TODO: replace this with more generic way of handling args and kwargs
                args = list(args)
                arg_tmp = args.pop(-1)
                args = (args, arg_tmp)
                try:
                    op_tmp = op(*args, **kwargs)
                except TypeError:
                    raise TypeError(f'Invalid arguments to operator: {name}. Check the documentation of the backend in '
                                    f'use for the valid argument structure to this operator.')

        # set attributes
        self.op = op
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.shape = op_tmp.shape if hasattr(op_tmp, 'shape') else ()
        self.dtype = op_tmp.dtype if hasattr(op_tmp, 'dtype') else type(op_tmp)

    def eval(self):
        return self.op(*self.args, **self.kwargs)


###########################
# backend wrapper classes #
###########################

class TensorflowBackend(tf.Graph):
    """Wrapper to tensorflow.

    Parameters
    ----------
    ops
        Additional operations this backend instance can perform, defined as key-value pairs.
    dtypes
        Additional data-types this backend instance can use, defined as key-value pairs.
    use_device
        Default default_device on which to place variables and operations.

    """

    def __init__(self,
                 ops: Optional[Dict[str, Callable]] = None,
                 dtypes: Optional[Dict[str, object]] = None,
                 use_device: str = 'cpu'
                 ) -> None:
        """Instantiates tensorflow backend, i.e. a tensorflow graph.
        """

        super().__init__()
        if use_device == 'cpu':
            device = '/cpu:0'
        elif use_device == 'gpu':
            device = '/gpu:0'
        else:
            device = use_device
        self.default_device = device

        # define operations and datatypes of the backend
        ################################################

        # base math operations
        self.ops = {"+": tf.add,
                    "-": tf.subtract,
                    "*": tf.multiply,
                    "/": tf.divide,
                    "%": tf.mod,
                    "^": tf.pow,
                    "**": tf.pow,
                    "@": tf.matmul,
                    ".T": tf.transpose,
                    ".I": tf.matrix_inverse,
                    ">": tf.greater,
                    "<": tf.less,
                    "==": tf.equal,
                    "!=": tf.not_equal,
                    ">=": tf.greater_equal,
                    "<=": tf.less_equal,
                    "=": tf.assign,
                    "+=": tf.assign_add,
                    "cond": tf.cond,
                    "neg": lambda x: -x,
                    "sin": tf.sin,
                    "cos": tf.cos,
                    "tan": tf.tan,
                    "atan": tf.atan,
                    "abs": tf.abs,
                    "sqrt": tf.sqrt,
                    "sq": tf.square,
                    "exp": tf.exp,
                    "max": tf.maximum,
                    "min": tf.minimum,
                    "argmax": tf.arg_max,
                    "argmin": tf.arg_min,
                    "round": tf.round,
                    "roundto": lambda x, y: tf.round(x * 10**y) / 10**y,
                    "sum": tf.reduce_sum,
                    "mean": tf.reduce_mean,
                    "concat": tf.concat,
                    "reshape": tf.reshape,
                    "shape": tf.shape,
                    "dtype": tf.keras.backend.dtype,
                    'squeeze': tf.squeeze,
                    "roll": tf.roll,
                    "cast": tf.cast,
                    "randn": tf.random_normal,
                    "ones": tf.ones,
                    "zeros": tf.zeros,
                    "range": tf.range,
                    "softmax": tf.nn.softmax,
                    "sigmoid": tf.sigmoid,
                    "tanh": tf.tanh,
                    "gather": tf.gather,
                    "gather_nd": tf.gather_nd,
                    "scatter": tf.scatter_nd,
                    "scatter_update": tf.scatter_update,
                    "scatter_add": tf.scatter_nd_add,
                    "mask": tf.boolean_mask,
                    "stack": tf.stack,
                    "pstack": tf.parallel_stack,
                    "group": tf.group,
                    "tuple": tf.tuple,
                    "no_op": no_op,
                    }
        if ops:
            self.ops.update(ops)

        self.dtypes = {"float16": tf.float16,
                       "float32": tf.float32,
                       "float64": tf.float64,
                       "int16": tf.int16,
                       "int32": tf.int32,
                       "int64": tf.int64,
                       "uint16": tf.uint16,
                       "uint32": tf.uint32,
                       "uint64": tf.uint64,
                       "complex64": tf.complex64,
                       "complex128": tf.complex128,
                       "bool": tf.bool
                       }
        if dtypes:
            self.dtypes.update(dtypes)

        self.existing_scopes = {}

    def run(self,
            steps: int,
            ops: Union[tf.Operation, List[tf.Operation]],
            inputs: List[dict],
            outputs: Dict[str, tf.Variable],
            sampling_steps: Optional[int] = None,
            sampling_ops: Optional[Union[tf.Operation, List[tf.Operation]]] = None,
            out_dir: Optional[str] = None,
            profile: Optional[str] = None
            ) -> Union[Dict[str, tf.Variable], Tuple[dict, float, float]]:
        """Executes all operations in tensorflow graph for a given number of steps.

        Parameters
        ----------
        steps
            Number of graph evaluations.
        ops
            Graph operations to evaluate.
        inputs
            Inputs fed into the graph.
        outputs
            Variables in the graph to store the history from.
        sampling_steps
            Number of graph execution steps to combine into a single output step.
        sampling_ops
            Graph operations for output storage.
        out_dir
            Directory to write the session log into.
        profile
            Can be used to extract information about graph execution time and memory load. Can be:
            - `t` for returning the total graph execution time.
            - `m` for returning the peak memory consumption during graph excecution.
            - `mt` or `tm` for both

        Returns
        -------
        Union[Dict[str, tf.Variable], Tuple[dict, float, float]]
            If `profile` was requested, a tuple is returned that contains
                1) the results dictionary
                2) the simulation time if `t` was requested, else None.
                3) the peak memory consumption if `m` was requested, else None.
            If not, only the results dictionary is returned which contains a numpy array with results for each
            output key that was provided via `outputs`.

        """

        # initializations
        #################

        # initialize session log
        if out_dir:
            writer = tf.summary.FileWriter(out_dir, graph=self)

        # initialize profiler
        if profile is None:
            profile = ''
        if 'm' in profile:
            meta = tf.RunMetadata()
            time_and_memory = tf.profiler.ProfileOptionBuilder.time_and_memory()
        if 't' in profile:
            t0 = t.time()

        # graph execution
        #################

        # start session
        with tf.Session(graph=self, config=tf.ConfigProto(allow_soft_placement=True)) as sess:

            # initialize variables on graph
            sess.run(tf.global_variables_initializer())

            # simulate backend behavior for each time-step
            if 'm' in profile:

                # in profiler-mode
                for step in range(steps):
                    if step % sampling_steps == 0:
                        sess.run(sampling_ops, inputs[step], run_metadata=meta,
                                 options=tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE))
                    else:
                        sess.run(ops, inputs[step], run_metadata=meta,
                                 options=tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE))
            else:

                # in non-profiler mode
                for step in range(steps):
                    if step % sampling_steps == 0:
                        sess.run(sampling_ops, inputs[step])
                    else:
                        sess.run(ops, inputs[step])

            # output storage and clean-up
            #############################

            # store output variables in output dictionary
            for key, var in outputs.items():
                outputs[key] = var.eval(sess)

            # store profiling results
            if 't' in profile:
                sim_time = t.time() - t0
            else:
                sim_time = 0.
            if 'm' in profile:
                peak_memory = tf.profiler.profile(graph=self, run_meta=meta, cmd='op', options=time_and_memory
                                                  ).total_peak_bytes / 1e6
            else:
                peak_memory = 0.

            # close session stuff
            if out_dir:
                writer.close()
            sess.close()

        if profile:
            return outputs, sim_time, peak_memory
        return outputs

    def add_var(self,
                vtype: str,
                name: str,
                value: Optional[Any] = None,
                shape: Optional[Union[tuple, list, tf.TensorShape]] = None,
                dtype: Optional[Union[str, tf.dtypes.DType]] = None,
                **kwargs
                ) -> Union[tf.Variable, tf.Tensor]:
        """Adds a variable to the backend.

        Parameters
        ----------
        vtype
            Variable type. Can be
                - `state_var` for variables that can change over time.
                - `constant` for non-changing variables.
                - `placeholder` for variables with a value unknown during initialization.
        name
            Name of the variable.
        value
            Value of the variable. Not needed for placeholders.
        shape
            Shape of the variable.
        dtype
            Datatype of the variable.
        kwargs
            Additional keyword arguments passed to the tensorflow functions.

        Returns
        -------
        Union[tf.Variable, tf.Tensor]
            Handle for the tensorflow variable.

        """

        # processs input arguments
        ##########################

        # extract variable scope
        scope, reuse = self._get_scope(kwargs.pop('scope', None))

        # extract graph dependencies
        dependencies = kwargs.pop('dependencies', None)

        # set the default_device
        device = kwargs.pop('device', self.default_device)

        # check whether necessary arguments were provided
        if all([arg is None for arg in [shape, value, dtype]]):
            raise ValueError('Either `value` or `shape` and `dtype` need to be provided')

        # set shape, data-type and value
        if shape is None:
            shape = value.shape
        if dtype is None:
            dtype = value.dtype
        if value is None:
            value = np.zeros(shape, dtype=dtype.as_numpy_dtype)

        # create variable
        #################

        with tf.device(device):
            with self.as_default():
                with scope as sc:
                    with tf.control_dependencies(dependencies):

                        if reuse:

                            # create variable under existing scope
                            with tf.name_scope(sc.original_name_scope):
                                return self._create_var(vtype, name, value, shape, dtype, **kwargs)

                        else:

                            # create variable under new scope
                            return self._create_var(vtype, name, value, shape, dtype, **kwargs)

    def add_op(self,
               op: str,
               *args,
               **kwargs
               ) -> tf.Operation:
        """Add operation to the backend.

        Parameters
        ----------
        op
            Key of the operation. Needs to be a key of `TensorflowGraph.ops`
        args
            Positional arguments to be passed to the operation.
        kwargs
            Keyword arguments to be passed to the operation.

        Returns
        -------
        tf.Operation
            Handle for the tensorflow operation.

        """

        # process input arguments
        #########################

        # extract scope
        scope, reuse = self._get_scope(kwargs.pop('scope', None))

        # extract graph dependencies
        dependencies = kwargs.pop('dependencies', None)

        # set the default_device
        device = kwargs.pop('device', self.default_device)

        # extract additional infos
        assign_to_var = kwargs.pop('assign_to_var', False)

        # create operation
        ##################

        with tf.device(device):
            with self.as_default():
                with scope as sc:
                    with tf.control_dependencies(dependencies):

                        if reuse:

                            # create operation under existing scope
                            with tf.name_scope(sc.original_name_scope):
                                return self._create_op(op, assign_to_var, *args, **kwargs)

                        else:

                            # create operation under new scope
                            return self._create_op(op, assign_to_var, *args, **kwargs)

    def add_layer(self,
                  ops: List[tf.Operation],
                  *args,
                  **kwargs
                  ) -> List[tf.Operation]:
        """Adds a layer of operations to the backend using `tensorflow.tuple`.

        Parameters
        ----------
        ops
            All tensorflow operations that should be part of this layer.
        args
            Additional positional arguments to be passed to `tensorflow.tuple`.
        kwargs
            Additional keyword arguments to be passed to `tensorflow.tuple`.

        Returns
        -------
        List[tf.Operation]
            List of tensorflow operations with dependencies added (layer operations will all be evaluated before
            any layer operation can be used in successive layers.)

        """

        # process input arguments
        #########################

        dependencies = kwargs.pop('dependencies', None)
        scope, reuse = self._get_scope(kwargs.pop('scope', None))
        device = kwargs.pop('device', self.default_device)

        # create layer
        ##############

        with tf.device(device):
            with self.as_default():
                with scope as sc:
                    with tf.control_dependencies(dependencies):
                        if reuse:
                            with tf.name_scope(sc.original_name_scope):
                                return tf.tuple(ops, *args, **kwargs)
                        else:
                            return tf.tuple(ops, *args, **kwargs)

    def clear(self):
        """Resets all tensorflow operations on the graph.
        """
        tf.reset_default_graph()

    def _create_op(self, op: str, assign_to_var: bool, *args, **kwargs) -> Union[tf.Operation, tf.Variable]:
        """

        Parameters
        ----------
        op
            Key of the operation.
        assign_to_var
            If true, new variable will be created and result of op will be assigned to it.
        args
            Positional arguments to be passed to the tensorflow function.
        kwargs
            Keyword argumetns to be passed to the tensorflow function.

        Returns
        -------
        Union[tf.Operation, tf.Variable]
            Result of the tensorflow operation.

        """

        try:
            tf_op = self.ops[op](*args, **kwargs)
        except TypeError:
            try:
                tf_op = self.ops[op](list(args), **kwargs)
            except TypeError:
                # TODO: replace this with more generic way of handling args and kwargs
                args = list(args)
                arg_tmp = args.pop(-1)
                tf_op = self.ops[op](args, arg_tmp, **kwargs)

        # either assign result to new variable and return that variable or return result
        if assign_to_var:
            var = self.add_var(vtype='state_var', name=tf_op.name.split('/')[-1] + ['_tmp'],
                               value=np.zeros(tf_op.shape, dtype=tf_op.dtype.as_numpy_dtype))
            return var.assign(tf_op)
        else:
            return tf_op

    @staticmethod
    def _create_var(vtype: str,
                    name: str,
                    value: Optional[Any] = None,
                    shape: Optional[Union[tuple, list, tf.TensorShape]] = None,
                    dtype: Optional[Union[str, tf.dtypes.DType]] = None,
                    **kwargs
                    ) -> Union[tf.Variable, tf.Tensor]:
        """Instantiates new variable in backend.

        Parameters
        ----------
        vtype
            Variable type. Can be
                - `state_var` for variables that can change over time.
                - `constant` for non-changing variables.
                - `placeholder` for variables with a value unknown during initialization.
        name
            Name of the variable.
        value
            Value of the variable. Not needed for placeholders.
        shape
            Shape of the variable.
        dtype
            Datatype of the variable.
        kwargs
            Additional keyword arguments passed to the tensorflow functions.

        Returns
        -------
        Union[tf.Variable, tf.Tensor]
            Handle to the tensorflow variable.

        """

        if vtype == 'state_var':
            return tf.get_variable(name, shape, dtype, initializer=tf.constant_initializer(value), **kwargs)
        elif vtype == 'constant':
            return tf.constant(value, dtype, shape, name, **kwargs)
        elif vtype == 'placeholder':
            return tf.placeholder(dtype, shape, name, **kwargs)
        else:
            raise ValueError(f'`Type` is {vtype} but needs to be set to `state_var`, `constant` or '
                             f'`placeholder`.')

    def _get_scope(self, scope: str):
        """

        Parameters
        ----------
        scope
            Name of the name scope.

        Returns
        -------
        str
            Existing or new name scope.

        """

        with self.as_default():
            if scope is None:
                return tf.variable_scope(tf.get_variable_scope(), reuse=tf.AUTO_REUSE), True
            if scope not in self.existing_scopes.keys():
                self.existing_scopes[scope] = True
            return tf.variable_scope(scope, reuse=tf.AUTO_REUSE), self.existing_scopes[scope]

    def _broadcast(self, op: str, op1: Any, op2: Any, return_ops: bool = False, **kwargs
                   ) -> Union[tuple, Any]:
        """Tries to match the shapes of op1 and op2 such that op can be applied. Then applies op to op1 and op2.

        Parameters
        ----------
        op
            Name/key of the backend operation.
        op1
            First argument to the operation.
        op2
            Second argument to the operation.
        return_ops
            If true, the adjusted arguments (op1 and op2) are returned.
        kwargs
            Additional keyword arguments to be passed to the backend.

        Returns
        -------
        tp.Union[tuple, tp.Any]
            Output of op applied to op1 and op2. If return_ops, op1 and op2 are also returned.

        """

        # get key and value of ops if they are dicts
        if type(op1) is dict:
            (op1_key, op1_val), = op1.items()
        else:
            op1_val = op1
            op1_key = None
        if type(op2) is dict:
            (op2_key, op2_val), = op2.items()
        else:
            op2_val = op2
            op2_key = None

        if not self.compare_shapes(op1_val, op2_val):

            # try removing singleton dimensions from op1/op2
            op1_val_tmp, op2_val_tmp = self.match_shapes(op1_val, op2_val, adjust_second=True, assign=op == self.assign)
            if not self.compare_shapes(op1_val_tmp, op2_val_tmp):
                op1_val_tmp, op2_val_tmp = self.match_shapes(op1_val_tmp, op2_val_tmp, adjust_second=False,
                                                             assign=op == self.assign)
            if self.compare_shapes(op1_val_tmp, op2_val_tmp):
                op1_val, op2_val = op1_val_tmp, op2_val_tmp

        try:

            # try applying the operation with matched shapes
            new_op = self.apply_op(op, op1_val, op2_val, op1_key, op2_key, **kwargs)

        except TypeError:

            # try to re-cast the data-types of op1/op2
            try:
                op2_val_tmp = self.backend.add_op('cast', op2_val, op1_val.dtype, **self.parser_kwargs)
                new_op = self.apply_op(op, op1_val, op2_val_tmp, op1_key, op2_key, **kwargs)
            except TypeError:
                op1_val_tmp = self.backend.add_op('cast', op1_val, op2_val.dtype, **self.parser_kwargs)
                new_op = self.apply_op(op, op1_val_tmp, op2_val, op1_key, op2_key, **kwargs)

        except ValueError:

            # try to match additional keyword arguments to shape of op1
            for key, var in kwargs.items():
                if hasattr(var, 'shape'):
                    _, kwargs[key] = self.match_shapes(op1_val, var, adjust_second=True, assign=op == self.assign)
            new_op = self.apply_op(op, op1_val, op2_val, op1_key, op2_key, **kwargs)

        if return_ops:
            return new_op, op1_val, op2_val
        return new_op

    def _match_shapes(self, op1: Any, op2: Any, adjust_second: bool = True, assign: bool = False) -> tuple:
        """Re-shapes op1 and op2 such that they can be combined via mathematical operations.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.
        assign
            If true, the re-shaped operators will be assigned to new variables. Else, the manipulation will be performed
            in place.
        adjust_second
            If true, the second operator will be re-shaped according to the shape of the first operator. If false,
            it will be done the other way around.

        Returns
        -------
        tuple
            The re-shaped operators.

        """

        if adjust_second:

            if len(op2.shape) == 0 and len(op1.shape) > 0 and assign:

                # create array of zeros and fill it with op2
                op2 = self.backend.add_op('+', self.backend.add_op("zeros", op1.shape, op1.dtype), op2)

            elif (len(op1.shape) > len(op2.shape)) and (1 in op1.shape) and (len(op2.shape) > 0):

                # reshape op2 to match the shape of op1
                target_shape = op1.shape
                idx = list(target_shape).index(1)
                if idx == 0:
                    op2 = self.backend.add_op('reshape', op2, [1, op2.shape[0]], **self.parser_kwargs)
                else:
                    op2 = self.backend.add_op('reshape', op2, [op2.shape[0], 1], **self.parser_kwargs)

            elif (len(op2.shape) > len(op1.shape) and 1 in op2.shape) or \
                    (len(op1.shape) == 2 and len(op2.shape) == 2 and op1.shape[1] != op2.shape[0] and 1 in op2.shape):

                # cut singleton dimension from op2
                idx = list(op2.shape).index(1)
                op2 = self.backend.add_op('squeeze', op2, idx, **self.parser_kwargs)

        else:

            if len(op1.shape) == 0 and len(op2.shape) > 0 and assign:

                # create array of zeros and fill it with op2
                op1 = self.backend.add_op('+', self.backend.add_op("zeros", op2.shape, op2.dtype, op1))

            elif (len(op2.shape) > len(op1.shape)) and (1 in op2.shape) and (len(op1.shape) > 0):

                # reshape op2 to match the shape of op1
                target_shape = op2.shape
                idx = list(target_shape).index(1)
                if idx == 0:
                    op1 = self.backend.add_op('reshape', op1, [1, op1.shape[0]], **self.parser_kwargs)
                else:
                    op1 = self.backend.add_op('reshape', op1, [op1.shape[0], 1], **self.parser_kwargs)

            elif len(op1.shape) > len(op2.shape) and 1 in op1.shape or \
                    (len(op1.shape) == 2 and len(op2.shape) == 2 and op1.shape[1] != op2.shape[0] and 1 in op1.shape):

                # cut singleton dimension from op2
                idx = list(op1.shape).index(1)
                op1 = self.backend.add_op('squeeze', op1, idx, **self.parser_kwargs)

        return op1, op2

    @staticmethod
    def _compare_shapes(op1: Any, op2: Any) -> bool:
        """Checks whether the shapes of op1 and op2 are compatible with each other.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.

        Returns
        -------
        bool
            If true, the shapes of op1 and op2 are compatible.

        """

        if hasattr(op1, 'shape') and hasattr(op2, 'shape'):
            if op1.shape == op2.shape:
                return True
            elif len(op1.shape) > 1 and len(op2.shape) > 1:
                return True
            else:
                return False
        else:
            return True

    @staticmethod
    def _compare_dtypes(op1: Any, op2: Any) -> bool:
        """Checks whether the data types of op1 and op2 are compatible with each other.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.

        Returns
        -------
        bool
            If true, the data types of op1 and op2 are compatible.

        """

        if op1.dtype == op2.dtype:
            return True
        elif op1.dtype.name in op2.dtype.name:
            return True
        elif op2.dtype.name in op1.dtype.name:
            return True
        elif op1.dtype.base_dtype == op2.dtype.base_dtype:
            return True
        else:
            return False


# class KerasBackend(tf.keras.models.Model):
#     """Expression parser that transforms expression into keras operations on a tensorflow graph.
#
#     Parameters
#     ----------
#     expr_str
#         See docstring of `ExpressionParser`.
#     args
#         See docstring of `ExpressionParser`. Each variable in args needs to be a dictionary with key-value pairs for:
#             - `var`: contains the tensorflow variable.
#             - `dependency`: Boolean. If True, the expression needs to wait for this variable to be calculated/updated
#                before being evaluated.
#     lhs
#         See docstring of `ExpressionParser`.
#     tf_graph
#         Instance of `tensorflow.Graph`. Mathematical expression will be parsed into this graph.
#
#     Attributes
#     ----------
#     tf_graph
#         Instance of `tensorflow.Graph` containing a graph-representation of `expr_str`.
#     ops
#         Dictionary containing all mathematical operations available for this parser and their syntax. These include:
#             - addition: `+`
#             - subtraction: `-`
#             - multiplication: `*`
#             - division: `/`
#             - modulo: `%`
#             - exponentiation: `^`
#             - matrix multiplication: `@`
#             - matrix transposition: `.T`
#             - matrix inversion: `.I`
#             - logical greater than: `>`
#             - logical less than: `<`
#             - logical equal: `==`
#             - logical unequal: `!=`
#             - logical greater or equal: `>=`
#             - logical smaller or equal: `<=`
#     funcs
#         Dicionary containing all additional functions available for this parser and their syntax. These include:
#             - sinus: `sin()`.
#             - cosinus: `cos()`.
#             - tangens: `tan()`.
#             - absolute: `abs()`.
#             - maximum: `max()`
#             - minimum: `min()`
#             - index of maximum: `argmax()`
#             - index of minimum: `argmin()`
#             - round to next integer: `round()`. Tensorflow name: `tensorflow.to_int32()`.
#             - round to certain decimal point: `roundto()`. Custom function using `tensorflow.round()`. Defined in
#               `pyrates.parser.parser.py`.
#             - sum over dimension(s): `sum()`. Tensorflow name: `reduce_sum()`.
#             - Concatenate multiples of tensor over certain dimension: `tile()`.
#             - Reshape tensor: `reshape()`.
#             - Cut away dimensions of size 1: `squeeze()`.
#             - Cast variable to data-type: `cast()`.
#             - draw random variable from standard normal distribution: `randn()`.
#               Tensorflow name: `tensorflow.random_normal`.
#             - Create array filled with ones: `ones()`.
#             - Create array filled with zeros: `zeros()`.
#             - Apply softmax function to variable: `softmax()`. Tensorflow name: `tensorflow.nn.softmax()`.
#             - Apply boolean mask to array: `boolean_mask()`.
#             - Create new array with non-zero entries at certain indices: `scatter()`.
#               Tensorflow name: `tensorflow.scatter_nd`
#             - Add values to certain entries of tensor: 'scatter_add()'. Tensorflow name: `tensorflow.scatter_nd_add`.
#             - Update values of certain tensor entries: `scatter_update()`.
#               Tensorflow name: `tensorflow.scatter_nd_update`.
#             - Apply tensor as index to other tensor: `array_idx()`. Tensorflow name: `tensorflow.gather_nd`.
#             - Get variable from tensorflow graph or create new variable: `new_var()`:
#               Tensorflow name: `tensorflow.get_variable`.
#         For a detailed documentation of how to use these functions, see the tensorflow Python API.
#     dtypes
#         Dictionary containing all data-types available for this parser. These include:
#             - float16, float32, float64
#             - int16, int32, int64
#             - uint16, uint32, uint64
#             - complex64, complex128,
#             - bool
#         All of those data-types can be used inside a mathematical expression instead of using `cast()`
#         (e.g. `int32(3.631)`.
#     For all other attributes, see docstring of `ExpressionParser`.
#
#     Methods
#     -------
#     See docstrings of `ExpressionParser` methods.
#
#     Examples
#     --------
#
#     References
#     ----------
#
#     """
#
#     def __init__(self, expr_str: str, args: dict, backend: tf.keras.layers.Layer, lhs: bool = False) -> None:
#         """Instantiates keras expression parser.
#         """
#
#         # call super init
#         #################
#
#         super().__init__(expr_str=expr_str, args=args, backend=backend, lhs=lhs)
#
#         # define operations and functions
#         #################################
#
#         # base math operations
#         ops = {"+": tf.keras.layers.Lambda(lambda x: x[0] + x[1]),
#                "-": tf.keras.layers.Lambda(lambda x: x[0] - x[1]),
#                "*": tf.keras.layers.Lambda(lambda x: x[0] * x[1]),
#                "/": tf.keras.layers.Lambda(lambda x: x[0] / x[1]),
#                "%": tf.keras.layers.Lambda(lambda x: x[0] % x[1]),
#                "^": tf.keras.layers.Lambda(lambda x: tf.keras.backend.pow(x[0], x[1])),
#                "@": tf.keras.layers.Lambda(lambda x: tf.keras.backend.dot(x[0], x[1])),
#                ".T": tf.keras.layers.Lambda(lambda x: tf.keras.backend.transpose(x)),
#                ".I": tf.keras.layers.Lambda(lambda x: tf.matrix_inverse(x)),
#                ">": tf.keras.layers.Lambda(lambda x: tf.keras.backend.greater(x[0], x[1])),
#                "<": tf.keras.layers.Lambda(lambda x: tf.keras.backend.less(x[0], x[1])),
#                "==": tf.keras.layers.Lambda(lambda x: tf.keras.backend.equal(x[0], x[1])),
#                "!=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.not_equal(x[0], x[1])),
#                ">=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.greater_equal(x[0], x[1])),
#                "<=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.less_equal(x[0], x[1])),
#                "=": tf.keras.backend.update
#                }
#         self.ops.update(ops)
#
#         # additional functions
#         funcs = {"sin": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sin(x)),
#                  "cos": tf.keras.layers.Lambda(lambda x: tf.keras.backend.cos(x)),
#                  "tanh": tf.keras.layers.Lambda(lambda x: tf.keras.backend.tanh(x)),
#                  "abs": tf.keras.layers.Lambda(lambda x: tf.keras.backend.abs(x)),
#                  "sqrt": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sqrt(x)),
#                  "sq": tf.keras.layers.Lambda(lambda x: tf.keras.backend.square(x)),
#                  "exp": tf.keras.layers.Lambda(lambda x: tf.keras.backend.exp(x)),
#                  "max": tf.keras.layers.Lambda(lambda x: tf.keras.backend.max(x)),
#                  "min": tf.keras.layers.Lambda(lambda x: tf.keras.backend.min(x)),
#                  "argmax": tf.keras.layers.Lambda(lambda x: tf.keras.backend.argmax(x)),
#                  "argmin": tf.keras.layers.Lambda(lambda x: tf.keras.backend.argmin(x)),
#                  "round": tf.keras.layers.Lambda(lambda x: tf.keras.backend.round(x)),
#                  "roundto": tf.keras.layers.Lambda(lambda x: tf.keras.backend.round(x[0] * 10**x[1]) / 10**x[1]),
#                  "sum": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sum(x[0], *x[1])
#                                                if type(x) is list else tf.keras.backend.sum(x)),
#                  "concat": tf.keras.layers.Lambda(lambda x: tf.keras.backend.concatenate(x[0], *x[1])
#                                                   if type(x[0]) is list else tf.keras.backend.concatenate(x)),
#                  "reshape": tf.keras.layers.Lambda(lambda x: tf.keras.backend.reshape(x[0], x[1])
#                                                    if type(x) is list else tf.keras.backend.reshape(x)),
#                  "shape": tf.keras.backend.shape,
#                  "dtype": tf.keras.backend.dtype,
#                  'squeeze': tf.keras.layers.Lambda(lambda x: tf.keras.backend.squeeze(x[0], x[1])
#                                                    if type(x) is list else tf.keras.backend.squeeze(x[0], -1)),
#                  "cast": tf.keras.layers.Lambda(lambda x: tf.keras.backend.cast(x[0], x[1])),
#                  "randn": tf.keras.layers.Lambda(lambda x: tf.keras.backend.random_normal(x[0], *x[1])
#                                                  if "Tensor" in str(type(x[0]))
#                                                  else tf.keras.backend.random_normal(x)),
#                  "ones": tf.keras.layers.Lambda(lambda x: tf.keras.backend.ones(x[0], x[1])
#                                                 if "Tensor" in str(type(x[0]))
#                                                 else tf.keras.backend.ones(x)),
#                  "zeros": tf.keras.layers.Lambda(lambda x: tf.keras.backend.zeros(x[0], x[1])
#                                                  if "Tensor" in str(type(x[0]))
#                                                  else tf.keras.backend.zeros(x)),
#                  "softmax": tf.keras.layers.Lambda(lambda x: tf.keras.activations.softmax(x[0], *x[1])
#                                                    if type(x[0]) is list else tf.keras.activations.softmax(x)),
#                  "gather": tf.keras.layers.Lambda(lambda x: tf.gather_nd(x[0], x[1])),
#                  "mask": tf.keras.layers.Masking,
#                  "lambda": tf.keras.layers.Lambda
#                  }
#         self.funcs.update(funcs)
#
#         dtypes = {"float16": tf.float16,
#                   "float32": tf.float32,
#                   "float64": tf.float64,
#                   "int16": tf.int16,
#                   "int32": tf.int32,
#                   "int64": tf.int64,
#                   "uint16": tf.uint16,
#                   "uint32": tf.uint32,
#                   "uint64": tf.uint64,
#                   "complex64": tf.complex64,
#                   "complex128": tf.complex128,
#                   "bool": tf.bool
#                   }
#         self.dtypes.update(dtypes)
#
#     def add_variable(self, name, shape, dtype=None, initializer=None,
#                    regularizer=None, trainable=True, constraint=None):
#         pass


class NumpyBackend(object):
    """Wrapper to numpy.

    Parameters
    ----------
    ops
        Additional operations this backend instance can perform, defined as key-value pairs.
    dtypes
        Additional data-types this backend instance can use, defined as key-value pairs.

    """

    def __init__(self,
                 ops: Optional[Dict[str, Callable]] = None,
                 dtypes: Optional[Dict[str, object]] = None,
                 ) -> None:
        """Instantiates tensorflow backend, i.e. a tensorflow graph.
        """

        super().__init__()

        # define operations and datatypes of the backend
        ################################################

        # base math operations
        self.ops = {"+": lambda x, y: np.add(x.eval(), y.eval()),
                    "-": lambda x, y: np.subtract(x.eval(), y.eval()),
                    "*": lambda x, y: np.multiply(x.eval(), y.eval()),
                    "/": lambda x, y: np.divide(x.eval(), y.eval()),
                    "%": lambda x, y: np.mod(x.eval(), y.eval()),
                    "^": lambda x, y: np.power(x.eval(), y.eval()),
                    "**": lambda x, y: np.float_power(x.eval(), y.eval()),
                    "@": lambda x, y: np.dot(x.eval(), y.eval()),
                    ".T": lambda x: np.transpose(x.eval()),
                    ".I": lambda x: np.invert(x.eval()),
                    ">": lambda x, y: np.greater(x.eval(), y.eval()),
                    "<": lambda x, y: np.less(x.eval(), y.eval()),
                    "==": lambda x, y: np.equal(x.eval(), y.eval()),
                    "!=": lambda x, y: np.not_equal(x.eval(), y.eval()),
                    ">=": lambda x, y: np.greater_equal(x.eval(), y.eval()),
                    "<=": lambda x, y: np.less_equal(x.eval(), y.eval()),
                    "=": numpy_assign,
                    "+=": numpy_assign_add,
                    "neg": lambda x: neg_one() * x.eval(),
                    "sin": lambda x: np.sin(x.eval()),
                    "cos": lambda x: np.cos(x.eval()),
                    "tan": lambda x: np.tan(x.eval()),
                    "atan": lambda x: np.arctan(x.eval()),
                    "abs": lambda x: np.abs(x.eval()),
                    "sqrt": lambda x: np.sqrt(x.eval()),
                    "sq": lambda x: np.square(x.eval()),
                    "exp": lambda x: np.exp(x.eval()),
                    "max": lambda x: np.max(x.eval()) if hasattr(x, 'eval') else np.max(x[0].eval(), *x[1:]),
                    "min": lambda x: np.min(x.eval()) if hasattr(x, 'eval') else np.min(x[0].eval(), *x[1:]),
                    "argmax": lambda x: np.argmax(x.eval()) if hasattr(x, 'eval') else np.argmax(x[0].eval(), *x[1:]),
                    "argmin": lambda x: np.argmin(x.eval()) if hasattr(x, 'eval') else np.argmin(x[0].eval(), *x[1:]),
                    "round": lambda x: np.round(x.eval()),
                    "roundto": lambda x: np.round(x.eval()) if hasattr(x, 'eval') else np.round(x[0].eval(), *x[1:]),
                    "sum": lambda x: np.sum(x.eval()) if hasattr(x, 'eval') else np.sum(x[0].eval(), *x[1:]),
                    "mean": lambda x: np.mean(x.eval()) if hasattr(x, 'eval') else np.mean(x[0].eval(), *x[1:]),
                    "concat": lambda x: np.concatenate(x.eval()) if hasattr(x, 'eval') else np.concatenate(x[0].eval(), *x[1:]),
                    "reshape": lambda x: np.reshape(x.eval()) if hasattr(x, 'eval') else np.reshape(x[0].eval(), *x[1:]),
                    "shape": lambda x: np.shape(x.eval()),
                    "dtype": lambda x: np.dtype(x.eval()),
                    'squeeze': lambda x: np.squeeze(x.eval()) if hasattr(x, 'eval') else np.squeeze(x[0].eval(), *x[1:]),
                    "roll": lambda x: np.roll(x.eval()) if hasattr(x, 'eval') else np.roll(x[0].eval(), *x[1:]),
                    "cast": numpy_cast,
                    "randn": lambda x: np.random.randn(x.eval()) if hasattr(x, 'eval') else np.random.randn(x[0].eval(), *x[1:]),
                    "ones": np.ones,
                    "zeros": np.zeros,
                    "range": np.arange,
                    "softmax": lambda x: np.exp(x)/np.sum(np.exp(x)),
                    "sigmoid": numpy_sigmoid,
                    "tanh": np.tanh,
                    "gather": lambda x: x,
                    "gather_nd": lambda x: x,
                    "scatter": lambda x: x,
                    "scatter_update": scatter_update_numpy,
                    "scatter_add": lambda x: x,
                    "mask": lambda x, y: x*(y > 0.),
                    "stack": lambda x: x,
                    "pstack": lambda x: x,
                    "group": lambda x: x,
                    "tuple": lambda x: x,
                    "no_op": no_op,
                    }
        if ops:
            self.ops.update(ops)

        # base math operations for constant vars
        self.constant_ops_1 = {"+": lambda x, y: np.add(x, y),
                               "-": lambda x, y: np.subtract(x, y),
                               "*": lambda x, y: np.multiply(x, y),
                               "/": lambda x, y: np.divide(x, y),
                               "%": lambda x, y: np.mod(x, y),
                               "^": lambda x, y: np.power(x, y),
                               "**": lambda x, y: np.float_power(x, y),
                               "@": lambda x, y: np.dot(x, y),
                               ".T": lambda x: np.transpose(x),
                               ".I": lambda x: np.invert(x),
                               ">": lambda x, y: np.greater(x, y),
                               "<": lambda x, y: np.less(x, y),
                               "==": lambda x, y: np.equal(x, y),
                               "!=": lambda x, y: np.not_equal(x, y),
                               ">=": lambda x, y: np.greater_equal(x, y),
                               "<=": lambda x, y: np.less_equal(x, y),
                               "neg": lambda x: -x,
                               "sin": lambda x: np.sin(x),
                               "cos": lambda x: np.cos(x),
                               "tan": lambda x: np.tan(x),
                               "atan": lambda x: np.arctan(x),
                               "abs": lambda x: np.abs(x),
                               "sqrt": lambda x: np.sqrt(x),
                               "sq": lambda x: np.square(x),
                               "exp": lambda x: np.exp(x),
                               "max": lambda x: np.max(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.max(x),
                               "min": lambda x: np.min(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.min(x),
                               "argmax": lambda x: np.argmax(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.argmax(x),
                               "argmin": lambda x: np.argmin(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.max(x),
                               "round": lambda x: np.round(x),
                               "roundto": lambda x: np.round(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.round(x),
                               "sum": lambda x: np.sum(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.sum(x),
                               "mean": lambda x: np.mean(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.mean(x),
                               "concat": lambda x: np.concatenate(x[0], *x[1:]) if str(type(x)) in "tuplefloat" else np.concatenate(x),
                               "reshape": lambda x: np.reshape(x.eval()) if hasattr(x, 'eval') else np.reshape(x[0].eval(), *x[1:]),
                               "shape": lambda x: np.shape(x.eval()),
                               "dtype": lambda x: np.dtype(x.eval()),
                               'squeeze': lambda x: np.squeeze(x.eval()) if hasattr(x, 'eval') else np.squeeze(x[0].eval(), *x[1:]),
                               "roll": lambda x: np.roll(x.eval()) if hasattr(x, 'eval') else np.roll(x[0].eval(), *x[1:]),
                               "cast": numpy_cast,
                               "randn": lambda x: np.random.randn(x.eval()) if hasattr(x, 'eval') else np.random.randn(x[0].eval(), *x[1:]),
                               "ones": np.ones,
                               "zeros": np.zeros,
                               "range": np.arange,
                               "softmax": lambda x: np.exp(x) / np.sum(np.exp(x)),
                               "sigmoid": numpy_sigmoid_constant,
                               "tanh": np.tanh,
                               "gather": lambda x: x,
                               "gather_nd": lambda x: x,
                               "scatter": lambda x: x,
                               "scatter_update": lambda x: x,
                               "scatter_add": lambda x: x,
                               "mask": lambda x, y: x * (y > 0.),
                               "stack": lambda x: x,
                               "pstack": lambda x: x,
                               "group": lambda x: x,
                               "tuple": lambda x: x,
                               "no_op": no_op,
                               }
        # base math operations for constant vars
        self.constant_ops_2 = {"+": lambda x, y: np.add(x.eval(), y),
                               "-": lambda x, y: np.subtract(x.eval(), y),
                               "*": lambda x, y: np.multiply(x.eval(), y),
                               "/": lambda x, y: np.divide(x.eval(), y),
                               "%": lambda x, y: np.mod(x.eval(), y),
                               "^": lambda x, y: np.power(x.eval(), y),
                               "**": lambda x, y: np.float_power(x.eval(), y),
                               "@": lambda x, y: np.dot(x.eval(), y),
                               ">": lambda x, y: np.greater(x.eval(), y),
                               "<": lambda x, y: np.less(x.eval(), y),
                               "==": lambda x, y: np.equal(x.eval(), y),
                               "!=": lambda x, y: np.not_equal(x.eval(), y),
                               ">=": lambda x, y: np.greater_equal(x.eval(), y),
                               "<=": lambda x, y: np.less_equal(x.eval(), y),
                               "=": numpy_assign_const,
                               "+=": numpy_assign_add_const,
                               "max": lambda x: np.max(x[0].eval(), *x[1:]),
                               "min": lambda x: np.min(x[0].eval(), *x[1:]),
                               "argmax": lambda x: np.argmax(x[0].eval(), *x[1:]),
                               "argmin": lambda x: np.argmin(x[0].eval(), *x[1:]),
                               "roundto": lambda x: np.round(x[0].eval(), *x[1:]),
                               "sum": lambda x: np.sum(x[0].eval(), *x[1:]),
                               "mean": lambda x: np.mean(x[0].eval(), *x[1:]),
                               "concat": lambda x: np.concatenate(x[0].eval(), *x[1:]),
                               "reshape": lambda x: np.reshape(x[0].eval(), *x[1:]),
                               'squeeze': lambda x: np.squeeze(x[0].eval(), *x[1:]),
                               "roll": lambda x: np.roll(x[0].eval(), *x[1:]),
                               "cast": numpy_cast,
                               "randn": lambda x: np.random.randn(x[0].eval(), *x[1:]),
                               "ones": np.ones,
                               "zeros": np.zeros,
                               "range": np.arange,
                               "softmax": lambda x: np.exp(x) / np.sum(np.exp(x)),
                               "sigmoid": lambda x: 1 / (1 + np.exp(x)),
                               "tanh": np.tanh,
                               "gather": lambda x: x,
                               "gather_nd": lambda x: x,
                               "scatter": lambda x: x,
                               "scatter_update": scatter_update_numpy_const,
                               "scatter_add": lambda x: x,
                               "mask": lambda x, y: x * (y > 0.),
                               "stack": lambda x: x,
                               "pstack": lambda x: x,
                               "group": lambda x: x,
                               "tuple": lambda x: x,
                               "no_op": no_op,
                               }

        # base math operations for constant vars
        self.constant_ops_3 = {"+": lambda x, y: np.add(x, y.eval()),
                               "-": lambda x, y: np.subtract(x, y.eval()),
                               "*": lambda x, y: np.multiply(x, y.eval()),
                               "/": lambda x, y: np.divide(x, y.eval()),
                               "%": lambda x, y: np.mod(x, y.eval()),
                               "^": lambda x, y: np.power(x, y.eval()),
                               "**": lambda x, y: np.float_power(x, y.eval()),
                               "@": lambda x, y: np.dot(x, y.eval()),
                               ">": lambda x, y: np.greater(x, y.eval()),
                               "<": lambda x, y: np.less(x, y.eval()),
                               "==": lambda x, y: np.equal(x, y.eval()),
                               "!=": lambda x, y: np.not_equal(x, y.eval()),
                               ">=": lambda x, y: np.greater_equal(x, y.eval()),
                               "<=": lambda x, y: np.less_equal(x, y.eval())
                               }

        self.dtypes = {"float16": np.float16,
                       "float32": np.float32,
                       "float64": np.float64,
                       "int16": np.int16,
                       "int32": np.int32,
                       "int64": np.int64,
                       "uint16": np.uint16,
                       "uint32": np.uint32,
                       "uint64": np.uint64,
                       "complex64": np.complex64,
                       "complex128": np.complex128,
                       "bool": np.bool
                       }
        if dtypes:
            self.dtypes.update(dtypes)

        self.graph = {'vars': {}, 'ops': {}, 'layers': []}
        self.var_counter = {}
        self.op_counter = {}

    def run(self,
            steps: int,
            ops: Union[tf.Operation, List[tf.Operation]],
            inputs: List[dict],
            outputs: Dict[str, tf.Variable],
            sampling_steps: Optional[int] = None,
            sampling_ops: Optional[Union[tf.Operation, List[tf.Operation]]] = None,
            out_dir: Optional[str] = None,
            profile: Optional[str] = None
            ) -> Union[Dict[str, tf.Variable], Tuple[dict, float, float]]:
        """Executes all operations in tensorflow graph for a given number of steps.

        Parameters
        ----------
        steps
            Number of graph evaluations.
        ops
            Graph operations to evaluate.
        inputs
            Inputs fed into the graph.
        outputs
            Variables in the graph to store the history from.
        sampling_steps
            Number of graph execution steps to combine into a single output step.
        sampling_ops
            Graph operations for output storage.
        out_dir
            Directory to write the session log into.
        profile
            Can be used to extract information about graph execution time and memory load. Can be:
            - `t` for returning the total graph execution time.
            - `m` for returning the peak memory consumption during graph excecution.
            - `mt` or `tm` for both

        Returns
        -------
        Union[Dict[str, tf.Variable], Tuple[dict, float, float]]
            If `profile` was requested, a tuple is returned that contains
                1) the results dictionary
                2) the simulation time if `t` was requested, else None.
                3) the peak memory consumption if `m` was requested, else None.
            If not, only the results dictionary is returned which contains a numpy array with results for each
            output key that was provided via `outputs`.

        """

        # initializations
        #################

        # initialize session log
        if out_dir:
            # TODO : implement log files
            pass

        # initialize profiler
        if profile is None:
            profile = ''
        if 'm' in profile:
            # TODO: implement memory tracker
            time_and_memory = None
        if 't' in profile:
            t0 = t.time()

        self.compile()
        n_layers = len(self.graph['layers'])

        # graph execution
        #################

        # simulate backend behavior for each time-step
        if 'm' in profile:

            pass

        else:

            # in non-profiler mode
            if any(inputs):
                for step, inp in zip(range(steps), inputs):
                    if step % sampling_steps == 0:
                        self.eval(sampling_ops)
                    for key, val in inp.items():
                        self.graph['vars'][key].value = val
                    for l in range(n_layers):
                        self.eval_layer(l)
            else:
                for step in range(steps):
                    if step % sampling_steps == 0:
                        self.eval(sampling_ops)
                    for l in range(n_layers):
                        self.eval_layer(l)

        # output storage and clean-up
        #############################

        # store output variables in output dictionary
        for key, var in outputs.items():
            outputs[key] = var.eval()

        # store profiling results
        if 't' in profile:
            sim_time = t.time() - t0
        else:
            sim_time = 0.
        if 'm' in profile:
            peak_memory = 'much'
        else:
            peak_memory = 0.

        if profile:
            return outputs, sim_time, peak_memory
        return outputs

    def add_var(self,
                vtype: str,
                name: str,
                value: Optional[Any] = None,
                shape: Optional[Union[tuple, list, np.shape]] = None,
                dtype: Optional[Union[str, np.dtype]] = None,
                **kwargs
                ) -> PyRatesVar:
        """Adds a variable to the backend.

        Parameters
        ----------
        vtype
            Variable type. Can be
                - `state_var` for variables that can change over time.
                - `constant` for non-changing variables.
                - `placeholder` for variables with a value unknown during initialization.
        name
            Name of the variable.
        value
            Value of the variable. Not needed for placeholders.
        shape
            Shape of the variable.
        dtype
            Datatype of the variable.
        kwargs
            Additional keyword arguments passed to the tensorflow functions.

        Returns
        -------
        PyRatesVar
            Handle for the numpy variable.

        """

        # processs input arguments
        ##########################

        # extract variable scope
        scope = kwargs.pop('scope', 'all')
        name = f'{scope}/{name}'
        
        # create variable
        #################

        var = PyRatesVar(vtype=vtype, dtype=dtype, shape=shape, value=value, name=name, backend=self)

        if name in self.var_counter:
            name_old = name
            name = f"{name}_{self.var_counter[name]}"
            self.var_counter[name_old] += 1
        else:
            self.var_counter[name] = 1
        var.name = name
        if var.vtype == 'constant':
            self.graph['vars'][name] = var.value
        else:
            self.graph['vars'][name] = var
        return self.graph['vars'][name]

    def add_op(self,
               op: str,
               *args,
               **kwargs
               ) -> Union[PyRatesOp, PyRatesVar]:
        """Add operation to the backend.

        Parameters
        ----------
        op
            Key of the operation. Needs to be a key of `TensorflowGraph.ops`
        args
            Positional arguments to be passed to the operation.
        kwargs
            Keyword arguments to be passed to the operation.

        Returns
        -------
        Union[PyRatesOp, PyRatesVar]
            Handle for the lambda-numpy function

        """

        # process input arguments
        #########################

        # extract scope
        scope = kwargs.pop('scope', 'all')

        # extract graph dependencies
        dependencies = kwargs.pop('dependencies', [])

        # extract additional infos
        assign_to_var = kwargs.pop('assign_to_var', False)

        kwargs.pop('name', None)

        # add dependency layer
        dep_layer = []
        for dep in dependencies:
            found = False
            for l in self.graph['layers']:
                if dep in l:
                    found = True
                    break
            if not found:
                dep_layer.append(dep)
        if dep_layer:
            self.graph['layers'].append(dep_layer)

        # create operation
        ##################
        
        constant_op = False
        if len(args) == 1:
            if hasattr(args[0], 'eval'):
                op = PyRatesOp(self.ops[op], op, *args, **kwargs)
            else:
                op = PyRatesOp(self.constant_ops_1[op], op, *args, **kwargs)
                constant_op = True
        else:
            if hasattr(args[0], 'eval') and hasattr(args[1], 'eval'):
                op = PyRatesOp(self.ops[op], op, *args, **kwargs)
            elif hasattr(args[0], 'eval'):
                op = PyRatesOp(self.constant_ops_2[op], op, *args, **kwargs)
            elif hasattr(args[1], 'eval'):
                op = PyRatesOp(self.constant_ops_3[op], op, *args, **kwargs)
            else:
                op = PyRatesOp(self.constant_ops_1[op], op, *args, **kwargs)
                constant_op = True
        
        if constant_op:
            new_var = op.eval()
            if hasattr(new_var, 'shape'):
                return self.add_var(vtype='constant', name=f'{scope}/{op.name}_evaluated', value=new_var)
            else:
                return new_var
        else:
            name = op.name
            if name in self.op_counter:
                name_old = name
                name = f"{name}_{self.op_counter[name]}"
                self.op_counter[name_old] += 1
            else:
                self.op_counter[name] = 1
            op.name = name
            self.graph['ops'][name] = op
            return self.graph['ops'][name]

    def add_layer(self,
                  ops: list,
                  *args,
                  **kwargs
                  ) -> tuple:
        """Adds a layer of operations to the backend using `tensorflow.tuple`.

        Parameters
        ----------
        ops
            All operations that should be part of this layer.

        Returns
        -------
        list
            List of operations with dependencies added (layer operations will all be evaluated before
            any layer operation can be used in successive layers.)

        """
        self.graph['layers'].append(ops)
        vars_tmp = deepcopy(self.graph['vars'])
        updated_vars = [self.graph['vars'][op.eval().name] for op in ops]
        for var in updated_vars:
            var.value = vars_tmp[var.name].value
        return ops, updated_vars

    def clear(self):
        """Resets all tensorflow operations on the graph.
        """
        self.graph['vars'].clear()
        self.graph['var_updates'].clear()
        self.graph['vars'].clear()

    def eval_var(self, var):
        return self.graph['vars'][var].value

    def eval_op(self, op):
        return self.graph['ops'][op].eval()

    #@jit(nopython=True, parallel=True)
    def eval_layer(self, idx):
        return [op.eval() for op in self.graph['layers'][idx]]

    def compile(self):
        layers = []
        while self.graph['layers']:
            l1 = self.graph['layers'].pop(0)
            if not any([l1 == l2 for l2 in layers]):
                layers.append(l1)
        self.graph['layers'] = layers

    def eval(self, ops):
        return [op.eval() for op in ops]

    def broadcast(self, op1: Any, op2: Any, **kwargs) -> tuple:
        """Tries to match the shapes of op1 and op2 such that op can be applied. Then applies op to op1 and op2.

        Parameters
        ----------
        op1
            First argument to the operation.
        op2
            Second argument to the operation.
        return_ops
            If true, the adjusted arguments (op1 and op2) are returned.
        kwargs
            Additional keyword arguments to be passed to the backend.

        Returns
        -------
        tp.Union[tuple, tp.Any]
            Output of op applied to op1 and op2. If return_ops, op1 and op2 are also returned.

        """

        # get key and value of ops if they are dicts
        if type(op1) is dict:
            (op1_key, op1_val), = op1.items()
        else:
            op1_val = op1
        if type(op2) is dict:
            (op2_key, op2_val), = op2.items()
        else:
            op2_val = op2

        # try to match shapes
        if not self._compare_shapes(op1_val, op2_val):

            # try removing singleton dimensions from op1/op2
            op1_val_tmp, op2_val_tmp = self._match_shapes(op1_val, op2_val, adjust_second=True, assign=False)
            if not self._compare_shapes(op1_val_tmp, op2_val_tmp):
                op1_val_tmp, op2_val_tmp = self._match_shapes(op1_val_tmp, op2_val_tmp, adjust_second=False,
                                                              assign=False)
            if self._compare_shapes(op1_val_tmp, op2_val_tmp):
                op1_val, op2_val = op1_val_tmp, op2_val_tmp

        # try to match data types
        if not self._compare_dtypes(op1_val, op2_val):
            op1_val, op2_val = self._match_dtypes(op1_val, op2_val)

        return op1_val, op2_val

    def _match_shapes(self, op1: Any, op2: Any, adjust_second: bool = True, assign: bool = False) -> tuple:
        """Re-shapes op1 and op2 such that they can be combined via mathematical operations.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.
        assign
            If true, the re-shaped operators will be assigned to new variables. Else, the manipulation will be performed
            in place.
        adjust_second
            If true, the second operator will be re-shaped according to the shape of the first operator. If false,
            it will be done the other way around.

        Returns
        -------
        tuple
            The re-shaped operators.

        """

        if adjust_second:
            op_adjust = op2
            op_target = op1
        else:
            op_adjust = op1
            op_target = op2

        if len(op_adjust.shape) == 0 and len(op_target.shape) > 0 and assign:

            # create array of zeros and fill it with op_adjust
            op_adjust = self.add_op('+', self.add_op("zeros", op_target.shape, op_target.dtype), op_adjust)

        elif (len(op_target.shape) > len(op_adjust.shape)) and (1 in op_target.shape) and (len(op_adjust.shape) > 0):

            # reshape op_adjust to match the shape of op_target
            target_shape = op_target.shape
            idx = list(target_shape).index(1)
            if idx == 0:
                op_adjust = self.add_op('reshape', op_adjust, [1, op_adjust.shape[0]])
            else:
                op_adjust = self.add_op('reshape', op_adjust, [op_adjust.shape[0], 1])

        elif (len(op_adjust.shape) > len(op_target.shape) and 1 in op_adjust.shape) or \
                (len(op_target.shape) == 2 and len(op_adjust.shape) == 2 and op_target.shape[1] != op_adjust.shape[0]
                 and 1 in op_adjust.shape):

            # cut singleton dimension from op_adjust
            idx = list(op_adjust.shape).index(1)
            op_adjust = self.add_op('squeeze', op_adjust, idx)

        if adjust_second:
            return op_target, op_adjust
        return op_adjust, op_target

    @staticmethod
    def _match_dtypes(op1: Any, op2: Any) -> tuple:
        """

        Parameters
        ----------
        op1
        op2

        Returns
        -------

        """

        op2.dtype = op1.dtype
        op2.value = np.asarray(op2.value, dtype=op2.dtype)
        return op1, op2

    @staticmethod
    def _compare_shapes(op1: Any, op2: Any) -> bool:
        """Checks whether the shapes of op1 and op2 are compatible with each other.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.

        Returns
        -------
        bool
            If true, the shapes of op1 and op2 are compatible.

        """

        if hasattr(op1, 'shape') and hasattr(op2, 'shape'):
            if op1.shape == op2.shape:
                return True
            elif len(op1.shape) > 1 and len(op2.shape) > 1:
                return True
            elif len(op1.shape) == 0 or len(op2.shape) == 0:
                return True
            else:
                return False
        else:
            return True

    @staticmethod
    def _compare_dtypes(op1: Any, op2: Any) -> bool:
        """Checks whether the data types of op1 and op2 are compatible with each other.

        Parameters
        ----------
        op1
            First operator.
        op2
            Second operator.

        Returns
        -------
        bool
            If true, the data types of op1 and op2 are compatible.

        """

        return True


def no_op(*args, **kwargs):
    pass


def numpy_assign(y, x):
    y.value[:] = x.eval()[:]
    return y


def numpy_assign_const(y, x):
    y.value[:] = x[:]
    return y


def numpy_assign_add(y, x):
    y.value[:] += x.eval()[:]
    return y


def numpy_assign_add_const(y, x):
    y.value[:] += x[:]
    return y


def numpy_cast(x, dtype):
    return np.asarray(x, dtype=dtype)


def scatter_update_numpy(x, idx, update):
    x.value[idx.eval()] = update.eval()
    return x


def scatter_update_numpy_const(x, idx, update):
    upd = update.eval() if hasattr(update, 'eval') else update
    x.value[idx] = upd
    return x


def numpy_sigmoid(x):
    return 1./(1. + np.exp(-x.eval()))


def numpy_sigmoid_constant(x):
    return 1./(1. + np.exp(-x))


def neg_one():
    return -1.0
