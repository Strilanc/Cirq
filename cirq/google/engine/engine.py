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

"""Classes for running against Google's Quantum Engine.

As an example, to run a circuit against the xmon simulator
    engine = cirq.google.Engine(api_key='mysecretapikey')
    options = cirq.google.JobConfig(project_id='my-project-id')
    result = engine.run(options, circuit, repetitions=10)
"""

import base64
import os
import random
import re
import string
import time
import urllib.parse
from collections import Iterable
from typing import Dict, List, Optional, Union, cast

import numpy as np
from apiclient import discovery
from google.protobuf.json_format import MessageToDict

from cirq.api.google.v1 import program_pb2
from cirq.circuits import Circuit
from cirq.circuits.drop_empty_moments import DropEmptyMoments
from cirq.devices import Device, UnconstrainedDevice
from cirq.google.convert_to_xmon_gates import ConvertToXmonGates
from cirq.google.params import sweep_to_proto
from cirq.google.programs import schedule_to_proto, unpack_results
from cirq.schedules import Schedule, moment_by_moment_schedule
from cirq.study import ParamResolver, Sweep, Sweepable, TrialResult
from cirq.study.sweeps import Points, Unit, Zip

gcs_prefix_pattern = re.compile('gs://[a-z0-9._/-]+')
TERMINAL_STATES = ['SUCCESS', 'FAILURE', 'CANCELLED']


class EngineTrialResult(TrialResult):
    """Results of a single run against the Engine.

    Attributes:
        params: A ParamResolver of settings used for this result.
        repetitions: The number of repetitions for this trial.
        measurements: A dictionary from measurement gate key to measurement
            results ordered by the qubits acted upon by the measurement gate.
    """

    def __init__(self,
                 params: ParamResolver,
                 repetitions: int,
                 measurements: Dict[str, np.ndarray]) -> None:
        self.params = params
        self.repetitions = repetitions
        self.measurements = measurements

    def __str__(self):
        def bitstring(vals):
            return ''.join('1' if v else '0' for v in vals)

        keyed_bitstrings = [
            (key, bitstring(val)) for key, val in self.measurements.items()
        ]
        return ' '.join('{}={}'.format(key, val)
                        for key, val in sorted(keyed_bitstrings))


class JobConfig:
    """Configuration for a program and job to run on Quantum Engine.

    Quantum engine has two resources: programs and jobs. Programs live
    under cloud projects. Every program may have many jobs, which represent
    scheduled or terminated programs executions. Program and job resources have
    string names. This object contains the information necessary to create a
    program and then create a job on Quantum Engine, hence running the program.
    Program ids are of the form
        `projects/project_id/programs/program_id`
    while job ids are of the form
        `projects/project_id/programs/program_id/jobs/job_id`
    """

    def __init__(self,
                 project_id: Optional[str] = None,
                 program_id: Optional[str] = None,
                 job_id: Optional[str] = None,
                 gcs_prefix: Optional[str] = None,
                 gcs_program: Optional[str] = None,
                 gcs_results: Optional[str] = None) -> None:
        """Configuration for a job that is run on Quantum Engine.

        Requires project_id.

        Args:
            project_id: The project id string of the Google Cloud Project to
                use. Programs and Jobs will be created under this project id.
                If this is set to None, the engine's default project id will be
                used instead. If that also isn't set, calls will fail.
            program_id: Id of the program to create, defaults to a random
                version of 'prog-ABCD'.
            job_id: Id of the job to create, defaults to 'job-0'.
            gcs_prefix: Google Cloud Storage bucket and object prefix to use
                for storing programs and results. The bucket will be created if
                needed. Must be in the form "gs://bucket-name/object-prefix/".
            gcs_program: Explicit override for the program storage location.
            gcs_results: Explicit override for the results storage location.
        """
        self.project_id = project_id
        self.program_id = program_id
        self.job_id = job_id
        self.gcs_prefix = gcs_prefix
        self.gcs_program = gcs_program
        self.gcs_results = gcs_results


