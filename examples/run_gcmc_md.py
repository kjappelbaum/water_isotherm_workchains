#!/usr/bin/python2
# -*- coding: utf-8 -*-
__author__ = 'Kevin M. Jablonka'
__copyright__ = 'MIT License'
__maintainer__ = 'Kevin M. Jablonka'
__email__ = 'kevin.jablonka@epfl.ch'
__version__ = '0.1.0'
__status__ = 'Dev'

import os
from aiida.common.example_helpers import test_and_get_code
from aiida.orm import DataFactory
from aiida.orm.data.base import Float
from aiida.work.run import submit
from water_isotherm_workchains.gcmc_md_workchain import GCMCMD

# data objects
ParameterData = DataFactory('parameter')
CifData = DataFactory('cif')
SinglefileData = DataFactory('singlefile')

structure = CifData(file=os.path.abspath(os.path.join('..', 'test_files', 'uio-66.cif')))
probe_radius = 1.525
atomic_radii = SinglefileData(file=os.path.abspath(
    "../test_files/zeopp.rad"
))  #
number_runs = 10  # how often do we repeat the GCMC/MD cyle?
pressure = 1000  # in Pa

# option for zeo++ and raspa
zr_options = {
    "resources": {
        "num_machines": 1,
        "tot_num_mpiprocs": 1,
    },
    "max_wallclock_seconds": 7 * 60 * 60,
    "withmpi": False,
}

raspa_parameters_gcmc = ParameterData(
    dict={
        "GeneralSettings": {
            "SimulationType": "MonteCarlo",
            "NumberOfCycles": 500,
            "NumberOfInitializationCycles": 0,
            "ChargeMethod": "Ewald",
            "CutOff": 12.0,
            "Forcefield": "LSMO_UFF-TraPPE",
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 500,
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "ExternalTemperature": 298.0,
        },
        "Component": [{
            "MoleculeName": "CO2",
            "MoleculeDefinition": "TraPPE",
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
            "NumberOfInitializationCycles": 10000,
            "ChargeMethod": "Ewald",
            "CutOff": 12.0,
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 1000,
            "Forcefield": "LSMO_UFF-TraPPE",
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "HeliumVoidFraction": 0.0,
            "ExternalTemperature": 298.0,
        },
        "Component": [{
            "MoleculeName": "CO2",
            "MoleculeDefinition": "TraPPE",
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
            "NumberOfCycles": 2000,
            "NumberOfInitializationCycles": 0,
            "NumberOfEquilibrationCycles": 0,
            "ChargeMethod": "Ewald",
            "CutOff": 12.0,
            'RemoveAtomNumberCodeFromLabel': 'yes',
            "ComputeRDF": "yes",
            "WriteRDFEvery": 2000,
            "Forcefield": "LSMO_UFF-TraPPE",
            "EwaldPrecision": 1e-6,
            "Framework": 0,
            "UnitCells": "1 1 1",
            "HeliumVoidFraction": 0.0,
            "Ensemble": "NVT",
            "TimeStep": 0.0005,
            "ExternalTemperature": 330.0,
        },
        "Component": [{
            "MoleculeName": "CO2",
            "MoleculeDefinition": "TraPPE",
            "TranslationProbability": 1.0,
            "RotationProbability": 1.0,
            "ReinsertionProbability": 1.0,
            "CreateNumberOfMolecules": 0,
        }],
    })



zeopp_code = test_and_get_code('zeopp@fidis',
                               expected_code_type='zeopp.network')
raspa_code = test_and_get_code('raspa2@fidis', expected_code_type='raspa')

submit(
    GCMCMD,
    structure=structure,
    zeopp_probe_radius=Float(probe_radius),
    number_runs=Float(number_runs),
    pressure=Float(pressure),
    zeopp_code=zeopp_code,
    _zeopp_options=zr_options,
    zeopp_atomic_radii=atomic_radii,
    raspa_code=raspa_code,
    raspa_parameters=raspa_parameters_gcmc,
    raspa_parameters_gcmc_0=raspa_parameters_gcmc_0,
    _raspa_options=zr_options,
    _usecharges=True,
    _label='Isotherm',
)
