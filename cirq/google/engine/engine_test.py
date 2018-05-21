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

"""Tests for engine."""

import numpy as np
import pytest

from apiclient import discovery
from google.protobuf.json_format import MessageToDict

from cirq.api.google.v1 import operations_pb2, params_pb2, program_pb2
from cirq.circuits import Circuit
from cirq.devices import UnconstrainedDevice
from cirq.google.engine.engine import Engine, EngineOptions
from cirq.schedules.schedulers import moment_by_moment_schedule
from cirq.study import ParamResolver, Points
from cirq.testing.mock import mock

_A_RESULT = program_pb2.Result(
    sweep_results=[program_pb2.SweepResult(repetitions=1, measurement_keys=[
        program_pb2.MeasurementKey(
            key='q',
            qubits=[operations_pb2.Qubit(row=1, col=1)])],
            parameterized_results=[
                program_pb2.ParameterizedResult(
                    params=params_pb2.ParameterDict(assignments={'a': 1}),
                    measurement_results=b'01')])])

_RESULTS = program_pb2.Result(
    sweep_results=[program_pb2.SweepResult(repetitions=1, measurement_keys=[
        program_pb2.MeasurementKey(
            key='q',
            qubits=[operations_pb2.Qubit(row=1, col=1)])],
            parameterized_results=[
                program_pb2.ParameterizedResult(
                    params=params_pb2.ParameterDict(assignments={'a': 1}),
                    measurement_results=b'01'),
                program_pb2.ParameterizedResult(
                    params=params_pb2.ParameterDict(assignments={'a': 2}),
                    measurement_results=b'01')])])


@mock.patch.object(discovery, 'build')
def test_run_circuit(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'SUCCESS'}}
    jobs.getResult().execute.return_value = {
        'result': MessageToDict(_A_RESULT)}

    result = Engine(api_key="key").run(
        EngineOptions('project-id', gcs_prefix='gs://bucket/folder'), Circuit(),
        UnconstrainedDevice)
    assert result.repetitions == 1
    assert result.params.param_dict == {'a': 1}
    assert result.measurements == {'q': np.array([[0]], dtype='uint8')}
    build.assert_called_with('quantum', 'v1alpha1',
                             discoveryServiceUrl=('https://{api}.googleapis.com'
                                                  '/$discovery/rest?version='
                                                  '{apiVersion}&key=key'))
    assert programs.create.call_args[1]['parent'] == 'projects/project-id'
    assert jobs.create.call_args[1][
               'parent'] == 'projects/project-id/programs/test'
    assert jobs.get().execute.call_count == 1
    assert jobs.getResult().execute.call_count == 1


@mock.patch.object(discovery, 'build')
def test_run_circuit_failed(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'FAILURE'}}

    with pytest.raises(RuntimeError, match='It is in state FAILURE'):
        Engine(api_key="key").run(
            EngineOptions('project-id', gcs_prefix='gs://bucket/folder'),
            Circuit(),
            UnconstrainedDevice)


@mock.patch.object(discovery, 'build')
def test_default_prefix(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'SUCCESS'}}
    jobs.getResult().execute.return_value = {
        'result': MessageToDict(_A_RESULT)}

    result = Engine(api_key="key").run(
        EngineOptions('org.com:project-id'), Circuit(),
        UnconstrainedDevice)
    assert result.repetitions == 1
    assert result.params.param_dict == {'a': 1}
    assert result.measurements == {'q': np.array([[0]], dtype='uint8')}
    build.assert_called_with('quantum', 'v1alpha1',
                             discoveryServiceUrl=('https://{api}.googleapis.com'
                                                  '/$discovery/rest?version='
                                                  '{apiVersion}&key=key'))
    assert programs.create.call_args[1]['body']['gcs_code_location'][
        'uri'].startswith('gs://gqe-project-id/programs/')

@mock.patch.object(discovery, 'build')
def test_run_sweep_params(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'SUCCESS'}}
    jobs.getResult().execute.return_value = {
        'result': MessageToDict(_RESULTS)}

    job = Engine(api_key="key").run_sweep(
        EngineOptions('project-id', gcs_prefix='gs://bucket/folder'),
        moment_by_moment_schedule(UnconstrainedDevice, Circuit()),
        params=[ParamResolver({'a': 1}), ParamResolver({'a': 2})])
    results = job.results()
    assert len(results) == 2
    for i, v in enumerate([1, 2]):
        assert results[i].repetitions == 1
        assert results[i].params.param_dict == {'a': v}
        assert results[i].measurements == {'q': np.array([[0]], dtype='uint8')}
    build.assert_called_with('quantum', 'v1alpha1',
                             discoveryServiceUrl=('https://{api}.googleapis.com'
                                                  '/$discovery/rest?version='
                                                  '{apiVersion}&key=key'))
    assert programs.create.call_args[1]['parent'] == 'projects/project-id'
    sweeps = programs.create.call_args[1]['body']['code']['parameterSweeps']
    assert len(sweeps) == 2
    for i, v in enumerate([1, 2]):
        assert sweeps[i]['repetitions'] == 1
        assert sweeps[i]['sweep']['factors'][0]['sweeps'][0]['points'][
                   'points'] == [v]
    assert jobs.create.call_args[1][
               'parent'] == 'projects/project-id/programs/test'
    assert jobs.get().execute.call_count == 1
    assert jobs.getResult().execute.call_count == 1