class Engine:
    """Runs programs on Quantum Engine.

    This class has methods for creating programs and jobs that execute on
    Quantum Engine:
        run
        run_sweep

    Another set of methods return information about programs and jobs that
    have been previously created on the Quantum Engine:
        get_program
        get_job
        get_job_results

    Finally, the engine has methods to update existing programs and jobs:
        cancel_job
        set_program_labels
        add_program_labels
        remove_program_labels
        set_job_labels
        add_job_labels
        remove_job_labels
    """

    def __init__(self,
                 api_key: str,
                 api: str = 'quantum',
                 version: str = 'v1alpha1',
                 default_project_id: Optional[str] = None,
                 discovery_url: Optional[str] = None,
                 gcs_prefix: Optional[str] = None,
                 **kwargs
    ) -> None:
        """Engine service client.

        Args:
            api_key: API key to use to retrieve discovery doc.
            api: API name.
            version: API version.
            default_project_id: The project_id used in jobs when they don't
                specify their own.
            discovery_url: Discovery url for the API. If not supplied, uses
                Google's default api.googleapis.com endpoint.
            gcs_prefix: A default gcs_prefix to use.
        """
        self.api_key = api_key
        self.api = api
        self.default_project_id = default_project_id
        self.version = version
        self.discovery_url = discovery_url or ('https://{api}.googleapis.com/'
                                               '$discovery/rest'
                                               '?version={apiVersion}&key=%s')
        self.gcs_prefix = gcs_prefix
        self.service = discovery.build(
            self.api,
            self.version,
            discoveryServiceUrl=self.discovery_url % urllib.parse.quote_plus(
                self.api_key),
            **kwargs)

    def run(self,
            program: Union[Circuit, Schedule],
            job_config: Optional[JobConfig] = None,
            device: Device = None,
            param_resolver: ParamResolver = ParamResolver({}),
            repetitions: int = 1,
            priority: int = 50,
            target_route: str = '/xmonsim',
    ) -> EngineTrialResult:
        """Runs the supplied Circuit or Schedule via Quantum Engine.

        Args:
            program: The Circuit or Schedule to execute. If a circuit is
                provided, a moment by moment schedule will be used.
            job_config: Configures the names of programs and jobs.
            device: The device on which to run a circuit. The circuit will be
                validated against this device before sending to the engine.
                If device is None, no validation will be done. Can only be
                supplied if program is a Circuit, otherwise the device from
                the Schedule will be used.
            param_resolver: Parameters to run with the program.
            repetitions: The number of repetitions to simulate.
            priority: The priority to run at, 0-100.
            target_route: The engine route to run against.

        Returns:
            A single EngineTrialResult for this run.
        """
        return list(self.run_sweep(program,
                                   job_config,
                                   device,
                                   [param_resolver],
                                   repetitions,
                                   priority,
                                   target_route))[0]

    def run_sweep(self,
                  program: Union[Circuit, Schedule],
                  job_config: Optional[JobConfig] = None,
                  device: Device = None,
                  params: Sweepable = None,
                  repetitions: int = 1,
                  priority: int = 500,
                  target_route: str = '/xmonsim',
    ) -> 'EngineJob':
        """Runs the supplied Circuit or Schedule via Quantum Engine.

        In contrast to run, this runs across multiple parameter sweeps, and
        does not block until a result is returned.

        Args:
            program: The Circuit or Schedule to execute. If a circuit is
                provided, a moment by moment schedule will be used.
            job_config: Configures the names of programs and jobs.
            device: The device on which to run a circuit. The circuit will be
                validated against this device before sending to the engine.
                If device is None, no validation will be done. Can only be
                supplied if program is a Circuit, otherwise the device from
                the Schedule will be used.
            params: Parameters to run with the program.
            repetitions: The number of circuit repetitions to run.
            priority: The priority to run at, 0-100.
            target_route: The engine route to run against.

        Returns:
            An EngineJob. If this is iterated over it returns a list of
            EngineTrialResults, one for each parameter sweep.
        """
        # Check and compute engine options.
        if job_config is None:
            job_config = JobConfig()
        project_id = job_config.project_id
        if project_id is None:
            project_id = self.default_project_id
        if project_id is None:
            raise ValueError(
                "Need a cloud project id. "
                "This engine has default_project_id=None and "
                "the given JobConfig has project_id=None. "
                "One or the other must be set.")

        gcs_prefix = job_config.gcs_prefix or self.gcs_prefix or (
                'gs://gqe-{}/'.format(project_id[project_id.rfind(':') + 1:]))
        if gcs_prefix and not gcs_prefix.endswith('/'):
            gcs_prefix += '/'
        if gcs_prefix and not gcs_prefix_pattern.match(gcs_prefix):
            raise TypeError('gcs_prefix must be of the form "gs://'
                            '<bucket name and optional object prefix>/"')
        if not gcs_prefix and (not job_config.gcs_program or
                               not job_config.gcs_results):
            raise TypeError('Either gcs_prefix must be provided or both'
                            ' gcs_program and gcs_results are required.')

        program_id = job_config.program_id or 'prog-%s' % ''.join(
            random.choice(string.ascii_uppercase + string.digits) for _ in
            range(6))
        job_id = job_config.job_id or 'job-0'
        gcs_program = job_config.gcs_program or '%sprograms/%s/%s' % (
            gcs_prefix, program_id, program_id)
        gcs_results = job_config.gcs_results or '%sprograms/%s/jobs/%s' % (
            gcs_prefix, program_id, job_id)

        # Check program to run and program parameters.
        if not 0 <= priority < 1000:
            raise TypeError('priority must be between 0 and 1000')

        if isinstance(program, Circuit):
            device = device or UnconstrainedDevice
            device.validate_circuit(program)
            # Convert to a schedule.
            circuit_copy = Circuit(program.moments)
            ConvertToXmonGates().optimize_circuit(circuit_copy)
            DropEmptyMoments().optimize_circuit(circuit_copy)
            schedule = moment_by_moment_schedule(device, circuit_copy)

        elif isinstance(program, Schedule):
            if device:
                raise TypeError(
                    'Device can not be provided when running a schedule.')
            schedule = program
        else:
            raise TypeError('Unexpected program type.')

        schedule.device.validate_schedule(schedule)

        # Create program.
        sweeps = _sweepable_to_sweeps(params or ParamResolver({}))
        proto_program = program_pb2.Program()
        for sweep in sweeps:
            sweep_proto = proto_program.parameter_sweeps.add()
            sweep_to_proto(sweep, sweep_proto)
            sweep_proto.repetitions = repetitions
        program_dict = MessageToDict(proto_program)
        program_dict['operations'] = [MessageToDict(op) for op in
                                      schedule_to_proto(schedule)]
        code = {
            '@type': 'type.googleapis.com/cirq.api.google.v1.Program'}
        code.update(program_dict)
        request = {
            'name': 'projects/%s/programs/%s' % (project_id,
                                                 program_id,),
            'gcs_code_location': {'uri': gcs_program, },
            'code': code,
        }
        response = self.service.projects().programs().create(
            parent='projects/%s' % project_id, body=request).execute()

        # Create job.
        request = {
            'name': '%s/jobs/%s' % (response['name'], job_id),
            'output_config': {
                'gcs_results_location': {
                    'uri': gcs_results
                }
            },
            'scheduling_config': {
                'priority': priority,
                'target_route': target_route
            },
        }
        response = self.service.projects().programs().jobs().create(
            parent=response['name'], body=request).execute()

        return EngineJob(
            JobConfig(project_id, program_id, job_id, gcs_prefix,
                      gcs_program, gcs_results), response, self)

    def get_program(self, program_resource_name: str) -> Dict:
        """Returns the previously created quantum program.

        Params:
            program_resource_name: A string of the form
                `projects/project_id/programs/program_id`.

        Returns:
            A dictionary containing the metadata and the program.
        """
        return self.service.projects().programs().get(
            name=program_resource_name).execute()

    def get_job(self, job_resource_name: str) -> Dict:
        """Returns metadata about a previously created job.

        See get_job_result if you want the results of the job and not just
        metadata about the job.

        Params:
            job_resource_name: A string of the form
                `projects/project_id/programs/program_id/jobs/job_id`.

        Returns:
            A dictionary containing the metadata.
        """
        return self.service.projects().programs().jobs().get(
            name=job_resource_name).execute()

    def get_job_results(self, job_resource_name: str) -> List[
        EngineTrialResult]:
        """Returns the actual results (not metadata) of a completed job.

        Params:
            job_resource_name: A string of the form
                `projects/project_id/programs/program_id/jobs/job_id`.

        Returns:
            An iterable over the EngineTrialResult, one per parameter in the
            parameter sweep.
        """
        response = self.service.projects().programs().jobs().getResult(
            parent=job_resource_name).execute()
        trial_results = []
        for sweep_result in response['result']['sweepResults']:
            sweep_repetitions = sweep_result['repetitions']
            key_sizes = [(m['key'], len(m['qubits']))
                         for m in sweep_result['measurementKeys']]
            for result in sweep_result['parameterizedResults']:
                data = base64.standard_b64decode(result['measurementResults'])
                measurements = unpack_results(data, sweep_repetitions,
                                              key_sizes)

                trial_results.append(EngineTrialResult(
                    params=ParamResolver(
                        result.get('params', {}).get('assignments', {})),
                    repetitions=sweep_repetitions,
                    measurements=measurements))
        return trial_results

    def cancel_job(self, job_resource_name: str):
        """Cancels the given job.

        See also the cancel method on EngineJob.

        Params:
            job_resource_name: A string of the form
                `projects/project_id/programs/program_id/jobs/job_id`.
        """
        self.service.projects().programs().jobs().cancel(
            name=job_resource_name, body={}).execute()

    def _set_program_labels(self, program_resource_name: str,
                            labels: Dict[str, str], fingerprint: str):
        self.service.projects().programs().patch(
            name=program_resource_name,
            body={'name': program_resource_name, 'labels': labels,
                  'labelFingerprint': fingerprint},
            updateMask='labels').execute()

    def set_program_labels(self, program_resource_name: str,
                           labels: Dict[str, str]):
        job = self.get_program(program_resource_name)
        self._set_program_labels(program_resource_name, labels,
                                 job.get('labelFingerprint', ''))

    def add_program_labels(self, program_resource_name: str,
                           labels: Dict[str, str]):
        job = self.get_program(program_resource_name)
        old_labels = job.get('labels', {})
        new_labels = old_labels.copy()
        new_labels.update(labels)
        if new_labels != old_labels:
            fingerprint = job.get('labelFingerprint', '')
            self._set_program_labels(program_resource_name, new_labels,
                                     fingerprint)

    def remove_program_labels(self, program_resource_name: str,
                              label_keys: List[str]):
        job = self.get_program(program_resource_name)
        old_labels = job.get('labels', {})
        new_labels = old_labels.copy()
        for key in label_keys:
            new_labels.pop(key, None)
        if new_labels != old_labels:
            fingerprint = job.get('labelFingerprint', '')
            self._set_program_labels(program_resource_name, new_labels,
                                     fingerprint)

    def _set_job_labels(self, job_resource_name: str, labels: Dict[str, str],
                        fingerprint: str):
        self.service.projects().programs().jobs().patch(
            name=job_resource_name,
            body={'name': job_resource_name, 'labels': labels,
                  'labelFingerprint': fingerprint},
            updateMask='labels').execute()

    def set_job_labels(self, job_resource_name: str, labels: Dict[str, str]):
        job = self.get_job(job_resource_name)
        self._set_job_labels(job_resource_name, labels,
                             job.get('labelFingerprint', ''))

    def add_job_labels(self, job_resource_name: str, labels: Dict[str, str]):
        job = self.get_job(job_resource_name)
        old_labels = job.get('labels', {})
        new_labels = old_labels.copy()
        new_labels.update(labels)
        if new_labels != old_labels:
            fingerprint = job.get('labelFingerprint', '')
            self._set_job_labels(job_resource_name, new_labels, fingerprint)

    def remove_job_labels(self, job_resource_name: str, label_keys: List[str]):
        job = self.get_job(job_resource_name)
        old_labels = job.get('labels', {})
        new_labels = old_labels.copy()
        for key in label_keys:
            new_labels.pop(key, None)
        if new_labels != old_labels:
            fingerprint = job.get('labelFingerprint', '')
            self._set_job_labels(job_resource_name, new_labels, fingerprint)


