from typing import cast, Optional, Union

import equinox as eqx
import equinox.internal as eqxi
import jax
import jax.numpy as jnp
import jax.random as jrandom
import jax.tree_util as jtu
from jaxtyping import Array, PRNGKeyArray, PyTree

from .._custom_types import RealScalarLike
from .._misc import (
    default_floating_dtype,
    force_bitcast_convert_type,
    is_tuple_of_ints,
    split_by_tree,
)
from .base import AbstractBrownianPath


class UnsafeBrownianPath(AbstractBrownianPath):
    """Brownian simulation that is only suitable for certain cases.

    This is a very quick way to simulate Brownian motion, but can only be used when all
    of the following are true:

    1. You are using a fixed step size controller. (Not an adaptive one.)

    2. You do not need to backpropagate through the differential equation.

    3. You do not need deterministic solutions with respect to `key`. (This
       implementation will produce different results based on fluctuations in
       floating-point arithmetic.)

    Internally this operates by just sampling a fresh normal random variable over every
    interval, ignoring the correlation between samples exhibited in true Brownian
    motion. Hence the restrictions above. (They describe the general case for which the
    correlation structure isn't needed.)
    """

    shape: PyTree[jax.ShapeDtypeStruct] = eqx.field(static=True)
    # Handled as a string because PRNGKey is actually a function, not a class, which
    # makes it appearly badly in autogenerated documentation.
    key: PRNGKeyArray

    def __init__(
        self,
        shape: Union[tuple[int, ...], PyTree[jax.ShapeDtypeStruct]],
        key: PRNGKeyArray,
    ):
        self.shape = (
            jax.ShapeDtypeStruct(shape, default_floating_dtype())
            if is_tuple_of_ints(shape)
            else shape
        )
        self.key = key
        if any(
            not jnp.issubdtype(x.dtype, jnp.inexact)
            for x in jtu.tree_leaves(self.shape)
        ):
            raise ValueError("UnsafeBrownianPath dtypes all have to be floating-point.")

    @property
    def t0(self):
        return -jnp.inf

    @property
    def t1(self):
        return jnp.inf

    @eqx.filter_jit
    def evaluate(
        self, t0: RealScalarLike, t1: Optional[RealScalarLike] = None, left: bool = True
    ) -> PyTree[Array]:
        del left
        if t1 is None:
            t1 = t0
            t0 = 0
        t0 = eqxi.nondifferentiable(t0, name="t0")
        t1 = eqxi.nondifferentiable(t1, name="t1")
        t1 = cast(RealScalarLike, t1)
        t0_ = force_bitcast_convert_type(t0, jnp.int32)
        t1_ = force_bitcast_convert_type(t1, jnp.int32)
        key = jrandom.fold_in(self.key, t0_)
        key = jrandom.fold_in(key, t1_)
        key = split_by_tree(key, self.shape)
        return jtu.tree_map(
            lambda key, shape: self._evaluate_leaf(t0, t1, key, shape), key, self.shape
        )

    def _evaluate_leaf(
        self, t0: RealScalarLike, t1: RealScalarLike, key, shape: jax.ShapeDtypeStruct
    ):
        return jrandom.normal(key, shape.shape, shape.dtype) * jnp.sqrt(t1 - t0).astype(
            shape.dtype
        )


UnsafeBrownianPath.__init__.__doc__ = """
**Arguments:**

- `shape`: Should be a PyTree of `jax.ShapeDtypeStruct`s, representing the shape, 
    dtype, and PyTree structure of the output. For simplicity, `shape` can also just 
    be a tuple of integers, describing the shape of a single JAX array. In that case
    the dtype is chosen to be the default floating-point dtype.
- `key`: A random key.
"""
