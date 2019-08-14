# -*- coding: utf-8 -*-
"""DdecCp2kChargesWorkChain workchain of the AiiDA DDEC plugin"""
from __future__ import absolute_import
from copy import deepcopy

from aiida.common import AttributeDict
from aiida.engine import WorkChain, ToContext
from aiida.orm import Dict, Code, Str
from aiida.plugins import CalculationFactory, DataFactory
from aiida_cp2k.workchains import Cp2kMultistageWorkChain
from .utils import merge_Dict, extract_core_electrons

# calculations
DdecCalculation = CalculationFactory('ddec')  # pylint: disable=invalid-name

# data objects
CifData = DataFactory('cif')  # pylint: disable=invalid-name

default_ddec_options = {  # pylint: disable=invalid-name
    'resources': {'num_machines': 1, 'num_mpiprocs_per_machine': 1},
    'max_wallclock_seconds': 3 * 60 * 60,
    'withmpi': False,
}

default_cp2k_options = {  # pylint: disable=invalid-name
    'resources': {'num_machines': 2},
    'max_wallclock_seconds': 48 * 60 * 60,
}

default_ddec_params = Dict(  # pylint: disable=invalid-name
    dict={
        'net charge': 0.0,
        'charge type': 'DDEC6',
        'periodicity along A, B, and C vectors': [True, True, True],
        'compute BOs': False,
        'atomic densities directory complete path': '/home/yakutovi/chargemol_09_26_2017/atomic_densities/',
        'input filename': 'valence_density',
    }
).store()


class Cp2kRelaxChargesWorkChain(WorkChain):
    """A workchain that computes DDEC and EqEq charges using D. Ongari's multistage CP2K workchain"""
    @classmethod
    def define(cls, spec):
        """Define workflow specification."""
        super(Cp2kRelaxChargesWorkChain, cls).define(spec)

        spec.expose_inputs(Cp2kMultistageWorkChain,
                           namespace='cp2k_multistage')

        # DDEC
        spec.input('ddec_code', valid_type=Code)
        spec.input(
            'ddec_parameters',
            valid_type=Dict,
            default=default_ddec_params,
            required=False,
        )
        spec.input_namespace('ddec_options',
                             default=deepcopy(default_ddec_options),
                             dynamic=True,
                             required=False,
                             non_db=True)

        # Eqeq
        spec.input('eqeq_code', valid_type=Code)
        spec.input(
            'eqeq_parameters',
            valid_type=Dict,
            default=default_eqeq_params,
            required=False,
        )
        spec.input_namespace('eqeq_options',
                             default=deepcopy(default_eqeq_options),
                             dynamic=True,
                             required=False,
                             non_db=True)

        # specify the chain of calculations to be performed
        spec.outline(cls.setup, cls.select_protocol, cls.run_cp2k,
                     cls.prepare_ddec, cls.run_ddec, cls.run_eqeq,
                     cls.return_results)

        spec.expose_outputs(Cp2kMultistageWorkChain,
                            include=('output_structure', 'remote_folder'))

        # specify the outputs of the workchain
        spec.output('output_structure_ddec', valid_type=CifData, required=True)
        spec.output('output_structure_eqeq', valid_type=CifData, required=True)

    def setup(self):
        """Perform initial setup"""
        self.ctx.base_inp = AttributeDict(
            self.exposed_inputs(Cp2kMultistageWorkChain, 'cp2k_multistage'))

        self.ctx.inp_structure = self.ctx.base_inp.base.cp2k.structure

    def select_protocol(self):
        """selects relaxation protocol with some simple heuristics"""
        # check if a lot of electrons
        total_number_electrons = self.ctx.inp_structure.get_pymatgen(
        )._nelectrons

        if total_number_electrons > 2000:
            self.ctx.protocol = Str("large")
        else:
            self.ctx.protocol = Str("std")

    def run_cp2k(self):
        """Compute charge-density with CP2K"""
        parameters = Dict(
            dict={
                'FORCE_EVAL': {
                    'DFT': {
                        'PRINT': {
                            'E_DENSITY_CUBE': {
                                '_': 'ON',
                                'STRIDE': '1 1 1'
                            }
                        }
                    }
                }
            }).store()

        inputs = deepcopy(self.ctx.base_inp)
        # input settings for the charge density cube
        inputs['base']['cp2k']['parameters'] = parameters
        inputs['protocol_tag'] = self.ctx.protocol
        running = self.submit(Cp2kMultistageWorkChain, **inputs)
        self.report(
            'pk: {} | Running Cp2kMultistageWorkChain to compute the charge-density'
            .format(running.pk))
        return ToContext(charge_density_calc=running)

    def prepare_ddec(self):
        """Prepare inputs for ddec point charges calculation."""
        # extract number of core electrons from the cp2k output
        last_res_repo_path = self.ctx.charge_density_calc.outputs.remote_folder.creator.outputs.retrieved._repository._get_base_folder(  # pylint: disable=protected-access, line-too-long
        ).abspath

        core_e = extract_core_electrons(Str(last_res_repo_path))
        # prepare input dictionary
        self.ctx.ddec_inputs = {
            'code':
            self.inputs.ddec_code,
            'charge_density_folder':
            self.ctx.charge_density_calc.outputs.remote_folder.creator.outputs.
            remote_folder,
            'parameters':
            merge_Dict(self.inputs.ddec_parameters, core_e),
            'metadata': {
                'options': self.inputs.ddec_options,
                'label': 'DDEC calculation',
            },
        }

    def run_ddec(self):
        """Compute ddec point charges from precomputed charge-density."""
        # Create the calculation process and launch it
        running = self.submit(DdecCalculation, **self.ctx.ddec_inputs)
        self.report(
            'pk: {} | Running ddec to compute point charges based on the charge-density'
            .format(running.pk))
        return ToContext(ddec_calc=running)

    def return_results(self):
        self.report('DdecCp2kChargesWorkChain is completed')
        self.out('output_structure_ddec', self.ctx.ddec_calc.outputs.structure)