class EngineJob:
    """A job created on Quantum Engine.

    This job may be in a variety of states. It may be scheduling, it may be
    executing on a machine, or it may have entered a terminal state
    (either succeeding or failing).

    Attributes:
      job_config: The JobConfig used to create the job.
      job_resource_name: The full resource name of the engine job.
    """

    def __init__(self,
                 job_config: JobConfig,
                 job: Dict,
                 engine: Engine) -> None:
        """A job submitted to the engine.

        Args:
            job_config: The JobConfig used to create the job.
            job: A full Job Dict.
            engine: Engine connected to the job.
        """
        self.job_config = job_config
        self._job = job
        self._engine = engine
        self.job_resource_name = job['name']
        self.program_resource_name = self.job_resource_name.split('/jobs')[0]
        self._results = None  # type: Optional[List[EngineTrialResult]]

    def _update_job(self):
        if self._job['executionStatus']['state'] not in TERMINAL_STATES:
            self._job = self._engine.get_job(self.job_resource_name)
        return self._job

    def status(self):
        """Return the execution status of the job."""
        return self._update_job()['executionStatus']['state']

    def cancel(self):
        """Cancel the job."""
        self._engine.cancel_job(self.job_resource_name)

    def results(self) -> List[EngineTrialResult]:
        """Returns the job results, blocking until the job is complete."""
        if not self._results:
            job = self._update_job()
            for _ in range(1000):
                if job['executionStatus']['state'] in TERMINAL_STATES:
                    break
                time.sleep(0.5)
                job = self._update_job()
            if job['executionStatus']['state'] != 'SUCCESS':
                raise RuntimeError(
                    'Job %s did not succeed. It is in state %s.' % (
                        job['name'], job['executionStatus']['state']))
            self._results = self._engine.get_job_results(
                self.job_resource_name)
        return self._results

    def __iter__(self):
        return self.results().__iter__()