@mock.patch.object(discovery, 'build')
def test_run_sweep_sweeps(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'SUCCESS'}}
    jobs.getResult().execute.return_value = {
        'result': MessageToDict(_RESULTS)}

    job = Engine(api_key="key").run_sweep(
        EngineOptions('project-id', gcs_prefix='gs://bucket/folder'),
        moment_by_moment_schedule(UnconstrainedDevice, Circuit()),
        params=Points('a', [1, 2]))
    results = job.results()
    assert len(results) == 2
    for i, v in enumerate([1, 2]):
        assert results[i].repetitions == 1
        assert results[i].params.param_dict == {'a': v}
        assert results[i].measurements == {'q': np.array([[0]], dtype='uint8')}
    build.assert_called_with('quantum', 'v1alpha1',
                             discoveryServiceUrl=('https://{api}.googleapis.com'
                                                  '/$discovery/rest?version='
                                                  '{apiVersion}&key=key'))
    assert programs.create.call_args[1]['parent'] == 'projects/project-id'
    sweeps = programs.create.call_args[1]['body']['code']['parameterSweeps']
    assert len(sweeps) == 1
    assert sweeps[0]['repetitions'] == 1
    assert sweeps[0]['sweep']['factors'][0]['sweeps'][0]['points'][
               'points'] == [1, 2]
    assert jobs.create.call_args[1][
               'parent'] == 'projects/project-id/programs/test'
    assert jobs.get().execute.call_count == 1
    assert jobs.getResult().execute.call_count == 1


@mock.patch.object(discovery, 'build')
def test_bad_priority(build):
    with pytest.raises(TypeError, match='priority must be between 0 and 1000'):
        Engine(api_key="key").run(
            EngineOptions('project-id', gcs_prefix='gs://bucket/folder'),
            Circuit(),
            UnconstrainedDevice,
            priority=1001)


@mock.patch.object(discovery, 'build')
def test_cancel(build):
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    jobs = programs.jobs()
    programs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test'}
    jobs.create().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'READY'}}
    jobs.get().execute.return_value = {
        'name': 'projects/project-id/programs/test/jobs/test',
        'executionStatus': {'state': 'CANCELLED'}}

    job = Engine(api_key="key").run_sweep(
        EngineOptions('project-id', gcs_prefix='gs://bucket/folder'),
        Circuit(), device=UnconstrainedDevice)
    job.cancel()
    assert job.job_resource_name == ('projects/project-id/programs/test/'
                                     'jobs/test')
    assert job.state() == 'CANCELLED'
    assert jobs.cancel.call_args[1][
               'name'] == 'projects/project-id/programs/test/jobs/test'


@mock.patch.object(discovery, 'build')
def test_program_labels(build):
    program_name = 'projects/my-proj/programs/my-prog'
    service = mock.Mock()
    build.return_value = service
    programs = service.projects().programs()
    engine = Engine(api_key="key")

    def body():
        return programs.patch.call_args[1]['body']

    programs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'}}
    engine.add_program_labels(program_name, {'a': '2', 'c': '1'})

    assert body()['labels'] == {'a': '2', 'b': '1', 'c': '1'}
    assert body()['labelFingerprint'] == ''

    programs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'},
                                           'labelFingerprint': 'abcdef'}
    engine.set_program_labels(program_name, {'s': '1', 'p': '1'})
    assert body()['labels'] == {'s': '1', 'p': '1'}
    assert body()['labelFingerprint'] == 'abcdef'

    programs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'},
                                           'labelFingerprint': 'abcdef'}
    engine.remove_program_labels(program_name, ['a', 'c'])
    assert body()['labels'] == {'b': '1'}
    assert body()['labelFingerprint'] == 'abcdef'


@mock.patch.object(discovery, 'build')
def test_job_labels(build):
    job_name = 'projects/my-proj/programs/my-prog/jobs/my-job'
    service = mock.Mock()
    build.return_value = service
    jobs = service.projects().programs().jobs()
    engine = Engine(api_key="key")

    def body():
      return jobs.patch.call_args[1]['body']

    jobs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'}}
    engine.add_job_labels(job_name, {'a': '2', 'c': '1'})

    assert body()['labels'] == {'a': '2', 'b': '1', 'c': '1'}
    assert body()['labelFingerprint'] == ''

    jobs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'},
                                       'labelFingerprint': 'abcdef'}
    engine.set_job_labels(job_name, {'s': '1', 'p': '1'})
    assert body()['labels'] == {'s': '1', 'p': '1'}
    assert body()['labelFingerprint'] == 'abcdef'

    jobs.get().execute.return_value = {'labels': {'a': '1', 'b': '1'},
                                       'labelFingerprint': 'abcdef'}
    engine.remove_job_labels(job_name, ['a', 'c'])
    assert body()['labels'] == {'b': '1'}
    assert body()['labelFingerprint'] == 'abcdef'

