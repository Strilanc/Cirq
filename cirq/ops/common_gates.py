# Copyright 2018 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Quantum gates that are commonly used in the literature."""
import math
from typing import Union, Tuple, Optional, List

import numpy as np

from cirq.ops import gate_features, eigen_gate, raw_types
from cirq.value import Symbol


class Rot11Gate(eigen_gate.EigenGate,
                gate_features.TwoQubitGate,
                gate_features.TextDiagrammableGate,
                raw_types.InterchangeableQubitsGate):
    """Phases the |11> state of two adjacent qubits by a fixed amount.

    A ParameterizedCZGate guaranteed to not be using the parameter key field.
    """

    def __init__(self,
                 *positional_args,
                 half_turns: Union[Symbol, float] = 1.0) -> None:
        assert not positional_args
        super().__init__(exponent=half_turns)

    def _eigen_components(self):
        return [
            (0, np.diag([1, 1, 1, 0])),
            (1, np.diag([0, 0, 0, 1])),
        ]

    def _canonical_exponent_period(self) -> Optional[float]:
        return 2

    def _with_exponent(self, exponent: Union[Symbol, float]) -> 'Rot11Gate':
        return Rot11Gate(half_turns=exponent)

    @property
    def half_turns(self) -> Union[Symbol, float]:
        return self._exponent

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return '@', 'Z'

    def text_diagram_exponent(self):
        return self._exponent

    def __repr__(self) -> str:
        if self.half_turns == 1:
            return 'CZ'
        return 'CZ**{!r}'.format(self.half_turns)


class RotXGate(eigen_gate.EigenGate,
               gate_features.TextDiagrammableGate,
               gate_features.SingleQubitGate):
    """Fixed rotation around the X axis of the Bloch sphere."""

    def __init__(self,
                 *positional_args,
                 half_turns: Union[Symbol, float] = 1.0) -> None:
        assert not positional_args
        super().__init__(exponent=half_turns)

    def _eigen_components(self):
        return [
            (0, np.array([[0.5, 0.5], [0.5, 0.5]])),
            (1, np.array([[0.5, -0.5], [-0.5, 0.5]])),
        ]

    def _canonical_exponent_period(self) -> Optional[float]:
        return 2

    def _with_exponent(self, exponent: Union[Symbol, float]) -> 'RotXGate':
        return RotXGate(half_turns=exponent)

    @property
    def half_turns(self) -> Union[Symbol, float]:
        return self._exponent

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return 'X',

    def text_diagram_exponent(self):
        return self._exponent

    def __repr__(self) -> str:
        if self.half_turns == 1:
            return 'X'
        return 'X**{!r}'.format(self.half_turns)


class RotYGate(eigen_gate.EigenGate,
               gate_features.TextDiagrammableGate,
               gate_features.SingleQubitGate):
    """Fixed rotation around the Y axis of the Bloch sphere."""

    def __init__(self,
                 *positional_args,
                 half_turns: Union[Symbol, float] = 1.0) -> None:
        assert not positional_args
        super().__init__(exponent=half_turns)

    def _eigen_components(self):
        return [
            (0, np.array([[0.5, -0.5j], [0.5j, 0.5]])),
            (1, np.array([[0.5, 0.5j], [-0.5j, 0.5]])),
        ]

    def _canonical_exponent_period(self) -> Optional[float]:
        return 2

    def _with_exponent(self, exponent: Union[Symbol, float]) -> 'RotYGate':
        return RotYGate(half_turns=exponent)

    @property
    def half_turns(self) -> Union[Symbol, float]:
        return self._exponent

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return 'Y',

    def text_diagram_exponent(self):
        return self._exponent

    def __repr__(self) -> str:
        if self.half_turns == 1:
            return 'Y'
        return 'Y**{!r}'.format(self.half_turns)


class RotZGate(eigen_gate.EigenGate,
               gate_features.TextDiagrammableGate,
               gate_features.SingleQubitGate):
    """Fixed rotation around the Z axis of the Bloch sphere."""

    def __init__(self,
                 *positional_args,
                 half_turns: Union[Symbol, float] = 1.0) -> None:
        assert not positional_args
        super().__init__(exponent=half_turns)

    def _eigen_components(self):
        return [
            (0, np.diag([1, 0])),
            (1, np.diag([0, 1])),
        ]

    def _canonical_exponent_period(self) -> Optional[float]:
        return 2

    def _with_exponent(self, exponent: Union[Symbol, float]) -> 'RotZGate':
        return RotZGate(half_turns=exponent)

    @property
    def half_turns(self) -> Union[Symbol, float]:
        return self._exponent

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        if abs(self.half_turns) == 0.5:
            return 'S'
        if abs(self.half_turns) == 0.25:
            return 'T'
        return 'Z',

    def text_diagram_exponent(self) -> float:
        if self.half_turns in [0.5, 0.25, -0.25, -0.5]:
            return 1 if self.half_turns > 0 else -1
        return self.half_turns

    def __repr__(self) -> str:
        if self.half_turns == 1:
            return 'Z'
        if self.half_turns == 0.5:
            return 'Z'
        return 'Z**{!r}'.format(self.half_turns)


