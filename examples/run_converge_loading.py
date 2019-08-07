#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys

from aiida.common import NotExistent
from aiida.plugins import DataFactory
from aiida.orm import Code, Dict
from aiida.engine import submit
from water_isotherm_workchains.converge_loading_workchain import (
    ConvergeLoadingWorkchain,
)
from water_isotherm_workchains.utils import slugify

ParameterData = DataFactory("dict")
SinglefileData = DataFactory("singlefile")
CifData = DataFactory("cif")

# Import the structure
structure = CifData(file=os.path.abspath("../test_files/uio-66.cif"))
structure.label = slugify(structure.filename)


zeopp_code = Code.get_from_string(zeopp_codename)
raspa_code = Code.get_from_string(raspa_codename)


zeopp_atomic_radii_file = SinglefileData(
    file=os.path.abspath("./UFF.rad")
)  # Radius file for the framework

general_calc_params = Dict(
    dict={
        "zeopp": {
            "pld_min": 3.90,
            "lcd_max": 15.0,
            "volpo_samples": 100,
            "sa_samples": 100,
            "block_samples": 100,
            "accuracy": "DEF",
        },
        "raspa": {
            "pressure_min": 0.6e5,
            "pressure_max": 1.0e5,
            "dpa": 0.1e5,
            "dpmax": 0.2e5,
            "widom_cycle_mult": 1,
            "verbosity": 10,
            "cutoff": 12.0,
            "isotherm_dynamic": True,
            "isotherm_full": True,
            "selected_pressures": [0.1e5, 1.0e5],
            "kh_min": 1e-10,
            "usecharges": False,
            "charge_from_cif": True,
            "simulation_type": "MonteCarlo",
            "system_type": "Framework",
            "temperature": 300.0,
            "additional_cycle": 5000,
            "molsatdens": 21.2,
        },
    }
)

raspa_comp = {
    "comp1": {
        "name": "CO2",
        "mol_fraction": 1.0,
        "radius": 1.65,
        "mol_def": "TraPPE",
        "conv_threshold": 0.10,
        "singlebead": False,
    }
}


raspa_parameters = Dict(
    dict={
        "GeneralSettings": {
            "NumberOfCycles": 1000,
            "NumberOfInitializationCycles": 1000,
            "PrintEvery": 1000,
            "Forcefield": "GenericMOFs",
            "RemoveAtomNumberCodeFromLabel": True,
        },
        "System": {},
        "Component": {"comp" + str(i + 1): {} for i in range(len(list(raspa_comp)))},
    }
)

zeopp_options = {
    "resources": {"num_machines": 1, "tot_num_mpiprocs": 1},
    "max_memory_kb": 2000000,
    "max_wallclock_seconds": 1 * 30 * 60,
    "withmpi": False,
}

raspa_options = {
    "resources": {"num_machines": 1, "tot_num_mpiprocs": 1},
    "max_memory_kb": 200000,
    "max_wallclock_seconds": 2 * 60 * 60,
    "withmpi": False,
}


submit(
    MultiCompIsothermWorkChain,
    structure=structure,
    zeopp_code=zeopp_code,
    raspa_code=raspa_code,
    raspa_parameters=raspa_parameters,
    raspa_comp=raspa_comp,
    zeopp_atomic_radii=zeopp_atomic_radii_file,
    general_calc_params=general_calc_params,
    zeopp_options=zeopp_options,
    raspa_options=raspa_options,
    metadata={
        "label": "MultiCompIsothermWorkChain",
        "description": "Test for <{}>".format(structure.label),
    },
)
