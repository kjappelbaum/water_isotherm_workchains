#!/usr/bin/python2
# -*- coding: utf-8 -*-
__author__ = 'Kevin M. Jablonka'
__copyright__ = 'MIT License'
__maintainer__ = 'Kevin M. Jablonka'
__email__ = 'kevin.jablonka@epfl.ch'
__version__ = '0.1.0'
__status__ = 'Dev'

import time
import os
import glob
from aiida.common.example_helpers import test_and_get_code
from aiida.orm import DataFactory
from aiida.orm.data.base import Float
from aiida.work.run import submit
from water_isotherm_workchains.gcmc_md_cycle_dist_workchain import GCMCMD2

# data objects
ParameterData = DataFactory('parameter')
CifData = DataFactory('cif')
SinglefileData = DataFactory('singlefile')

pressures = [
     00.023e5]


cifs = [os.path.abspath(os.path.join('..', 'test_files', 'uio-66.cif'))]
probe_radius = 3.1589 / 2.
atomic_radii = SinglefileData(
    file=os.path.abspath("../test_files/zeopp.rad"))  #
number_runs = 2  # how often do we repeat the GCMC/MD cycle?

# option for zeo++ and RASPA
zr_options = {
    "resources": {
        "num_machines": 1,
        "tot_num_mpiprocs": 1,
    },
    "max_wallclock_seconds": 24 * 60 * 60,
    "withmpi": False,
}

raspa_parameters_gcmc = ParameterData(
    dict={
        "GeneralSettings": {
            "SimulationType": "MonteCarlo",
            "NumberOfCycles": 1000,
            "NumberOfInitializationCycles": 0,
            "ChargeMethod": "Ewald",
            "CutOff": 13.0,
            "Forcefield": "UFF-TIP4P-TC",
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 1000,
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "ExternalTemperature": 298.0,
        },
        "Component": [{
            "MoleculeName": "tip4p",
            "MoleculeDefinition": "tip4p",
            "TranslationProbability": 0.5,
            "RotationProbability": 0.5,
            "ReinsertionProbability": 0.5,
            "SwapProbability": 1.0,
            "CreateNumberOfMolecules": 0,
        }],
    })

raspa_parameters_gcmc_0 = ParameterData(
    dict={
        "GeneralSettings": {
            "SimulationType": "MonteCarlo",
            "NumberOfCycles": 2000,
            "NumberOfInitializationCycles": 20000,
            "ChargeMethod": "Ewald",
            "CutOff": 13.0,
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 2000,
            "Forcefield": "UFF-TIP4P",
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "ExternalTemperature": 298.0,
        },
        "Component": [{
            "MoleculeName": "tip4p",
            "MoleculeDefinition": "tip4p",
            "TranslationProbability": 0.5,
            "RotationProbability": 0.5,
            "ReinsertionProbability": 0.5,
            "SwapProbability": 1.0,
            "CreateNumberOfMolecules": 0,
        }],
    })

raspa_parameters_md = ParameterData(
    dict={
        "GeneralSettings": {
            "SimulationType": "MolecularDynamics",
            "NumberOfCycles": 15000,
            "NumberOfInitializationCycles": 0,
            "NumberOfEquilibrationCycles": 0,
            "ChargeMethod": "Ewald",
            "CutOff": 13.0,
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 15000,
            "Forcefield": "UFF-TIP4P",
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "HeliumVoidFraction": 0.0,
            "Ensemble": "NVT",
            "TimeStep": 0.0005,
            "ExternalTemperature": 298.0,
        },
        "Component": [{
            "MoleculeName": "tip4p",
            "MoleculeDefinition": "tip4p",
            "TranslationProbability": 1.0,
            "RotationProbability": 1.0,
            "ReinsertionProbability": 1.0,
            "CreateNumberOfMolecules": 0,
        }],
    })

zeopp_code = test_and_get_code('zeopp@fidis',
                               expected_code_type='zeopp.network')
raspa_code = test_and_get_code('raspa2@fidis', expected_code_type='raspa')

for cif in cifs:
    for pressure in pressures:
        structure = CifData(file=cif)
        submit(
            GCMCMD2,
            structure=structure,
            zeopp_probe_radius=Float(probe_radius),
            number_runs=Float(number_runs),
            pressure=Float(pressure),
            number_cycles_lower=Float(1),
            number_cycles_upper=Float(100000),
            zeopp_code=zeopp_code,
            _zeopp_options=zr_options,
            zeopp_atomic_radii=atomic_radii,
            raspa_code=raspa_code,
            raspa_parameters_md=raspa_parameters_md,
            raspa_parameters_gcmc=raspa_parameters_gcmc,
            raspa_parameters_gcmc_0=raspa_parameters_gcmc_0,
            _raspa_options=zr_options,
            _usecharges=True,
            _label='gcmc_md_test',
        )
        time.sleep(10)