class MeasurementGate(gate_features.TextDiagrammableGate):
    """Indicates that qubits should be measured plus a key to identify results.

    Params:
        key: The string key of the measurement. If this is set to None, then
            some default key will be used instead (e.g.
            cirq.google.XmonSimulator will use a comma-separated list of the
            names of the qubits that the measurement gate was applied to).
        invert_mask: A list of Truthy or Falsey values indicating whether
            the corresponding qubits should be flipped. None indicates no
            inverting should be done.
    """

    def __init__(self,
                 key: Optional[str],
                 invert_mask: Optional[Tuple[bool, ...]] = None) -> None:
        self.key = key
        self.invert_mask = invert_mask

    def validate_args(self, qubits):
        if (self.invert_mask is not None and
                len(self.invert_mask) > len(qubits)):
            raise ValueError('len(invert_mask) > len(qubits)')

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return 'M',

    def on_each(self, targets):
        """Returns a list of operations measuring each of the targets.

        Args:
            targets: The qubits to apply this measurement gate to.

        Returns:
            Operations separately measuring the target qubits.
        """
        return [self.on(target) for target in targets]

    def __repr__(self):
        return 'MeasurementGate({}, {})'.format(repr(self.key),
                                                repr(self.invert_mask))

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.key == other.key and self.invert_mask == other.invert_mask

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((MeasurementGate, self.key, self.invert_mask))


def measure(*qubits, key=None, invert_mask=None) -> raw_types.Operation:
    """Returns a single MeasurementGate applied to all the given qubits.

    Args:
        *qubits: The qubits that the measurement gate should measure.
        key: The string key of the measurement. If this is None, it defaults
            to a comma-separated list of the target qubits' names.
        invert_mask: A list of Truthy or Falsey values indicating whether
            the corresponding qubits should be flipped. None indicates no
            inverting should be done.

    Returns:
        An operation targeting the given qubits with a measurement.
    """
    if key is None:
        key = ','.join(str(q) for q in qubits)
    return MeasurementGate(key, invert_mask).on(*qubits)


def measure_each(*qubits, key_func=str) -> List[raw_types.Operation]:
    """Returns a list of operations individually measuring the given qubits.

    Args:
        *qubits: The qubits to measure.
        key_func: Determines the key of the measurements of each qubit. Takes
            the qubit and returns the key for that qubit. Defaults to str.

    Returns:
        A list of operations individually measuring the given qubits.

    """
    return [MeasurementGate(key_func(q)).on(q) for q in qubits]


X = RotXGate()  # Pauli X gate.
Y = RotYGate()  # Pauli Y gate.
Z = RotZGate()  # Pauli Z gate.
CZ = Rot11Gate()  # Negates the amplitude of the |11> state.
MEASURE = MeasurementGate(key=None)  # Measurement with key implied by context.

S = Z**0.5
T = Z**0.25


class HGate(gate_features.TextDiagrammableGate,
            gate_features.CompositeGate,
            gate_features.SelfInverseGate,
            gate_features.KnownMatrixGate,
            gate_features.SingleQubitGate):
    """180 degree rotation around the X+Z axis of the Bloch sphere."""

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return 'H',

    def default_decompose(self, qubits):
        q = qubits[0]
        yield Y(q)**0.5
        yield X(q)

    def matrix(self):
        """See base class."""
        s = math.sqrt(0.5)
        return np.array([[s, s], [s, -s]])

    def __repr__(self):
        return 'H'


H = HGate()  # Hadamard gate.


class CNotGate(eigen_gate.EigenGate,
               gate_features.TextDiagrammableGate,
               gate_features.CompositeGate,
               gate_features.TwoQubitGate):
    """A controlled-NOT. Toggle the second qubit when the first qubit is on."""

    def __init__(self,
                 *positional_args,
                 half_turns: Union[Symbol, float] = 1.0) -> None:
        assert not positional_args
        super().__init__(exponent=half_turns)

    def default_decompose(self, qubits):
        c, t = qubits
        yield Y(t)**-0.5
        yield Rot11Gate(half_turns=self.half_turns).on(c, t)
        yield Y(t)**0.5

    def _eigen_components(self):
        return [
            (0, np.array([[1, 0, 0, 0],
                          [0, 1, 0, 0],
                          [0, 0, 0.5, 0.5],
                          [0, 0, 0.5, 0.5]])),
            (1, np.array([[0, 0, 0, 0],
                          [0, 0, 0, 0],
                          [0, 0, 0.5, -0.5],
                          [0, 0, -0.5, 0.5]])),
        ]

    def _canonical_exponent_period(self) -> Optional[float]:
        return 2

    def _with_exponent(self, exponent: Union[Symbol, float]) -> 'CNotGate':
        return CNotGate(half_turns=exponent)

    @property
    def half_turns(self) -> Union[Symbol, float]:
        return self._exponent

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        return '@', 'X'

    def text_diagram_exponent(self):
        return self._exponent

    def __repr__(self) -> str:
        if self.half_turns == 1:
            return 'CNOT'
        return 'CNOT**{!r}'.format(self.half_turns)


CNOT = CNotGate()  # Controlled Not Gate.


class SwapGate(gate_features.TextDiagrammableGate,
               gate_features.CompositeGate,
               gate_features.SelfInverseGate,
               gate_features.KnownMatrixGate,
               gate_features.TwoQubitGate,
               raw_types.InterchangeableQubitsGate):
    """Swaps two qubits."""

    def matrix(self):
        """See base class."""
        return np.array([[1, 0, 0, 0],
                         [0, 0, 1, 0],
                         [0, 1, 0, 0],
                         [0, 0, 0, 1]])

    def default_decompose(self, qubits):
        """See base class."""
        a, b = qubits
        yield CNOT(a, b)
        yield CNOT(b, a)
        yield CNOT(a, b)

    def __repr__(self):
        return 'SWAP'

    def text_diagram_wire_symbols(self,
                                  qubit_count=None,
                                  use_unicode_characters=True,
                                  precision=3):
        if not use_unicode_characters:
            return 'swap', 'swap'
        return '×', '×'


SWAP = SwapGate()  # Exchanges two qubits' states.