def engine_from_environment() -> Engine:
    """Returns an Engine instance configured using environment variables.

    The two environment variables that must be specified are:
        QUANTUM_ENGINE_API_KEY
        QUANTUM_ENGINE_PROJECT

    QUANTUM_ENGINE_API_KEY should be the API key to ...?
    QUANTUM_ENGINE_PROJECT should be ...?
    """

    env_api_key = 'QUANTUM_ENGINE_API_KEY'
    env_default_project_id = 'QUANTUM_ENGINE_PROJECT'

    api_key = os.environ[env_api_key]
    if not api_key:
        raise EnvironmentError(
            'Environment variable {} is not set.'.format(env_api_key))

    default_project_id = os.environ[env_default_project_id]
    if not default_project_id:
        raise EnvironmentError(
            'Environment variable {} is not set.'.format(
                env_default_project_id))

    return Engine(api_key=api_key, default_project_id=default_project_id)


def _sweepable_to_sweeps(sweepable: Sweepable) -> List[Sweep]:
    if isinstance(sweepable, ParamResolver):
        return [_resolver_to_sweep(sweepable)]
    elif isinstance(sweepable, Sweep):
        return [sweepable]
    elif isinstance(sweepable, Iterable):
        iterable = cast(Iterable, sweepable)
        if isinstance(next(iter(iterable)), Sweep):
            sweeps = iterable
            return list(sweeps)
        else:
            resolvers = iterable
            return [_resolver_to_sweep(p) for p in resolvers]
    else:
        raise TypeError('Unexpected Sweepable.') # coverage: ignore


def _resolver_to_sweep(resolver: ParamResolver) -> Sweep:
    return Zip(*[Points(key, [value]) for key, value in
                 resolver.param_dict.items()]) if len(
        resolver.param_dict) else Unit
