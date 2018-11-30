"""This module provides wrappers for different backends that are needed by the parser class.
"""

# external imports
import tensorflow as tf
import time as t
import numpy as np

# meta infos
__author__ = "Richard Gast"
__status__ = "development"


class TensorflowBackend(tf.Graph):
    """

    """

    def __init__(self):

        super().__init__()

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
                    "neg": lambda x: -x,
                    "sin": tf.sin,
                    "cos": tf.cos,
                    "tan": tf.tan,
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
                    "concat": tf.concat,
                    "reshape": tf.reshape,
                    "shape": tf.shape,
                    "dtype": tf.keras.backend.dtype,
                    'squeeze': tf.squeeze,
                    "cast": tf.cast,
                    "randn": tf.random_normal,
                    "ones": tf.ones,
                    "zeros":tf.zeros,
                    "softmax": tf.nn.softmax,
                    "sigmoid": tf.sigmoid,
                    "tanh": tf.tanh,
                    "gather": tf.gather,
                    "gather_nd": tf.gather_nd,
                    "scatter": tf.scatter_nd,
                    "scatter_update": tf.scatter_update,
                    "scatter_add": tf.scatter_add,
                    "mask": tf.boolean_mask,
                    "stack": tf.stack,
                    "pstack": tf.parallel_stack,
                    "group": tf.group,
                    "tuple": tf.tuple
                    }

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

        self.existing_scopes = {}

    def run(self, steps, ops, inputs, outputs, sampling_steps=None, sampling_ops=None, out_dir=None):
        """

        Parameters
        ----------
        steps
        ops
        inputs
        outputs
        sampling_steps
        sampling_ops
        out_dir

        Returns
        -------

        """

        # initialize session log
        if out_dir:
            writer = tf.summary.FileWriter(out_dir, graph=self)

        # start session
        with tf.Session(graph=self) as sess:

            # initialize variables on graph
            sess.run(tf.global_variables_initializer())

            # simulate backend behavior for each time-step
            t_start = t.time()
            for step in range(steps):
                if step % sampling_steps == 0:
                    sess.run(sampling_ops, inputs[step])
                else:
                    sess.run(ops, inputs[step])
            t_end = t.time()

            # close session log
            if out_dir:
                writer.close()

            # store output variables in output dictionary
            for key, var in outputs.items():
                outputs[key] = var.eval(sess)

        return outputs, t_end - t_start

    def add_variable(self, name, value, shape=None, dtype=None, **kwargs):
        """

        Parameters
        ----------
        name
        value
        shape
        dtype
        scope

        Returns
        -------

        """

        # processs input arguments
        scope, reuse = self.get_scope(kwargs.pop('scope', None))
        dependencies = kwargs.pop('dependencies', None)

        if shape is None:
            shape = value.shape
        if dtype is None:
            dtype = value.dtype

        # create variable
        with self.as_default():
            with scope as sc:
                with tf.control_dependencies(dependencies):
                    if reuse:
                        with tf.name_scope(sc.original_name_scope):
                            return tf.get_variable(name, shape, dtype, initializer=tf.constant_initializer(value))
                    else:
                        return tf.get_variable(name, shape, dtype, initializer=tf.constant_initializer(value))

    def add_constant(self, name, value, shape=None, dtype=None, **kwargs):
        """

        Parameters
        ----------
        name
        value
        shape
        dtype
        scope

        Returns
        -------

        """

        # process input arguments
        scope, reuse = self.get_scope(kwargs.pop('scope', None))
        dependencies = kwargs.pop('dependencies', None)

        if shape is None:
            shape = value.shape
        if dtype is None:
            dtype = value.dtype

        # create constant
        with self.as_default():
            with scope as sc:
                with tf.control_dependencies(dependencies):
                    if reuse:
                        with tf.name_scope(sc.original_name_scope):
                            return tf.constant(value, dtype, shape, name)
                    else:
                        return tf.constant(value, dtype, shape, name)

    def add_placeholder(self, name, shape, dtype, **kwargs):
        """

        Parameters
        ----------
        name
        shape
        dtype
        scope

        Returns
        -------

        """

        # process input arguments
        scope, reuse = self.get_scope(kwargs.pop('scope', None))
        dependencies = kwargs.pop('dependencies', [])

        # create placeholder
        with self.as_default():
            with scope as sc:
                with tf.control_dependencies(dependencies):
                    if reuse:
                        with tf.name_scope(sc.original_name_scope):
                            return tf.placeholder(dtype, shape, name)
                    else:
                        return tf.placeholder(dtype, shape, name)

    def add_op(self, op: str, *args, **kwargs):
        """

        Parameters
        ----------
        op
        args
        kwargs

        Returns
        -------

        """

        # process input arguments
        dependencies = kwargs.pop('dependencies', None)
        assign_to_var = kwargs.pop('assign_to_var', False)
        scope, reuse = self.get_scope(kwargs.pop('scope', None))

        # create operation
        with self.as_default():
            with scope as sc:
                with tf.control_dependencies(dependencies):
                    if reuse:
                        with tf.name_scope(sc.original_name_scope):
                            try:
                                tf_op = self.ops[op](*args, **kwargs)
                            except TypeError:
                                tf_op = self.ops[op](list(args), **kwargs)
                            if assign_to_var:
                                var = self.add_variable(None,
                                                        value=np.zeros(tf_op.shape, dtype=tf_op.dtype.as_numpy_dtype))
                                return var.assign(tf_op)
                            else:
                                return tf_op
                    else:
                        try:
                            tf_op = self.ops[op](*args, **kwargs)
                        except TypeError:
                            tf_op = self.ops[op](list(args), **kwargs)
                        if assign_to_var:
                            var = self.add_variable(None,
                                                    value=np.zeros(tf_op.shape, dtype=tf_op.dtype.as_numpy_dtype))
                            return var.assign(tf_op)
                        else:
                            return tf_op

    def add_layer(self, ops, *args, **kwargs):
        """

        Parameters
        ----------
        ops
        args
        kwargs

        Returns
        -------

        """

        # process input arguments
        dependencies = kwargs.pop('dependencies', None)
        scope, reuse = self.get_scope(kwargs.pop('scope', None))

        # create layer
        with self.as_default():
            with scope as sc:
                with tf.control_dependencies(dependencies):
                    if reuse:
                        with tf.name_scope(sc.original_name_scope):
                            return tf.tuple(ops, *args, **kwargs)
                    else:
                        return tf.tuple(ops, *args, **kwargs)

    def get_scope(self, scope):
        """

        Parameters
        ----------
        scope

        Returns
        -------

        """

        with self.as_default():
            if scope is None:
                return tf.variable_scope(tf.get_variable_scope(), reuse=tf.AUTO_REUSE), True
            if scope not in self.existing_scopes.keys():
                self.existing_scopes[scope] = True
            return tf.variable_scope(scope, reuse=tf.AUTO_REUSE), self.existing_scopes[scope]


