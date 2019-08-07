#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import click

from aiida.plugins import DataFactory
from aiida.orm import Code, Dict, Float
from aiida.engine import submit
from water_isotherm_workchains.converge_loading_workchain import (
    ConvergeLoadingWorkchain,
)
from water_isotherm_workchains.utils.utils import slugify

ParameterData = DataFactory("dict")
SinglefileData = DataFactory("singlefile")
CifData = DataFactory("cif")

# Import the structure
structure = CifData(file=os.path.abspath("../test_files/uio-66.cif"))
structure_label = slugify(structure.filename)
structure.label = structure_label


@click.command("cli")
@click.argument("raspa_code_string")
@click.argument("zeopp_code_string")
def main(raspa_code_string, zeopp_code_string):
    zeopp_code = Code.get_from_string(zeopp_code_string)
    raspa_code = Code.get_from_string(raspa_code_string)

    zeopp_atomic_radii_file = SinglefileData(
        file=os.path.abspath("../test_files/zeopp.rad")
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

    raspa_comp = {
        "comp1": {
            "name": "methane",
            "mol_fraction": 1.0,
            "mol_def": "TraPPE",
            "conv_threshold": 5,
            "radius": 1.4,
            "singlebead": True,
        }
    }

    raspa_parameters = Dict(
        dict={
            "GeneralSettings": {
                "SimulationType": "MonteCarlo",
                "NumberOfCycles": 10000,
                "NumberOfInitializationCycles": 30000,
                "PrintEvery": 1000,
                "CutOff": 12.0,
                "WriteBinaryRestartFileEvery": 5000,
                "Forcefield": "GenericMOFs",
                "RemoveAtomNumberCodeFromLabel": True,
            },
            "System": {
                structure_label: {"ExternalTemperature": 500, "type": "Framework"}
            },
            "Component": {"comp" + str(i + 1): {} for i in range(len(raspa_comp))},
        }
    )

    zeopp_parameters = Dict(
        dict={
            "block_samples": 100,
            "volpo_samples": 100,
            "sa_samples": 100,
            "accuracy": "DEF",
        }
    )

    submit(
        ConvergeLoadingWorkchain,
        structure=structure,
        zeopp_code=zeopp_code,
        pressure=Float(5e5),
        min_cycles=Int(1500),
        zeopp_options=zeopp_options,
        raspa_options=raspa_options,
        raspa_parameters=raspa_parameters,
        zeopp_parameters=zeopp_parameters,
        raspa_code=raspa_code,
        raspa_comp=raspa_comp,
        zeopp_atomic_radii=zeopp_atomic_radii_file,
        metadata={
            "label": "MultiCompIsothermWorkChain",
            "description": "Test for <{}>".format(structure.label),
        },
    )


if __name__ == "__main__":
    main()