class KerasExpressionParser(tf.keras.models.Model):
    """Expression parser that transforms expression into keras operations on a tensorflow graph.

    Parameters
    ----------
    expr_str
        See docstring of `ExpressionParser`.
    args
        See docstring of `ExpressionParser`. Each variable in args needs to be a dictionary with key-value pairs for:
            - `var`: contains the tensorflow variable.
            - `dependency`: Boolean. If True, the expression needs to wait for this variable to be calculated/updated
               before being evaluated.
    lhs
        See docstring of `ExpressionParser`.
    tf_graph
        Instance of `tensorflow.Graph`. Mathematical expression will be parsed into this graph.

    Attributes
    ----------
    tf_graph
        Instance of `tensorflow.Graph` containing a graph-representation of `expr_str`.
    ops
        Dictionary containing all mathematical operations available for this parser and their syntax. These include:
            - addition: `+`
            - subtraction: `-`
            - multiplication: `*`
            - division: `/`
            - modulo: `%`
            - exponentiation: `^`
            - matrix multiplication: `@`
            - matrix transposition: `.T`
            - matrix inversion: `.I`
            - logical greater than: `>`
            - logical less than: `<`
            - logical equal: `==`
            - logical unequal: `!=`
            - logical greater or equal: `>=`
            - logical smaller or equal: `<=`
    funcs
        Dicionary containing all additional functions available for this parser and their syntax. These include:
            - sinus: `sin()`.
            - cosinus: `cos()`.
            - tangens: `tan()`.
            - absolute: `abs()`.
            - maximum: `max()`
            - minimum: `min()`
            - index of maximum: `argmax()`
            - index of minimum: `argmin()`
            - round to next integer: `round()`. Tensorflow name: `tensorflow.to_int32()`.
            - round to certain decimal point: `roundto()`. Custom function using `tensorflow.round()`. Defined in
              `pyrates.parser.parser.py`.
            - sum over dimension(s): `sum()`. Tensorflow name: `reduce_sum()`.
            - Concatenate multiples of tensor over certain dimension: `tile()`.
            - Reshape tensor: `reshape()`.
            - Cut away dimensions of size 1: `squeeze()`.
            - Cast variable to data-type: `cast()`.
            - draw random variable from standard normal distribution: `randn()`.
              Tensorflow name: `tensorflow.random_normal`.
            - Create array filled with ones: `ones()`.
            - Create array filled with zeros: `zeros()`.
            - Apply softmax function to variable: `softmax()`. Tensorflow name: `tensorflow.nn.softmax()`.
            - Apply boolean mask to array: `boolean_mask()`.
            - Create new array with non-zero entries at certain indices: `scatter()`.
              Tensorflow name: `tensorflow.scatter_nd`
            - Add values to certain entries of tensor: 'scatter_add()'. Tensorflow name: `tensorflow.scatter_nd_add`.
            - Update values of certain tensor entries: `scatter_update()`.
              Tensorflow name: `tensorflow.scatter_nd_update`.
            - Apply tensor as index to other tensor: `array_idx()`. Tensorflow name: `tensorflow.gather_nd`.
            - Get variable from tensorflow graph or create new variable: `new_var()`:
              Tensorflow name: `tensorflow.get_variable`.
        For a detailed documentation of how to use these functions, see the tensorflow Python API.
    dtypes
        Dictionary containing all data-types available for this parser. These include:
            - float16, float32, float64
            - int16, int32, int64
            - uint16, uint32, uint64
            - complex64, complex128,
            - bool
        All of those data-types can be used inside a mathematical expression instead of using `cast()`
        (e.g. `int32(3.631)`.
    For all other attributes, see docstring of `ExpressionParser`.

    Methods
    -------
    See docstrings of `ExpressionParser` methods.

    Examples
    --------

    References
    ----------

    """

    def __init__(self, expr_str: str, args: dict, backend: tf.keras.layers.Layer, lhs: bool = False) -> None:
        """Instantiates keras expression parser.
        """

        # call super init
        #################

        super().__init__(expr_str=expr_str, args=args, backend=backend, lhs=lhs)

        # define operations and functions
        #################################

        # base math operations
        ops = {"+": tf.keras.layers.Lambda(lambda x: x[0] + x[1]),
               "-": tf.keras.layers.Lambda(lambda x: x[0] - x[1]),
               "*": tf.keras.layers.Lambda(lambda x: x[0] * x[1]),
               "/": tf.keras.layers.Lambda(lambda x: x[0] / x[1]),
               "%": tf.keras.layers.Lambda(lambda x: x[0] % x[1]),
               "^": tf.keras.layers.Lambda(lambda x: tf.keras.backend.pow(x[0], x[1])),
               "@": tf.keras.layers.Lambda(lambda x: tf.keras.backend.dot(x[0], x[1])),
               ".T": tf.keras.layers.Lambda(lambda x: tf.keras.backend.transpose(x)),
               ".I": tf.keras.layers.Lambda(lambda x: tf.matrix_inverse(x)),
               ">": tf.keras.layers.Lambda(lambda x: tf.keras.backend.greater(x[0], x[1])),
               "<": tf.keras.layers.Lambda(lambda x: tf.keras.backend.less(x[0], x[1])),
               "==": tf.keras.layers.Lambda(lambda x: tf.keras.backend.equal(x[0], x[1])),
               "!=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.not_equal(x[0], x[1])),
               ">=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.greater_equal(x[0], x[1])),
               "<=": tf.keras.layers.Lambda(lambda x: tf.keras.backend.less_equal(x[0], x[1])),
               "=": tf.keras.backend.update
               }
        self.ops.update(ops)

        # additional functions
        funcs = {"sin": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sin(x)),
                 "cos": tf.keras.layers.Lambda(lambda x: tf.keras.backend.cos(x)),
                 "tanh": tf.keras.layers.Lambda(lambda x: tf.keras.backend.tanh(x)),
                 "abs": tf.keras.layers.Lambda(lambda x: tf.keras.backend.abs(x)),
                 "sqrt": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sqrt(x)),
                 "sq": tf.keras.layers.Lambda(lambda x: tf.keras.backend.square(x)),
                 "exp": tf.keras.layers.Lambda(lambda x: tf.keras.backend.exp(x)),
                 "max": tf.keras.layers.Lambda(lambda x: tf.keras.backend.max(x)),
                 "min": tf.keras.layers.Lambda(lambda x: tf.keras.backend.min(x)),
                 "argmax": tf.keras.layers.Lambda(lambda x: tf.keras.backend.argmax(x)),
                 "argmin": tf.keras.layers.Lambda(lambda x: tf.keras.backend.argmin(x)),
                 "round": tf.keras.layers.Lambda(lambda x: tf.keras.backend.round(x)),
                 "roundto": tf.keras.layers.Lambda(lambda x: tf.keras.backend.round(x[0] * 10**x[1]) / 10**x[1]),
                 "sum": tf.keras.layers.Lambda(lambda x: tf.keras.backend.sum(x[0], *x[1])
                                               if type(x) is list else tf.keras.backend.sum(x)),
                 "concat": tf.keras.layers.Lambda(lambda x: tf.keras.backend.concatenate(x[0], *x[1])
                                                  if type(x[0]) is list else tf.keras.backend.concatenate(x)),
                 "reshape": tf.keras.layers.Lambda(lambda x: tf.keras.backend.reshape(x[0], x[1])
                                                   if type(x) is list else tf.keras.backend.reshape(x)),
                 "shape": tf.keras.backend.shape,
                 "dtype": tf.keras.backend.dtype,
                 'squeeze': tf.keras.layers.Lambda(lambda x: tf.keras.backend.squeeze(x[0], x[1])
                                                   if type(x) is list else tf.keras.backend.squeeze(x[0], -1)),
                 "cast": tf.keras.layers.Lambda(lambda x: tf.keras.backend.cast(x[0], x[1])),
                 "randn": tf.keras.layers.Lambda(lambda x: tf.keras.backend.random_normal(x[0], *x[1])
                                                 if "Tensor" in str(type(x[0]))
                                                 else tf.keras.backend.random_normal(x)),
                 "ones": tf.keras.layers.Lambda(lambda x: tf.keras.backend.ones(x[0], x[1])
                                                if "Tensor" in str(type(x[0]))
                                                else tf.keras.backend.ones(x)),
                 "zeros": tf.keras.layers.Lambda(lambda x: tf.keras.backend.zeros(x[0], x[1])
                                                 if "Tensor" in str(type(x[0]))
                                                 else tf.keras.backend.zeros(x)),
                 "softmax": tf.keras.layers.Lambda(lambda x: tf.keras.activations.softmax(x[0], *x[1])
                                                   if type(x[0]) is list else tf.keras.activations.softmax(x)),
                 "gather": tf.keras.layers.Lambda(lambda x: tf.gather_nd(x[0], x[1])),
                 "mask": tf.keras.layers.Masking,
                 "lambda": tf.keras.layers.Lambda
                 }
        self.funcs.update(funcs)

        dtypes = {"float16": tf.float16,
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
        self.dtypes.update(dtypes)